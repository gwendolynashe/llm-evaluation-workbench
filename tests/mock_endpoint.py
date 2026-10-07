"""A local stand-in for an OpenAI-compatible /v1/chat/completions endpoint.

Answers triage prompts with the labels from cases/triage.yaml, reply prompts with a
short fixed draft, and llm-rubric grader prompts with a passing grade. Every request
body is appended to the log file as one JSON line.

    python tests/mock_endpoint.py PORT LOGFILE
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

CASES = yaml.safe_load((Path(__file__).resolve().parent.parent / "cases" / "triage.yaml").read_text())
LABELS = {c["vars"]["ticket"]: {"category": c["vars"]["category"], "urgent": c["vars"]["urgent"]} for c in CASES}
USAGE = {"prompt_tokens": 250, "completion_tokens": 40, "total_tokens": 290}


def reply_text(messages):
    system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
    last = messages[-1]["content"]
    if "<Rubric>" in last:
        return json.dumps({"reason": "mock grade", "pass": True, "score": 1.0})
    if system.startswith("You triage"):
        return json.dumps(LABELS.get(last, {"category": "other", "urgent": False}))
    return "Sorry about the trouble. Please send the order number and we will check it today."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        with open(sys.argv[2], "a") as log:
            log.write(json.dumps({"path": self.path, "authorization": self.headers.get("authorization"), "body": body}) + "\n")
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        payload = json.dumps({
            "id": "chatcmpl-mock", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": reply_text(body["messages"])}}],
            "usage": USAGE,
        }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
