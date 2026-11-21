"""V8 Refusal soundness: refused ops never appear in machine or screens."""

from __future__ import annotations

from ..planner import Machine
from . import ValidationResult, Violation


def validate_refusal_soundness(machine: Machine, refused_op_ids: set[str]) -> ValidationResult:
    """V8: report any refused operation that appears in the machine."""
    violations: list[Violation] = []

    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.op_id and state.op_id in refused_op_ids:
            violations.append(
                Violation(
                    validator="V8_refusal_soundness",
                    state_id=sid,
                    message=f"State {sid} belongs to refused operation {state.op_id}",
                )
            )

    # Also check the machine's own refused_op_ids field for consistency
    for op_id in machine.refused_op_ids:
        for sid in sorted(machine.states):
            state = machine.states[sid]
            if state.op_id == op_id:
                violations.append(
                    Violation(
                        validator="V8_refusal_soundness",
                        state_id=sid,
                        message=f"State {sid} belongs to refused operation {op_id}",
                    )
                )

    return ValidationResult("V8_refusal_soundness", len(violations) == 0, violations)
