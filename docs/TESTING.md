# Revenant: Testing strategy

Evidence wording: tests give "behavioural evidence against stated invariants". Report Hypothesis seed, `max_examples`, and generator coverage as measured. No numbers are claimed before they are produced by a run.

## 1. Layers
| Layer | Tooling | Scope |
|---|---|---|
| Unit | pytest | classifier, refusals, gsm7, renderer, redaction, URL guard |
| Property-based (marker `pbt`) | Hypothesis | compiler and runtime invariants (section 2) |
| Stateful PBT | Hypothesis `RuleBasedStateMachine` | random key presses against a compiled bundle |
| Integration | pytest + httpx + Postgres container | AT-shaped callbacks, upstream mocks, SMS outbox, dedupe, lockout |
| Contract | recorded AT payload fixtures | form parsing, `CON/END` format |
| Corpus | vendored real OpenAPI specs (licence checked) | compile never crashes; refusal report measured, not assumed |
| Adversarial | fixtures | prompt-injection spec, SSRF refs, YAML bomb, canary PIN |
| E2E | Playwright | upload sample, compile (deterministic annotator), graph renders, emulator books appointment |
| Kiro smoke | `scripts/kiro_smoke.sh` (needs key) | headless run produces schema-valid annotations; skipped in CI without key, transcript committed |
| Manual device | checklist | AT simulator run, real handset SMS receipt |

## 2. Hypothesis properties (compiler invariants)
Generators: `st_operation()` builds OpenAPI operations and MCP tools from schema strategies, in-subset and out-of-subset; `st_label()` produces adversarial text (long, emoji, non-GSM-7, control chars, `CON `, `*`, `#`); `st_slot_fill()` fills dynamic slots with worst-case strings; `st_app()` composes 1-12 operations.

| ID | Property |
|---|---|
| P1 | Every rendered screen under any slot fill: `len(prefix+body) <= max_chars`, GSM-7 only, no control chars |
| P2 | Every state reachable from ROOT |
| P3 | Every state has a path to a terminal state; no dead end; invalid-input retries are bounded (3) |
| P4 | Back: from any non-root INPUT/MENU state, `0` leads to the previous state and collected params before it are preserved; `00` reaches ROOT |
| P5 | Longest shortest path from ROOT to any terminal <= `max_steps`; random key walks terminate within `max_steps + retries` |
| P6 | Determinism: compile twice gives identical `bundle_hash`; invariant under operation order permutation and JSON key order |
| P7 | Totality: any JSON Schema either maps to a supported Param or yields a Refusal with a known code; never raises |
| P8 | Replay equivalence: stateful session output equals output rebuilt from cumulative `text` |
| P9 | PIN: no screen, event, log record, or DB row contains the PIN canary; PIN state precedes only ACTION then terminal |
| P10 | Pagination: concatenated pages contain every item exactly once; each page within budget |
| P11 | SMS fallback: body GSM-7, segments <= budget, contains all declared result fields (lossless) or compile refuses with `R_...` |
| P12 | Idempotence of merge: applying annotations twice equals once; annotations cannot add transitions or operations |
| P13 | Refusal soundness: refused ops never appear in machine or screens |

Validator self-test (guards against vacuous validators): mutation fixtures take a valid bundle and break one thing (delete edge, orphan state, 200-char label, PIN with echo slot, back loop to self, add 12-step chain). Each mutation must be flagged by exactly the intended validator.

Profiles: `dev` (50 examples, fast, runs on file save via hook), `ci` (200 examples, derandomised seed printed), `deep` (nightly/manual, higher). Failures keep the Hypothesis example database in `.hypothesis/` (gitignored except committed regressions in `tests/pbt/regressions/`).

## 3. Runtime and integration cases (examples)
- AT callback happy path for both demo apps; `text=""`, `"1"`, `"1*2*3"`, back sequences, `"1*0*1"`.
- Duplicate callback returns stored response, one upstream call (T4).
- Upstream timeout at 3 s yields SMS path and `END` text; job sent.
- Wrong token 404; malformed form 200 with `END` generic error (never stack trace).
- Lockout after 3 bad PINs; message identical to bad-PIN message.
- No-LLM runtime: run integration suite with all LLM env vars unset; must pass.
- Kiro failure injection: exit code non-zero, invalid JSON, schema violation, timeout -> deterministic fallback recorded, bundle still verifies.

## 4. Kiro-specific verification
- Annotation schema test: reject unknown keys, over-length labels.
- Adversarial spec (T8) through the real headless path once; transcript stored in `.kiro/evidence/`.
- Hooks documented with a screenshot/log of at least one firing.

## 5. Real-world corpus honesty
Compile N public specs; publish per-spec table: operations total, compiled, refused by code. Expect many refusals; that is the product being truthful. Do not report a single "coverage %" headline without the table.

## 6. CI gates
ruff, mypy (strict on compiler/runtime), pytest unit+pbt(ci), integration (service containers), frontend typecheck + build, Playwright smoke, secret scan, dependency audit, `revenant verify generated/*`. Merge to main only when green; record run URLs for the write-up.

## 7. Manual acceptance (before video)
1. Probe screens 160/182/183 in AT simulator (U4/U7). 2. Dial both apps in simulator. 3. Emulator matches simulator output. 4. SMS received on real handset. 5. Canary PIN grep clean. 6. Kill Kiro key: compile still succeeds deterministically.

## Recorded `ci` profile run (2026-11-15)
Command: `pytest -m pbt --hypothesis-profile=ci -q --hypothesis-show-statistics`
Result: **24 passed, 241 deselected** in 62 s.
Caveat, stated plainly: most property tests set their own `@settings(max_examples=N)` (observed values 20, 30, 40, 50),
which overrides the profile's example count. So this run did **not** execute 200 examples per property; each ran the
count in its own decorator. Raising or removing those per-test overrides is an open item. The `ci` profile is derandomised,
so no random seed is printed.
