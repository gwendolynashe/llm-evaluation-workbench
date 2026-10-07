"""Offline checks for the promptfoo configs.

The static tests need only PyYAML. The end-to-end tests run the real promptfoo CLI
against tests/mock_endpoint.py on localhost; they are skipped when no promptfoo
binary is found (set PROMPTFOO_BIN or put promptfoo on PATH).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ["promptfooconfig.yaml", "promptfooconfig.replies.yaml"]
OPENAI_REASONING_NAMES = ("gpt-",)  # promptfoo forwards config.reasoning_effort only for these


def load(name):
    return yaml.safe_load((ROOT / name).read_text())


@pytest.mark.parametrize("name", CONFIGS)
def test_providers_share_one_endpoint_and_price_every_token(name):
    config = load(name)
    providers = config["providers"] + [config["defaultTest"].get("options", {}).get("provider")]
    providers = [p for p in providers if p]
    assert len({p["config"]["apiBaseUrl"] for p in providers}) == 1
    for provider in providers:
        cfg = provider["config"]
        assert cfg["apiKeyEnvar"] == "GATEWAY_API_KEY"
        assert cfg["omitDefaults"] is True, f"{provider['id']} would get temperature 0 and max_tokens 1024"
        assert 0 < cfg["inputCost"] <= cfg["outputCost"] < 0.0001, provider["id"]


@pytest.mark.parametrize("name", CONFIGS)
def test_reasoning_effort_reaches_non_openai_models_via_passthrough(name):
    for provider in load(name)["providers"]:
        model = provider["id"].split(":")[-1]
        if not model.startswith(OPENAI_REASONING_NAMES):
            assert "reasoning_effort" not in provider["config"], f"{model}: promptfoo would drop it silently"


def test_triage_cases_are_labelled_with_known_values():
    cases = yaml.safe_load((ROOT / "cases" / "triage.yaml").read_text())
    assert len(cases) == 12
    for case in cases:
        assert case["vars"]["category"] in {"billing", "bug", "account", "how-to", "other"}
        assert isinstance(case["vars"]["urgent"], bool)


def promptfoo_bin():
    return os.environ.get("PROMPTFOO_BIN") or shutil.which("promptfoo")


@pytest.fixture(scope="module")
def mock(tmp_path_factory):
    work = tmp_path_factory.mktemp("eval")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log = work / "requests.jsonl"
    server = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_endpoint.py"), str(port), str(log)])
    time.sleep(1)
    for item in ("prompts", "cases"):
        shutil.copytree(ROOT / item, work / item)
    for name in CONFIGS:
        text = (ROOT / name).read_text().replace(load(name)["providers"][0]["config"]["apiBaseUrl"],
                                                 f"http://127.0.0.1:{port}/v1")
        (work / name).write_text(text)
    yield work, log
    server.terminate()


def run_eval(work, name):
    env = {**os.environ, "GATEWAY_API_KEY": "test-key", "PROMPTFOO_DISABLE_TELEMETRY": "1",
           "PROMPTFOO_DISABLE_UPDATE": "1", "PROMPTFOO_CACHE_ENABLED": "false",
           "PROMPTFOO_CONFIG_DIR": str(work / ".promptfoo")}
    out = work / f"{name}.json"
    subprocess.run([promptfoo_bin(), "eval", "-c", name, "--no-cache", "--no-table", "-o", str(out)],
                   cwd=work, env=env, check=False, capture_output=True, timeout=300)
    return json.loads(out.read_text())["results"]["results"]


@pytest.mark.skipif(not promptfoo_bin(), reason="promptfoo CLI not installed")
def test_triage_eval_end_to_end(mock):
    work, log = mock
    rows = run_eval(work, "promptfooconfig.yaml")
    assert len(rows) == 48 and all(row["success"] for row in rows)
    luna = next(r for r in rows if r["provider"]["label"] == "gpt-5.6-luna")
    assert luna["cost"] == pytest.approx(250 * 0.00000006 + 40 * 0.00000036)
    bodies = {json.loads(line)["body"]["model"]: json.loads(line)["body"] for line in log.read_text().splitlines()}
    assert "temperature" not in bodies["claude-sonnet-5"] and "max_tokens" not in bodies["claude-sonnet-5"]
    assert bodies["deepseek-v4.1-flash"]["reasoning_effort"] == "none"
    assert bodies["gpt-5.6-luna"]["reasoning_effort"] == "low"


@pytest.mark.skipif(not promptfoo_bin(), reason="promptfoo CLI not installed")
def test_rubric_grader_goes_to_the_same_endpoint(mock):
    work, log = mock
    rows = run_eval(work, "promptfooconfig.replies.yaml")
    assert len(rows) == 8 and all(row["success"] for row in rows)
    graded = [json.loads(line)["body"] for line in log.read_text().splitlines() if "<Rubric>" in line]
    assert graded and {body["model"] for body in graded} == {"gpt-6-sol"}
