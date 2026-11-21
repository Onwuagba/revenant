"""V3 Back navigation: 0 leads to previous state, 00 reaches ROOT."""

from __future__ import annotations

from ..planner import TERMINAL_KINDS, Machine, StateKind
from . import ValidationResult, Violation


def validate_back(machine: Machine) -> ValidationResult:
    """V3: check 0 and 00 transitions on every non-root INPUT/MENU/CONFIRM/PIN state."""
    violations: list[Violation] = []

    for sid in sorted(machine.states):
        state = machine.states[sid]
        if sid == machine.root:
            continue
        if state.kind in TERMINAL_KINDS or state.kind == StateKind.ACTION:
            continue

        # 00 must reach root
        if state.transitions.get("00") != machine.root:
            violations.append(
                Violation(
                    validator="V3_back",
                    state_id=sid,
                    message=f"State {sid}: 00 does not lead to ROOT",
                )
            )

        # 0 must lead to prev (if prev is set)
        if state.prev:
            if state.transitions.get("0") != state.prev:
                violations.append(
                    Violation(
                        validator="V3_back",
                        state_id=sid,
                        message=f"State {sid}: 0 does not lead to previous state {state.prev}",
                    )
                )

        # Back must not loop to self
        if state.transitions.get("0") == sid:
            violations.append(
                Violation(
                    validator="V3_back", state_id=sid, message=f"State {sid}: 0 loops to self"
                )
            )

    return ValidationResult("V3_back", len(violations) == 0, violations)
