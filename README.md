# LLM evaluation workbench: promptfoo configs for comparing models behind one API

Two ready-to-run [promptfoo](https://github.com/promptfoo/promptfoo) evals — support-ticket triage scored with deterministic checks, and reply drafting graded by a stronger model — comparing models from four vendors through one OpenAI-compatible endpoint, with per-token prices so promptfoo reports real cost. Unofficial; not affiliated with promptfoo.

[Quick start](#quick-start) · [What is compared](#what-is-compared) · [Settings that matter](#six-promptfoo-settings-that-matter-with-a-gateway) · [Cost of a run](#what-a-run-costs) · [Claude via Messages](#claude-through-anthropic-messages-instead) · [FAQ](#faq)

<sub>Last checked: 2026-10-07 with promptfoo 0.124.0 (Node 22.22+). Every setting below was confirmed by running the CLI against a local mock endpoint; `tests/` repeats that run.</sub>

## Quick start

```bash
git clone https://github.com/gwendolynashe/llm-evaluation-workbench
cd llm-evaluation-workbench
export GATEWAY_API_KEY=your-key

npx promptfoo@latest eval                                    # triage: 12 tickets × 4 models
npx promptfoo@latest eval -c promptfooconfig.replies.yaml    # replies: 4 tickets × 2 models + grader
npx promptfoo@latest view                                    # side-by-side matrix in the browser
```

The configs point at [ArgoLink](https://argolink.io/gh-llm-evaluation-workbench) (`apiBaseUrl: https://argolink.io/v1`), which serves the GPT, DeepSeek, GLM, Claude and Kimi models used here under one key. To evaluate another OpenAI-compatible gateway, change `apiBaseUrl` in the `&gateway` anchor at the top of each config and use model IDs it serves.

## What is compared

| Eval | Provider ID | Settings | Input / output per 1M | Official input / output |
|---|---|---|---:|---:|
| triage | `openai:chat:gpt-5.6-luna` | `reasoning_effort: low` | $0.06 / $0.36 | $0.20 / $1.20 |
| triage | `openai:chat:deepseek-v4.1-flash` | `passthrough: {reasoning_effort: none}` | $0.12 / $0.48 | $0.15 / $0.60 |
| triage | `openai:chat:glm-5.3-flash` | `passthrough: {reasoning_effort: high}` | $0.12 / $0.40 | $0.15 / $0.50 |
| triage | `openai:chat:claude-sonnet-5` | no effort, no sampling params | $0.80 / $4.00 | $2 / $10 |
| replies | `openai:chat:gpt-5.6-terra` | `reasoning_effort: low` | $0.60 / $3.60 | $2 / $12 |
| replies | `openai:chat:kimi-k2.6` | thinking off (model default) | $0.76 / $3.20 | $0.95 / $4 |
| replies, grader | `openai:chat:gpt-6-sol` | `reasoning_effort: low` | $0.60 / $3.00 | $2 / $10 |

<sub>Rates from the public catalog (`GET https://argolink.io/api/catalog/v1/models?page_size=100`) and the model pages, 2026-10-07; they are the `inputCost`/`outputCost` values in the configs, divided per token. DeepSeek models bill 2× on weekdays 09:00–12:00 and 14:00–18:00 Beijing time. Re-check before you budget.</sub>

### Triage eval (`promptfooconfig.yaml`)

The prompt ([prompts/triage.json](./prompts/triage.json)) defines five categories and when a ticket is urgent, and asks for one JSON object. The 12 labelled tickets in [cases/triage.yaml](./cases/triage.yaml) carry the expected answer as `vars`, so one `defaultTest` checks them all:

| Metric | Assertion | Fails when |
|---|---|---|
| `valid_json` | `is-json` | the reply is not bare JSON (a ```` ```json ```` fence fails too) |
| `category` | `javascript: JSON.parse(output).category === context.vars.category` | wrong label |
| `urgency` | `javascript: JSON.parse(output).urgent === context.vars.urgent` | urgent flag wrong |
| — | `cost` < $0.002 per call | a reasoning budget runs away |
| — | `latency` < 30 s | the model is too slow for a triage queue |

Named metrics show up as separate pass rates in `promptfoo view`, so you can see that a model labels well but over-flags urgency.

### Reply eval (`promptfooconfig.replies.yaml`)

Four tickets whose good reply is easy to get wrong: a refund demand, an outage with "when will it be fixed?", a feature that does not exist, and a vague complaint. `llm-rubric` checks that the reply promises no refund, fix time or feature and ends with one concrete next step; a `javascript` assertion caps it at 120 words. The grader is `gpt-6-sol` on the same endpoint:

```yaml
defaultTest:
  options:
    provider:
      id: openai:chat:gpt-6-sol
      config:
        <<: *gateway
        reasoning_effort: low
```

## Six promptfoo settings that matter with a gateway

| Setting | Why | What happens without it (promptfoo 0.124.0) |
|---|---|---|
| `apiBaseUrl` | full base URL including `/v1`; promptfoo appends `/chat/completions` | requests go to the vendor's own API |
| `apiKeyEnvar: GATEWAY_API_KEY` | keeps the gateway key apart from a real `OPENAI_API_KEY` | promptfoo sends `OPENAI_API_KEY` to the gateway |
| `omitDefaults: true` | sends only what you configured | promptfoo adds `temperature: 0` and `max_tokens: 1024` for model names it does not know, and `claude-sonnet-5` answers 400 to any non-default `temperature` |
| `passthrough: {reasoning_effort: ...}` | for non-OpenAI model names | a plain `reasoning_effort` key is dropped silently for them, so DeepSeek keeps thinking and bills it |
| `inputCost` / `outputCost` | USD per token | promptfoo has no price for these model IDs; cost shows 0 and the `cost` assertion is meaningless |
| `defaultTest.options.provider` | puts the `llm-rubric` grader on your endpoint | promptfoo picks a default grader from the vendor keys in your environment (`openai:chat:gpt-6-sol` when `OPENAI_API_KEY` is set), with that vendor's key and URL |

## What a run costs

Estimated from the prompts in this repo: triage calls are about 180 input and 12 output tokens; reply drafts about 90 in and 160 out; each grading call about 460 in and 50 out. Reasoning tokens bill as output and come on top, so models that think (GLM-5.3 Flash always does, Claude Sonnet 5 does by default) cost more than shown. After a real run, promptfoo's cost column has the exact figure.

| Run | Calls | Estimated cost |
|---|---:|---:|
| triage, `gpt-5.6-luna` | 12 | $0.00018 |
| triage, `deepseek-v4.1-flash` (off-peak) | 12 | $0.00033 |
| triage, `glm-5.3-flash` | 12 | $0.00032 + thinking |
| triage, `claude-sonnet-5` | 12 | $0.0023 + thinking |
| **triage, all four** | 48 | **$0.0031 + thinking** |
| replies, `gpt-5.6-terra` + `kimi-k2.6` | 8 | $0.0048 |
| replies, grader `gpt-6-sol` | 8 | $0.0034 |
| **replies, total** | 16 | **$0.0083** |

promptfoo caches responses by default, so re-running an unchanged eval is free; pass `--no-cache` to measure again.

## Claude through Anthropic Messages instead

The triage config reaches Claude over Chat Completions, which the endpoint converts. To use Claude's own format (effort, thinking and prompt caching arrive as sent), swap the provider:

```yaml
  - id: anthropic:messages:claude-sonnet-5
    label: claude-sonnet-5 (messages)
    config:
      apiBaseUrl: https://argolink.io        # root origin: with /v1 the request goes to /v1/v1/messages
      apiKey: "{{ env.GATEWAY_API_KEY }}"
      effort: medium                         # sent as output_config.effort
      inputCost: 0.0000008
      outputCost: 0.000004
```

promptfoo's Anthropic provider sends `max_tokens: 2048` and no `temperature` by default, which is what `claude-sonnet-5` needs.

## Adding your own cases

Append to `cases/triage.yaml` with the same `vars` (`ticket`, `category`, `urgent`); the shared assertions apply automatically. For a new task, copy a config, write a prompt file in `prompts/`, and give each case its expected answer in `vars` so one `defaultTest` can check them all. Keep rubric assertions for what code cannot check.

## FAQ

**Why Chat Completions for every model, even GPT?**
It is the one format every model on the endpoint accepts, so all rows of the matrix go through the same path. For GPT models you can use the Responses API instead (`openai:responses:<model>` in promptfoo).

**Can the grader be the same model as a contestant?**
It can, but a model tends to grade its own style kindly. Use a different, stronger model for `llm-rubric`.

**Why did a model fail `valid_json` with an answer that looks right?**
Usually a code fence or a sentence around the JSON. That is a real instruction-following failure for a triage queue; switch the assertion to `contains-json` if you want to tolerate it.

**How many calls run in parallel?**
`evaluateOptions.maxConcurrency: 4`. Raise it if your account allows more parallel requests.

## Run the tests

```bash
pip install pytest pyyaml
pytest tests/                                   # static checks of both configs
PROMPTFOO_BIN=$(which promptfoo) pytest tests/  # also runs both evals end to end against tests/mock_endpoint.py
```

The end-to-end tests start a mock endpoint on localhost, point a copy of each config at it, run the real promptfoo CLI, and check the results, the computed cost, and the exact request bodies (no `temperature` for Claude, `reasoning_effort` delivered to DeepSeek, grader on the same endpoint). No key and no network needed.

## License

MIT
