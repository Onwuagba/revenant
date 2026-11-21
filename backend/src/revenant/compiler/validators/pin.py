"""V6 PIN safety: PIN state followed only by ACTION then terminal;
PIN value never reaches a screen slot or stored param."""

from __future__ import annotations

from ..planner import TERMINAL_KINDS, Machine, StateKind
from . import ValidationResult, Violation


def validate_pin(machine: Machine) -> ValidationResult:
    """V6: check PIN states are followed only by ACTION then terminal."""
    violations: list[Violation] = []

    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.kind != StateKind.PIN:
            continue

        # PIN must transition to exactly one ACTION state (via *)
        targets = set(state.transitions.values())
        action_targets = {
            t
            for t in targets
            if machine.states.get(t) and machine.states[t].kind == StateKind.ACTION
        }

        if not action_targets:
            violations.append(
                Violation(
                    validator="V6_pin",
                    state_id=sid,
                    message=f"PIN state {sid} is not followed by an ACTION state",
                )
            )

        # ACTION must be followed by a terminal state
        for at in action_targets:
            action = machine.states.get(at)
            if action:
                action_targets2 = set(action.transitions.values())
                terminal_targets = {
                    t
                    for t in action_targets2
                    if machine.states.get(t) and machine.states[t].kind in TERMINAL_KINDS
                }
                if not terminal_targets:
                    violations.append(
                        Violation(
                            validator="V6_pin",
                            state_id=at,
                            message=f"ACTION state {at} after PIN is not followed by a "
                            "terminal state",
                        )
                    )

        # PIN must not have any slots (PIN value never rendered)
        if state.slots:
            violations.append(
                Violation(
                    validator="V6_pin",
                    state_id=sid,
                    message=f"PIN state {sid} has slots — PIN value could be rendered",
                )
            )

        # PIN template must not contain a slot placeholder
        if state.template and "{" in state.template:
            violations.append(
                Violation(
                    validator="V6_pin",
                    state_id=sid,
                    message=f"PIN state {sid} template contains a slot placeholder",
                )
            )

    return ValidationResult("V6_pin", len(violations) == 0, violations)
