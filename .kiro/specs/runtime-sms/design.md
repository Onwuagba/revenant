# Design: runtime and SMS

## Components (`backend/src/revenant/runtime/`)
- `app.py`: FastAPI router factory `build_router(bundle, deps)`; shared by the platform and generated apps. Callback parsing, token check, response formatting.
- `machine.py`: pure `step(bundle, state, key) -> (state, screen)` and `replay(bundle, text) -> state`. No I/O.
- `session.py`: Postgres session cache, `(session_id, step_index)` dedupe, option cache.
- `actions.py`: upstream REST and MCP `tools/call` with deadline and Idempotency-Key; outcomes: ok, slow, long, error.
- `sms.py`: `SmsProvider` interface, outbox enqueue, worker claim loop.
- `redact.py`: logging filter dropping `text`, `pin`, `password`, `token`, `authorization`; exception-handler redaction.

## Data flow
Callback -> token check -> redacted logging (no body) -> dedupe -> replay from `text` -> `step` -> ACTION (if any) -> response. Slow/long -> `sms_outbox` row + `END`.

## Error handling
Any unexpected error returns HTTP 200 `END` with a generic message after redacted logging. Upstream failure -> generic failure text; lockout bookkeeping by MSISDN HMAC.

## Testing strategy
Contract tests with recorded AT payload fixtures; integration tests with Postgres container; the canary-PIN test; no-LLM run; Hypothesis P8, P9, P11, and a stateful `RuleBasedStateMachine` (cut-list item 9, built last).

## Correctness properties (verbatim from docs/TESTING.md)
| ID | Property |
|---|---|
| P8 | Replay equivalence: stateful session output equals output rebuilt from cumulative `text` |
| P9 | PIN: no screen, event, log record, or DB row contains the PIN canary; PIN state precedes only ACTION then terminal |
| P11 | SMS fallback: body GSM-7, segments <= budget, contains all declared result fields (lossless) or compile refuses with `R_...` |
