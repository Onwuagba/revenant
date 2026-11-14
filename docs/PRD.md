# Revenant: PRD

Status: design, 2026-11-14. Target: Kiroween 2026, deadline 4 Dec 2026 14:00 PT (23:00 WAT). Plan to submit 3 Dec.

## 1. One line
Revenant compiles an OpenAPI spec or MCP server into a verified USSD + SMS app for feature phones. Carrier constraints are machine-checked before anything deploys. Unsupported shapes are refused with a reason, not guessed.

## 2. Problem and users
New services (APIs, MCP tools) assume a smartphone. Feature-phone and data-rationed users reach services over USSD, where a screen is ~182 characters and a session is short (Kenyan telcos: 180 s total, 30-60 s per reply; see PLATFORM_FACTS). Hand-building these flows is slow and breaks silently (screen overflow, dead ends, no back).

Primary user: **developer** at a fintech, NGO, public-service or agritech team who already has an API or MCP server. Secondary: **end user** on a feature phone; **judge** evaluating via emulator and video.

## 3. Positioning (developer infrastructure)
| Product | Category (per selection doc, not independently verified) | Revenant difference |
|---|---|---|
| BlueKai (2025 winner) | client-style app | Revenant is a compiler + verifier, not a client |
| Buni AI, USSDly | generate USSD from prompts | Input is a machine contract (OpenAPI/MCP); output is validated, deterministic, and runs with no LLM |
| Telerivet, RapidPro | visual flow builders | No hand-drawn flows; flows are derived and then checked |

Claim boundary (SHARED_STANDARDS): "behavioural evidence", "verified against stated invariants", never "proof", never "compiles any API". Supported subset is documented in `architecture/IR_AND_TYPE_SUBSET.md`.

## 4. Goals / non-goals
Goals (must ship):
1. Real ingestion of OpenAPI 3.0/3.1 and MCP (tools/list over streamable HTTP) into one IR.
2. IR to navigable USSD state machine with precomputed screens.
3. Validators: reachability, exit paths, back-navigation, session step limit, screen length + GSM-7 charset, PIN safety, SMS fallback sizing. Each produces a machine-readable result.
4. Documented type subset; graceful refusal (nested objects, `date-time`, free text, polymorphism) shown in the console as a "Buried" report.
5. SMS fallback for long or slow results.
6. Runtime with no LLM, serving Africa's Talking USSD callbacks (sandbox) and an in-browser feature-phone emulator.
7. Kiro CLI headless as a real compile step (annotation stage), with schema-validated output and deterministic fallback.
8. Hypothesis PBT over compiler and runtime invariants.
9. Demo: clinic booking, then live compile of a farmer-prices MCP.

Non-goals: arbitrary-API compilation; per-user OAuth flows; payments processing; multi-tenant billing; production shortcode leasing; non-GSM-7 scripts; Redis; mobile app.

Optional (cut list): bounded free-text interpretation (ADR-008), local-language copy pack, Skeleton Crew entry.

## 5. User stories and acceptance criteria
| ID | Story | Acceptance |
|---|---|---|
| US1 | As a developer I upload an OpenAPI file or give an MCP URL and get a compile report. | Report lists compiled operations, refused operations with reason codes, validator results, annotator used (kiro-cli or deterministic). |
| US2 | I see the state graph and each screen with its character count. | Graph renders from bundle; every screen shows count/182; worst-case count for dynamic slots shown. |
| US3 | A spec element outside the subset never crashes the compiler. | Fuzzed schemas yield supported or refused-with-code (PBT P7). |
| US4 | I deploy to the AT sandbox and dial the code. | Callback returns `CON`/`END` text within 3 s for the demo flows; screens identical to emulator. |
| US5 | A long result arrives by SMS. | USSD shows `END` with "sent by SMS"; SMS text contains the full result, split into <=N segments or refused at compile time. |
| US6 | End user can go back, exit, retry. | `0` back, `00` home, invalid input re-prompts max 3 times then ends; verified by validators and PBT. |
| US7 | PINs are never echoed, logged or stored. | PIN state is last input; no log/DB row contains PIN digits (test with canary PIN). |
| US8 | An upstream spec change re-verifies. | Hook/CLI `revenant verify` diffs IR hash and re-runs validators; CI exits non-zero on violation. |
| US9 | A judge can try it without an account. | `/emulator` public with sample projects read-only; `/judges` page explains. |

## 6. Success metrics (demo-scope; no invented targets)
- Two specs (OpenAPI clinic, MCP farmer-prices) compile end to end live in under the 3-minute video, with the Kiro headless stage visible in the log.
- Validator and PBT suites green in CI; counts reported as measured, with the Hypothesis seed and example counts printed.
- Refusal report shown for at least one deliberately unsupported operation per spec.

## 7. Device and demo constraint
Kiroween requires the video to show the app on its intended device and the sponsor may demand hardware. Plan (PLATFORM_FACTS U5/U6): real feature-phone handset receives the SMS fallback and confirmation; USSD shown in AT simulator and our emulator, labelled "simulated handset" on screen; document that live USSD on a handset needs a leased shortcode. Keep the handset and SIM available for a sponsor request.

## 8. Category
Primary: **Resurrection** (feature-phone channel revived for the agent/API era; theme "GSM rising from the grave"). Skeleton Crew evaluated (ADR-006): the emitter produces two self-contained generated apps in `generated/clinic-booking/` and `generated/farmer-prices/`; cost is small because the emitter exists anyway. Choose the category on 1 Dec after re-reading rules (U10). A project wins one overall OR one category.

## 9. Theming ("GSM rising from the grave")
Console = "The Crypt". Pipeline stages are named Exhume (ingest), Reanimate (annotate/compile), Last Rites (validate), Rise (deploy). Refused operations are tombstones ("Buried: nested object at /body/address"). Signal-bars motif doubles as validation health. Phosphor-green on near-black, monospace screens at 182-char width with a live counter. Colour is never the only status signal (icon + text).

## 10. Risks (top)
See `docs/DECISIONS.md` and RISK_REGISTER. Revenant-specific: Kiro headless access (U1), no real-handset USSD (U6), scope vs 19 days, Kiro-in-compile looking decorative (mitigated by validator-in-the-loop via MCP and evidence transcripts).
