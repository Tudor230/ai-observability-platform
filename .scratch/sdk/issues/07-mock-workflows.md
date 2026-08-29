# Mock workflows design

Type: grilling
Status: resolved
Blocked by: 02, 04

## Question

How do we design the deterministic test harness: fixed inputs/outputs/cost, expected traces, and deliberate failures (tool timeout, LLM error, invalid JSON, retrieval failure, high latency) that validate SDK capture and backend failure classification? What does a mock workflow look like end-to-end, and how are expected traces asserted?

## Answer

Decided by grilling with the user.

- **Purpose in v1**: validate SDK capture — expected trace shape, attributes, and failure propagation asserted against exported OTLP. The harness is **backend-ready**: the same deterministic traces feed backend failure classification and cost computation once the backend exists.
- **Form**: Python scenarios run through the real SDK + instrumentors, using **framework-native fake models** (LangChain `FakeChatModel`, LlamaIndex `MockLLM`) with fixed responses and fixed usage metadata. Bundled in the SDK repo; runnable via **pytest** and a **CLI** that prints a pass/fail report with failing assertions.
- **Expected trace**: programmatic assertions only — trace shape (span kinds + hierarchy: workflow CHAIN root, AGENT, LLM/TOOL/RETRIEVER nesting), attributes (token counts, model, provider, business context, version, session.id), and failure propagation (`sdk.error.*` attributes, root ERROR status + summary, retry counts).
- **Failure catalog (v1)**: tool timeout, LLM error, invalid JSON, retrieval failure, high latency (controlled fake sleep), rate limit (429-style error), retry-then-success (`sdk.retry.count > 0` asserted).
- **Fixed cost**: fake providers return fixed token counts → token/cost math deterministic; v1 asserts token counts; the same traces exercise backend cost computation later.
- **Acceptance path**: the scenario suite runs in CI on every SDK change — it is the SDK's own regression gate.