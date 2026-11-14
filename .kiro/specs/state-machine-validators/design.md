# Design: planner, renderer, validators

## Components (`backend/src/revenant/compiler/`)
- `planner.py`: IR -> `machine.json`. Pure and deterministic. Helper to compute shortest paths from ROOT.
- `render.py`: machine + IR -> `screens.json` with templates, slot budgets and worst-case lengths. Carrier profile (`standard=182`, `conservative=160`) is an input, never a constant in logic.
- `gsm7.py`: transliteration table, `is_gsm7`, `sanitise_slot`, septet counting (including extension table characters costing 2).
- `validators/`: one module per validator (`reachability.py`, `exits.py`, `back.py`, `steps.py`, `length.py`, `pin.py`, `sms.py`, plus refusal soundness) and `run_all(bundle) -> list[ValidationResult]`.
- `emit.py` later assembles `bundle.json` and `bundle_hash` (sha256 of canonical JSON).

## Data flow
`ir.json` -> planner -> `machine.json` -> renderer -> `screens.json` -> validators -> `report.json` -> bundle.

## Error handling
Validators never raise on a malformed bundle; they report violations. Planner refuses (typed error) only for programmer errors.

## Testing strategy
Unit tests per module; mutation self-tests; Hypothesis P1-P6, P10 with generators `st_operation`, `st_label`, `st_slot_fill`, `st_app` (1-12 ops). Profiles dev/ci/deep.

## Correctness properties (verbatim from docs/TESTING.md)
| ID | Property |
|---|---|
| P1 | Every rendered screen under any slot fill: `len(prefix+body) <= max_chars`, GSM-7 only, no control chars |
| P2 | Every state reachable from ROOT |
| P3 | Every state has a path to a terminal state; no dead end; invalid-input retries are bounded (3) |
| P4 | Back: from any non-root INPUT/MENU state, `0` leads to the previous state and collected params before it are preserved; `00` reaches ROOT |
| P5 | Longest shortest path from ROOT to any terminal <= `max_steps`; random key walks terminate within `max_steps + retries` |
| P6 | Determinism: compile twice gives identical `bundle_hash`; invariant under operation order permutation and JSON key order |
| P10 | Pagination: concatenated pages contain every item exactly once; each page within budget |
(P13 refusal soundness is stated in the ir-type-subset spec and extended here at task 12.)
