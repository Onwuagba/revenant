# Design: Kiro compile step

## Components (`backend/src/revenant/compiler/annotate/` and `mcp_validator/`)
- `schema.py` + `annotations.schema.json`: the contract. Validate with `jsonschema` before anything else touches the output.
- `deterministic.py`: heuristic labels (truncate/transliterate titles, group by tag/prefix, risk from method/hints).
- `kiro_headless.py`: builds the run dir, runs the subprocess with a timeout, captures stream-json to a transcript file, parses exit codes, validates `annotations.json`, returns `AnnotatorResult(annotator, cached, reason, transcript_path, ...)`. Never raises; failures become fallback results.
- `merge.py`: applies annotations onto the draft IR; whitelisted effects only (labels, hints); idempotent.
- `mcp_validator/server.py`: FastMCP stdio server wrapping the validators.
- Agent definitions: `.kiro/agents/ussd-annotator.json` (headless) with prompt at `.kiro/agents/prompts/ussd-annotator.md`.
- Cache: `annotation_cache(spec_hash, agent_version)` in Postgres.

## Data flow
draft IR -> cache lookup -> (miss) headless run with validator MCP -> `annotations.json` -> schema check -> merge -> plan/render/validate -> (violations) repair run <= 2 -> bundle. Any failure -> deterministic annotator.

## Error handling
Exit codes 3 and 4, timeouts, bad JSON, schema violations are all "failure -> fallback" with a recorded reason.

## Security
Agent has read/write only in the run dir, no shell, no web (see `permissions.rules` in the agent file). Output is data; validators are the gate.

## Testing strategy
Schema tests; failure-injection tests (non-zero exit, invalid JSON, schema violation, timeout); adversarial fixture; `scripts/kiro_smoke.sh` (needs key, skipped in CI) with transcripts committed in `.kiro/evidence/`.

## Correctness properties (verbatim from docs/TESTING.md)
| ID | Property |
|---|---|
| P12 | Idempotence of merge: applying annotations twice equals once; annotations cannot add transitions or operations |
