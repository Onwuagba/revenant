---
inclusion: fileMatch
fileMatchPattern: ["backend/src/revenant/runtime/**", "backend/src/revenant/platform/**", "tests/integration/**"]
---
# PIN and secrets rules (docs/SECURITY.md T1, T2, T10, T12)

## Never log `text`
- The USSD callback field `text` (cumulative input, may contain a PIN) MUST NEVER appear in any log line, exception message, trace, metric label, analytics event or DB row. Request-body logging is disabled for `/ussd/*`.
- The structured logger drops keys `text`, `pin`, `password`, `token`, `authorization`. Exception handlers redact before logging. Do not log `request.form()`, `dict(form)`, or f-strings containing them.
- `session_events` stores no input values. MSISDNs appear only as HMAC prefix in logs; stored encrypted (AES-GCM).

## PIN rules
1. PIN state is the LAST input of a flow; the response after it is `END`. A PIN state is followed only by its ACTION then a terminal state (P9, validator V6).
2. The PIN is never rendered on any screen, never echoed, never stored in `ussd_sessions.params`, never put in `last_response`.
3. The PIN is held in memory only, passed to the upstream call, then discarded.
4. Lockout: 3 upstream auth failures per MSISDN HMAC per deployment -> 15 min lock; the lock message is IDENTICAL to the bad-PIN message (no enumeration).
5. Money/identity operations: PIN plus a CONFIRM screen that states amount/target. Write operations always need CONFIRM.
6. A canary-PIN test greps responses, logs and a DB dump for the canary digits; it must stay green.

## Secrets
- Upstream credentials: AES-GCM at rest, write-only API, never in a bundle or generated folder. Generated apps read them from env.
- `KIRO_API_KEY` lives only in the worker environment. Never print, log, commit or echo any key. Only `.env.example` (empty values) is committed.

## Output injection
- Upstream data placed in slots is sanitised: control chars stripped, newlines collapsed, transliterated to GSM-7, truncated to slot budget. Only the runtime adds `CON `/`END `.
- Callback endpoint uses an unguessable per-deployment path token stored hashed; wrong token -> 404; malformed form -> 200 with generic `END` (never a stack trace).
