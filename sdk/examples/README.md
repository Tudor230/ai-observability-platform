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

---

# Demo: rich RAG checkout-support agent

`rag_checkout_agent.py` is a richer, layered RAG demo for the MVP showcase. It
runs the same real LLM stack but produces a trace spanning **five span kinds**
under one workflow root:

```
CHAIN  checkout_rag          (workflow root, sdk.* business attrs)
├─ CHAIN retrieve_context
│  └─ RETRIEVER lookup_docs  (in-memory knowledge base -> retrieval.documents.*)
├─ CHAIN generate_answer
│  └─ AGENT checkout_agent
│     ├─ LLM                 (tool-calling step)
│     ├─ TOOL lookup_order   (real order lookup)
│     └─ LLM                 (final answer, fed the tool result)
├─ CHAIN compose_answer
└─ CHAIN validate_response
   ├─ CHAIN check_answer_non_empty
   ├─ CHAIN check_mentions_order_id
   └─ CHAIN check_delivery_eta
```

Run it exactly like `checkout_agent.py` (same provider config above):

```bash
cd sdk
OPENAI_API_KEY=sk-... uv run python examples/rag_checkout_agent.py "Where is my order ORD-1234?"
OPENAI_API_KEY=sk-... uv run python examples/rag_checkout_agent.py "What is the return policy?" --capture-prompts
```

The retriever is an in-memory `BaseRetriever` over a canned policy/FAQ
knowledge base, so the demo stays offline-runnable against any OpenAI-compatible
endpoint while still emitting real `RETRIEVER` + `retrieval.documents.*` spans.

---

# Demo: rich RAG order-support agent (LlamaIndex)

`rag_order_support_llamaindex.py` is the LlamaIndex counterpart for the MVP
showcase: a layered RAG order-support flow (retrieve -> tool -> synthesize ->
compose -> validate) producing a deep trace — **CHAIN / RETRIEVER / TOOL / LLM**
kinds under one workflow root:

```
CHAIN  order-support          (workflow root, sdk.* business attrs)
├─ CHAIN retrieve_context
│  └─ RETRIEVER PolicyRetriever.retrieve -> _retrieve
├─ CHAIN lookup_order_status
│  └─ TOOL  lookup_order      (FunctionTool call)
├─ CHAIN synthesize
│  └─ CHAIN RetrieverQueryEngine.query -> _query
│     ├─ RETRIEVER PolicyRetriever.retrieve -> _retrieve
│     └─ CHAIN CompactAndRefine.synthesize
│        └─ LLM  OpenAI.predict -> OpenAI.chat (tokens)
├─ CHAIN compose_answer
└─ CHAIN validate_response
   ├─ CHAIN check_answer_non_empty
   ├─ CHAIN check_mentions_order_id
   └─ CHAIN check_delivery_eta
```

Uses `llama_index.llms.openai.OpenAI` against the same provider config as the
LangChain demos (`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`):

```bash
cd sdk
OPENAI_API_KEY=sk-... uv run python examples/rag_order_support_llamaindex.py \
    "Where is my order ORD-1234?" --capture-prompts
```

---

# Demo: LangGraph human-in-the-loop refund approval

`langgraph_refund_approval.py` demonstrates **first-class LangGraph + HITL**
support. It compiles a `StateGraph` with conditional routing, LLM nodes, real
`@tool` nodes, and a `human_approval` node that calls `interrupt()` to pause
for a decision:

```
CHAIN  refund_approval        (workflow root, sdk.hitl.*, session.id = thread_id)
└─ CHAIN LangGraph
   ├─ CHAIN classify            (LLM -> intent routing)
   ├─ CHAIN check_policy        (TOOL lookup_policy)
   ├─ CHAIN draft_refund        (LLM -> proposal)
   ├─ CHAIN human_approval      ◀── interrupt(): the graph pauses here
   └─ (resume) CHAIN finalize   (TOOL create_refund + LLM resolution)
```

The graph runs twice: the **interrupt run** exports a trace ending at
`human_approval` (status OK, `sdk.hitl.interrupted=true`,
`sdk.hitl.interrupt_payload` = the question shown to the human), and the
**resume run** exports a second trace with `sdk.hitl.resume_value` +
`checkpoint_id`. Because `workflow_id` = the LangGraph `thread_id`, both traces
group into one Phoenix **session** — exactly how the HITL is meant to be
viewed.

Runs **fully offline** with a scripted fake model (fixed responses + usage) —
no API key needed:

```bash
cd sdk
uv run python examples/langgraph_refund_approval.py --mock --capture-prompts --auto-approve
# interactive: drop --auto-approve to decide y/N at the prompt
```

Or against a real OpenAI-compatible endpoint (same provider config as above):

```bash
OPENAI_API_KEY=sk-... uv run python examples/langgraph_refund_approval.py \
    --request-id ORD-1234 --capture-prompts
```

Then open http://localhost:6006 → Traces → project `demo` and follow the two
traces under the `ORD-1234` session, or inspect via
`uv run python dev/inspect_traces.py`.
