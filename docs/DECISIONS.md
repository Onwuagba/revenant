# Revenant: decisions (ADR log)

Format: decision, why, rejected alternative, revisit trigger.

**ADR-001 Compile-time LLM only; runtime deterministic.** Per-screen latency budget is carrier-bound and an LLM adds cost, latency and variance. Rejected: LLM per screen. Revisit: never for the demo.

**ADR-002 Kiro headless is the annotation stage, validator is the gate.** Makes Kiro a real runtime-of-compile step without trusting it. Agent calls the validator through MCP, then our pipeline re-validates. Rejected: Kiro writes the state machine directly (unverifiable, injectable). Fallback: deterministic annotator so the product works without Kiro. Revisit: if U1 fails, local runs + cached results (honestly labelled).

**ADR-003 Replay-from-text plus session cache.** AT sends cumulative `text`; a deterministic machine can always rebuild state. Rejected: Redis-only session state (extra service, no extra guarantee).

**ADR-004 Postgres only (queue, cache, sessions).** `SKIP LOCKED` job table and TTL cache table suffice at demo scale. Rejected: Redis/Celery (author knows Celery; still more ops for no demo gain). Redis stays optional/never.

**ADR-005 Own `$ref` resolver and SSRF policy.** Library resolvers fetch remote refs by default. Rejected: prance default behaviour.

**ADR-006 Skeleton Crew: build for it, decide at submission.** Emitter outputs two self-contained folders (`generated/clinic-booking`, `generated/farmer-prices`), each with vendored runtime, Dockerfile, bundle; costs ~0.5 day because the emitter is needed for "download bundle" anyway. Does not alter compiler quality. Category pick on 1 Dec after re-reading rules (U10): default Resurrection; switch if rules and write-up fit Skeleton Crew better. A project wins one overall OR one category.

**ADR-007 Supported subset is small and documented.** Enums, booleans, bounded numbers, short tokens, date windows, PIN, dynamic choices, flat objects. Everything else refused with codes. Honest scope beats "compiles any API" (judge feedback).

**ADR-008 Bounded free-text interpretation is optional, default off.** Deterministic fuzzy match first; LLM, if enabled, returns only a candidate id or NONE under 2 s. Cut-list item; runtime never requires it.

**ADR-009 Screen budget measured on full response string incl. `CON `/`END `, GSM-7 only.** 182 is documented lineage; operators differ (Clickatell suggests 160); AT enforcement unknown (U4/U7). Configurable profiles `standard=182`, `conservative=160`. Probe on Day 1 and record result here.

**ADR-010 Navigation keys: `0` back, `00` home; numbered items 1-9 with `8 More` only on paginated menus.** Common convention, consistent, validator-checkable. Inputs containing `*`/`#` invalid.

**ADR-011 PIN is last input, then END.** Limits exposure in AT's cumulative `text` and in carrier logs to one callback; also simplifies the validator. Costs: no PIN-then-continue flows (documented limit).

**ADR-012 MCP stdio only for bundled samples; streamable HTTP for user URLs.** Prevents RCE; samples run as HTTP services in compose.

**ADR-013 Real-handset strategy.** Real SMS on a feature phone (AT live, else GSM modem/Android gateway behind `SmsProvider`). USSD on handset requires a leased shortcode (U6): assumed unavailable; USSD shown in AT simulator + emulator, labelled. Rejected: local GSM test network (SDR + BTS): legal and time risk, and it would demo a network, not the product.

**ADR-014 Console auth: cookie sessions, not JWT.** Server-side revocation, simple CSRF story. Judges get a seeded read-only viewer plus public emulator.

**ADR-015 Frontend: React + TS + Vite, React Flow for the graph.** Graph is the hero visual; hand-rolled SVG rejected for time. Theme tokens in CSS variables, dark only (theme is the identity); contrast checked.

**ADR-016 Hosting: single VPS with Docker Compose + Caddy.** No free-tier price assumptions. Must remain up to 29 Jan 2027.

**ADR-017 Annotator output cached by `(spec_hash, agent_version)`.** Saves Kiro credits (Free tier 50, Pro 1,000 per search results, secondary source) and makes demos repeatable; UI shows cached vs fresh.

**ADR-018 Public API names the stages Exhume/Reanimate/Last Rites/Rise only in UI.** API and code use neutral names (`ingest`, `annotate`, `validate`, `deploy`) so docs and tests stay readable.
