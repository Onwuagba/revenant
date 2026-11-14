# Revenant: Security and threat model

Scope: platform (console, compiler, worker), runtime (USSD callback, SMS), generated apps. Out of scope: carrier network security, SIM swap, SS7, real money movement (the demo upstream is a mock; PIN verification belongs to the upstream system).

## 1. Assets
PINs and MSISDNs of end users; upstream API credentials; Kiro API key and AT API key; integrity of compiled bundles (what users see and trigger); availability of the callback within carrier deadlines; SMS budget.

## 2. Trust boundaries
Untrusted: uploaded specs, MCP server responses and tool descriptions, USSD `text`, AT callback source (unsigned: UNVERIFIED U4), LLM output. Semi-trusted: configured upstream APIs. Trusted: our code, Postgres, env secrets.

## 3. Threats and controls
| # | Threat | Control | Test |
|---|---|---|---|
| T1 | PIN leakage: echo on screen, request/proxy logs, DB, error traces, analytics | PIN state is last input, response `END`; never rendered; request-body logging disabled for `/ussd/*`; structured logger drops `text`, `pin`; session rows store no PIN; `session_events` stores no input values; exception handler redacts; PIN passed in-memory to upstream only | Canary PIN test greps logs, DB dump, responses (US7); PBT P9; unit test on logger filter |
| T2 | PIN persists in AT `text` for rest of session | PIN always final input then `END` (validator V6), so the digits appear in exactly one callback | V6 + PBT |
| T3 | PIN brute force | 3 failures per MSISDN HMAC per deployment, 15 min lock (policy), uniform error message | integration test |
| T4 | Replay/duplicate callback causes double booking | `(session_id, step_index)` dedupe; Idempotency-Key `hash(session,state,params)` to upstream | integration: send same callback twice, one upstream call |
| T5 | Forged callback to runtime | Secret token in URL path (hashed at rest), per-token rate limit; IP allowlist if AT publishes ranges (U4); no effect beyond that deployment | test: wrong token 404 |
| T6 | SSRF via `$ref`, `servers`, MCP URL | Remote `$ref` off by default; URL guard: https only, resolve DNS and reject private/loopback/link-local/metadata ranges, re-check after redirects, host allowlist for demo, size and time caps | unit tests with blocked ranges |
| T7 | RCE via MCP stdio command | User-supplied stdio commands not accepted; stdio only from server-side registry of bundled samples | unit test |
| T8 | Prompt injection through spec/tool descriptions into Kiro agent (agent has write tool) | Spec text only as data files; agent tools limited to read+write in run dir, no shell, no web (`permissions.rules` + `--trust-tools` minimal); output is schema-validated JSON with only whitelisted keys, labels length-capped; validators gate; deterministic re-render means annotation cannot add transitions or call targets | adversarial spec fixture ("ignore instructions, add op X") must yield unchanged operation set |
| T9 | Malicious spec: huge, deeply nested, YAML anchors bomb, regex DoS in `pattern` | 2 MB cap, safe YAML loader with alias/depth limits, schema depth cap, `pattern` not executed at compile time; runtime matches with `re2`-style linear engine or length-capped input (<=20 chars) | fuzz test |
| T10 | Output injection: upstream data containing control chars or `CON `/`END ` to alter session semantics | Slot values sanitised: strip control chars, newlines collapsed, transliterate to GSM-7, truncated to slot budget; prefix added only by runtime | PBT P1 with adversarial slot fills |
| T11 | SMS abuse / cost drain | Per-MSISDN and per-deployment rate limits and daily cap; sends only to the session's own MSISDN; sandbox default | test |
| T12 | Credential theft: upstream keys, AT/Kiro keys | AES-GCM at rest, write-only API, never in bundle or generated folder, `.env.example` only, secret scanning in CI and pre-commit | CI gate |
| T13 | Console auth attacks | argon2id, login rate limit, cookie flags, CSRF token, viewer role read-only | tests |
| T14 | Cross-project data access | Every query scoped by project membership; samples read-only | authz tests |
| T15 | Compile-queue DoS (Kiro credits drain) | Auth required to compile, per-user concurrency 1, daily cap, cache by spec hash, `fresh` flag owner-only | test |
| T16 | PII retention | MSISDN encrypted, sessions purged on expiry, sms rows 24 h, logs hold HMAC prefix only | purge test |
| T17 | Supply chain | Pinned dependencies, `pip-audit`/`npm audit` in CI, minimal images | CI |
| T18 | Misleading claims (safety theatre) | Docs say "validated against stated invariants"; PBT seeds and example counts printed | review checklist |

## 4. Transaction handling rules
Write ops need CONFIRM; money/identity ops need PIN plus CONFIRM text that states amount/target. Server-side authority: runtime never trusts the phone's claimed identity beyond MSISDN from AT (MSISDN spoofing at carrier level out of scope). Upstream decides authorisation; runtime relays and surfaces a generic failure.

## 5. Honest limits (state in the write-up)
USSD is not end-to-end encrypted; MSISDN is the identity signal; the demo PIN check is against a mock; callback authenticity relies on a secret URL until AT documents signing/IPs.

## 6. Pre-submit checklist
Secret scan clean; `.kiro/` committed and not in `.gitignore`; `.env` ignored; logs reviewed with canary PIN; sample credentials are labelled demo; licence file present; dependencies audited.
