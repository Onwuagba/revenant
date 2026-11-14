# Milestones: 15 Nov to 3 Dec 2026 (deadline 4 Dec 14:00 PT = 23:00 WAT)

Capacity: solo, part-time. "Light" = weekday evening, "Heavy" = weekend day (15, 21, 22, 28, 29 Nov). Plan loads work onto heavy days. Shared hours with Lazarus are NOT assumed; RISK_REGISTER #1 says Revenant first, Lazarus go/no-go 22 Nov.

Disclose in README any pre-existing code (rule: build inside the period; the repo starts 15 Nov).

| Date | Load | Deliverable (done = tested + committed) |
|---|---|---|
| Sun 15 Nov | Heavy | Public GitHub repo + MIT licence + `.kiro/` committed (not gitignored). **Submit Kiro credits form** (due 1 Dec 12:00 PT, 48 business hours review). **Go/no-go U1-U3**: install kiro-cli, run a headless hello with `KIRO_API_KEY`/login, in Docker. AT: sandbox account, channel, tunnel, run `scripts/probe_at.py` (160/182/183 chars, non-GSM-7) and settle U4/U7. Email AT about shortcode + real-handset SMS (U5/U6). Pick host. |
| Mon 16 | Light | IR pydantic models, canonical JSON, OpenAPI ingest (local refs), Alembic base. Spec: `ir-type-subset`. |
| Tue 17 | Light | Type classifier + refusal codes + SSRF/URL guard. `examples/specs/clinic.openapi.yaml`, `unsupported-demo.openapi.yaml`, `clinic_api` mock. |
| Wed 18 | Light | Planner (state machine), renderer with slot budgets, gsm7 module. |
| Thu 19 | Light | Validators V1-V8 + mutation self-tests. |
| Fri 20 | Light | Hypothesis P1-P7, P10, P12, P13 green in `ci` profile; hook for PBT on save. |
| Sat 21 | Heavy | Runtime: AT callback route, session cache, replay-from-text (P8), dedupe, actions to upstream, redaction + canary PIN test (P9), pin lockout. Clinic flow passes in AT simulator. |
| Sun 22 | Heavy | SMS outbox + worker + `SmsProvider` (AT, emulator, modem stub), SMS fallback sizing (P11). MCP ingest + farmer MCP sample. **Lazarus go/no-go** (outside this plan). |
| Mon 23 | Light | Kiro stage: `ussd-annotator` agent, steering, annotation schema, headless runner, fallback annotator, cache, evidence capture, validator MCP server. |
| Tue 24 | Light | Kiro repair loop, adversarial-spec test (T8), failure-injection tests; commit transcripts. |
| Wed 25 | Light | Platform API: auth, projects, sources, compile runs + SSE, bundles, deployments. |
| Thu 26 | Light | Frontend shell + theme, Crypt, Exhume/Reanimate panels with live log. |
| Fri 27 | Light | State graph, screen inspector with char counter, Last Rites panel, Buried list. |
| Sat 28 | Heavy | Emulator (phone shell, keypad, SMS inbox) wired to the runtime; emitter writes `generated/clinic-booking` and `generated/farmer-prices`; Rise panel. |
| Sun 29 | Heavy | Deploy to public host (compose, Caddy TLS, kiro-cli in worker, seed samples, viewer account). AT callbacks live for both channels. Real-handset SMS test (U5 plan A or B). Playwright smoke. |
| Mon 30 | Light | Security pass (SECURITY checklist, secret scan, canary PIN on deployed host, dependency audit). Fix defects. `/judges` page. |
| Tue 1 Dec | Light | **Feature freeze.** Re-read official rules in Chrome (U10, category choice, hardware clause). Verify credits redeemed by 4 Dec. Rehearse demo twice; record backup takes. |
| Wed 2 Dec | Heavy-ish | Record final video (<3 min), upload public YouTube. Write Kiro-usage write-up with evidence links. README, docs final, honest claims review. |
| Thu 3 Dec | Light | **Submit on Devpost** (repo, video, live URL + credentials, write-up, category, bonuses). Smoke the live URL from a clean browser. |
| Fri 4 Dec | Reserve | Emergency fixes only; hard stop well before 14:00 PT. |

## Cut list (cut in this order when behind)
1. Bounded free-text interpretation (ADR-008): never built.
2. Local-language copy pack, `conservative` profile UI toggle.
3. Playwright E2E beyond one smoke test.
4. Session inspector page and delivery-report endpoint.
5. Modem SMS provider (keep only if AT live SMS fails U5).
6. Skeleton Crew polish: keep the two folders (emitter output), drop standalone Docker verification.
7. React Flow styling polish; fallback plain tree list.
8. `refine` repair loop (keep single Kiro pass + deterministic gate).
9. Stateful PBT (keep property tests P1-P8).
Never cut: IR + subset + refusals, validators V1-V7, P1/P2/P3/P5/P9, AT callback + emulator, SMS fallback, Kiro headless stage with evidence, public URL, video on real handset, `.kiro/` content, honest docs.

## Checkpoints / go-no-go
- 15 Nov: U1. If headless key unavailable: Plan B (local runs, cached results, labelled) and tell the write-up truthfully.
- 21 Nov: clinic flow works in AT simulator, else drop all UI polish until it does.
- 25 Nov: both specs compile deterministically end to end; UI is skin over working core.
- 29 Nov: public deployment answers AT callbacks.
- 1 Dec: freeze.

## Minimum winning slice
OpenAPI + MCP ingest -> IR -> state machine -> validators + PBT green -> AT callback runtime + emulator -> SMS fallback on a real handset -> Kiro headless annotation step with committed evidence -> state-graph + validation console -> clinic demo then live farmer-prices compile -> public URL, repo with `.kiro/`, video.
