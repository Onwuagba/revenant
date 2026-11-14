# Design: ingestion

## Components (under `backend/src/revenant/compiler/`)
- `ingest_openapi.py`: size check, safe load, own `$ref` resolver (local by default), operation extraction to draft IR, hand-off to `classify_operation`.
- `ingest_mcp.py`: official `mcp` SDK client over streamable HTTP; `tools/list` to draft Operations; sidecar `revenant.yaml` keyed by tool name for annotations.
- `urlguard.py` (inside compiler or a shared `security` module): `check_url(url) -> ResolvedTarget` doing scheme check, DNS resolve, address-class rejection, redirect re-check, size/time caps. Fetchers must pin the resolved IP to avoid DNS rebinding between check and connect.
- Stdio registry: a static dict of bundled sample servers; no user-supplied command path exists in code.

## Data flow
source bytes or MCP URL -> guard -> parse -> draft operations -> classifier (spec `ir-type-subset`) -> `ir.draft.json` + `refusals.json`.

## Error handling
Every failure is a typed result (Refusal or an `IngestError` with a code) so the platform can show it; never a stack trace to users.

## Testing strategy
Unit tests with blocked address ranges (127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7); fixtures: alias bomb, deep nesting, ReDoS pattern, prompt-injection description text; the vendored corpus test (compile never crashes) is added later.

## Correctness properties
No PBT property from TESTING.md is owned here; P7 (totality) is exercised end to end by feeding ingest output to the classifier. Fuzz tests cover T9.
