---
inclusion: fileMatch
fileMatchPattern: ["tests/**", "backend/src/revenant/mcp_validator/**"]
---
# Testing conventions (docs/TESTING.md)

- Evidence wording: "behavioural evidence against stated invariants". Report the Hypothesis seed, `max_examples`, and generator coverage exactly as measured. Write no numbers before a run produces them.
- Markers: `@pytest.mark.pbt` on all Hypothesis property tests; `integration`, `e2e` as needed.
- Profiles: `dev` = 50 examples (fast, used by the on-save hook), `ci` = 200 examples with derandomised seed printed, `deep` = nightly/manual. Register them in `tests/conftest.py`.
- Hypothesis example DB in `.hypothesis/` is gitignored; committed regressions go in `tests/pbt/regressions/`.
- Generators: `st_operation()`, `st_label()` (adversarial: long, emoji, non-GSM-7, control chars, `CON `, `*`, `#`), `st_slot_fill()` (worst-case strings), `st_app()` (1-12 ops). Put them in `tests/pbt/strategies.py` once and reuse.
- One test per property ID, named `test_P<n>_<short_name>`, with the property text from TESTING.md in the docstring.
- Validator self-test: mutation fixtures break exactly one thing (delete edge, orphan state, 200-char label, PIN with echo slot, back loop to self, 12-step chain); each must be flagged by exactly the intended validator. This guards against vacuous validators.
- Never weaken a validator or loosen a property to make a test pass. If a property fails, report the counterexample and fix the code (or open a question about the requirement).
- Integration: Postgres container, AT-shaped form callbacks, upstream mocks. Run once with all LLM env vars unset.
- Kiro failure injection: non-zero exit, invalid JSON, schema violation, timeout -> deterministic fallback recorded and bundle still verifies.
