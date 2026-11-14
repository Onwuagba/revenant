# Design: IR and type subset

## Overview
Pure-Python, side-effect-free modules under `backend/src/revenant/compiler/`: `ir.py` (Pydantic v2 models, canonical dump), `subset.py` (classifier), `refusals.py` (code enum, Refusal model). No I/O, no network, no LLM.

## Components
- `ir.py`: `App`, `Operation`, `Param`, `Result`, `Flow`, `Refusal`; `canonical_json(obj) -> bytes` (sorted keys, stable ordering, no floats formatting surprises).
- `refusals.py`: `RefusalCode` string enum with exactly the 12 codes; `Refusal` model.
- `subset.py`: `classify_schema(schema, *, op_id, path, depth_limit) -> Param | Refusal` and `classify_operation(...) -> Operation | list[Refusal]`. Total function: wraps traversal with a depth cap and cycle detection (`R_RECURSIVE`); unknown constructs map to the nearest refusal code, never an exception.

## Data flow
`draft operation (from ingest)` -> `classify_operation` -> `Operation` (kept) or `Refusal[]` (reported). Dynamic option links and annotations are applied later by the merge step, not here.

## Error handling
Classifier returns values, never raises. Model validation errors are raised only for programmer errors (constructing an IR with over-long labels).

## Testing strategy
Unit tests per subset row and per refusal code; PBT for totality and refusal soundness. Generators in `tests/pbt/strategies.py`.

## Correctness properties (verbatim from docs/TESTING.md)
| ID | Property |
|---|---|
| P7 | Totality: any JSON Schema either maps to a supported Param or yields a Refusal with a known code; never raises |
| P13 | Refusal soundness: refused ops never appear in machine or screens |

(P6 determinism also depends on `canonical_json`; it is owned by the state-machine-validators spec.)
