# Demo: real (non-mocked) workflow

`checkout_agent.py` runs a checkout-support agent with **real LLM calls**
(LangChain `ChatOpenAI` over HTTP) inside an `ai_observability.workflow()`
boundary, with a tool call (`lookup_order`), a chained validation step
(`validate_response` → `check_answer_non_empty` /
`check_mentions_order_id` / `check_delivery_eta` nested spans), and exports
the full trace to the dev stack (Phoenix + Postgres).

Works with **any OpenAI-compatible chat endpoint**: OpenAI, DeepSeek, Groq,
Ollama, LM Studio, vLLM, ...

## 1. Start the trace backend

```bash
cd sdk/dev
docker compose up -d --wait      # Phoenix :6006 + Postgres :5432
```

## 2. Configure a provider

| Provider | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `OPENAI_MODEL` |
|---|---|---|---|
| OpenAI | `sk-...` | *(unset)* | `gpt-4o-mini` |
| DeepSeek | `sk-...` | `https://api.deepseek.com` | `deepseek-chat` |
| Ollama (local) | `ollama` | `http://localhost:11434/v1` | `qwen2.5:7b` |
| LM Studio (local) | `lm-studio` | `http://localhost:1234/v1` | your loaded model |

## 3. Run

```bash
cd sdk
OPENAI_API_KEY=sk-... uv run python examples/checkout_agent.py "Where is my order ORD-1234?"

# payload capture opt-in (prompts/responses visible in the trace):
OPENAI_API_KEY=sk-... uv run python examples/checkout_agent.py --capture-prompts
```

If the provider does not support the `tools` parameter the agent still answers
(no tool call) — the demo degrades gracefully.

## 4. Inspect the trace

```bash
uv run python dev/inspect_traces.py                 # latest workflow roots
uv run python dev/inspect_traces.py --trace <id>    # full span list
```

or open the Phoenix UI at http://localhost:6006 (project `demo`).

To intentionally see failure capture, pass an unreachable endpoint or invalid
key — the workflow root will be `ERROR` with `sdk.error.*` attributes.