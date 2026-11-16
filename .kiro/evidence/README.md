# Kiro evidence log

Filled in during the build. Do not write entries for runs that did not happen. Keep the raw stream-json transcripts next to this file as `headless-run-<id>.jsonl`.

| Field | Run 1 (clinic) | Run 2 (farmer-prices) | Run 3 (adversarial spec) |
|---|---|---|---|
| Date | 2026-11-16 | not run | not run |
| kiro-cli version (`kiro-cli --version`) | 3.3.0 (Google login, no API key) | | |
| Command line used | `kiro-cli chat --no-interactive --v3 --agent ussd-annotator --trust-tools=read,write,@revenant-validator --output-format stream-json --require-mcp-startup "<constant instruction>"` via `scripts/kiro_smoke.sh` | | |
| Exit code | 0 | | |
| Fresh or cached | fresh (not cached) | | |
| Model id (from stream) | not reported in the stream (field empty) | | |
| Duration | 30.9 s | | |
| Validators passed | annotations passed schema check; merged bundle passed V1-V8; operation set unchanged; Kiro called `@revenant-validator/validate_draft` once | | |
| Transcript file | `smoke-20261116T072917Z/runs/e52835111119/transcript.jsonl` (133 events) | | |

## Hook firings
Paste a short log excerpt or screenshot name for each hook that really fired (pbt-on-compiler-save, verify-on-spec-change, pin-leak-guard, docs-drift).
