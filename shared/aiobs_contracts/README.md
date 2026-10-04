# aiobs-contracts

Shared contract between [`ai-observability-sdk`](https://pypi.org/project/ai-observability-sdk/)
and the AI Observability Platform backend.

Single source of truth for:

- the `sdk.*` / OpenInference / `exception.*` attribute names both sides use,
- the authoritative failure taxonomy (`ERROR_KINDS`) and span kinds,
- payload-redaction rules and metadata redaction,
- best-effort classification hint patterns.

Both sides import these names instead of re-declaring them, so the SDK and the
backend cannot drift apart. You normally don't install this package directly —
the SDK pulls it in as a dependency.

## Development

Part of the [ai-observability-platform](https://github.com/Tudor230/ai-observability-platform)
monorepo (`shared/aiobs_contracts/`).
