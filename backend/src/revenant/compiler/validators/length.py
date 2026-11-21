"""V5 Length and charset: worst_case <= max_chars, GSM-7 only, no control chars."""

from __future__ import annotations

from ..gsm7 import is_gsm7, strip_control_chars
from ..planner import SCREEN_KINDS, Machine
from . import ValidationResult, Violation


def validate_length(machine: Machine) -> ValidationResult:
    """V5: check every screen's worst-case length, charset, and control chars."""
    violations: list[Violation] = []
    max_chars = machine.carrier_profile.max_chars

    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.kind not in SCREEN_KINDS:
            continue

        # Worst-case length check
        if state.worst_case_len > max_chars:
            violations.append(
                Violation(
                    validator="V5_length",
                    state_id=sid,
                    message=f"State {sid}: worst_case_len {state.worst_case_len} > "
                    f"max_chars {max_chars}",
                    measured=state.worst_case_len,
                )
            )

        # GSM-7 charset check on template
        if state.template and not is_gsm7(state.template):
            violations.append(
                Violation(
                    validator="V5_length",
                    state_id=sid,
                    message=f"State {sid}: template contains non-GSM-7 characters",
                )
            )

        # Control characters check (except newlines)
        if state.template:
            stripped = strip_control_chars(state.template)
            if stripped != state.template.replace("\n", "\n"):
                # Check for actual control chars (not newlines)
                for ch in state.template:
                    if ord(ch) < 0x20 and ch != "\n":
                        violations.append(
                            Violation(
                                validator="V5_length",
                                state_id=sid,
                                message=f"State {sid}: template contains control character "
                                f"U+{ord(ch):04X}",
                            )
                        )
                        break

    return ValidationResult("V5_length", len(violations) == 0, violations)
