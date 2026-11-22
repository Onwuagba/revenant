"""V7 SMS fallback (state-machine-validators requirement 3.7, runtime 5.4, property P11).

For every compiled operation, build the longest result text the runtime can send (via the shared
formatter in ``compiler/results.py``) and check it:

- every declared result field has a bound and a list result has ``maxItems``;
- the worst case fits ``carrier_profile.sms_segments`` (160 septets single, 153 concatenated);
- every declared result field appears in it (lossless).

Text-shaped results (no declared fields) are cut to the budget at runtime with ``...``; that is
the documented lossy path and is not a violation.
"""

from __future__ import annotations

from typing import Any

from ..ir import Operation
from ..planner import Machine, StateKind
from ..results import check_operation
from . import ValidationResult, Violation

SINGLE_SEGMENT = 160
CONCAT_SEGMENT = 153


def validate_sms(machine: Machine, ir_ops: list[Any] | None = None) -> ValidationResult:
    """V7: worst-case SMS per operation within the segment budget and lossless."""
    violations: list[Violation] = []
    segments = machine.carrier_profile.sms_segments
    ops = [o if isinstance(o, Operation) else Operation.model_validate(o) for o in ir_ops or []]
    result_states = {
        s.op_id: sid
        for sid, s in machine.states.items()
        if s.kind in (StateKind.RESULT_END, StateKind.SMS_END) and s.op_id
    }
    for op in sorted(ops, key=lambda o: o.id):
        if op.id in machine.refused_op_ids:
            continue
        for message, measured in check_operation(op, segments):
            violations.append(
                Violation(
                    validator="V7_sms",
                    state_id=result_states.get(op.id, op.id),
                    message=f"{op.id}: {message}",
                    measured=measured,
                )
            )
    # A screen result that does not fit must have been turned into SMS_END by the renderer.
    max_chars = machine.carrier_profile.max_chars
    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.kind == StateKind.RESULT_END and state.worst_case_len > max_chars:
            violations.append(
                Violation(
                    validator="V7_sms",
                    state_id=sid,
                    message=f"RESULT_END state {sid} exceeds the screen budget but was not "
                    "converted to SMS_END",
                    measured=state.worst_case_len,
                )
            )
    return ValidationResult("V7_sms", len(violations) == 0, violations)


def check_sms_budget(body: str, max_segments: int) -> tuple[bool, int]:
    """Check if an SMS body fits within the segment budget. Returns (fits, segment_count)."""
    from ..results import segment_count

    segments = segment_count(body)
    return segments <= max_segments, segments
