"""V2 Exit paths: every state must have a path to a terminal state;
invalid-input retries must be bounded."""

from __future__ import annotations

from ..planner import TERMINAL_KINDS, Machine
from . import ValidationResult, Violation


def validate_exits(machine: Machine) -> ValidationResult:
    """V2: report states with no path to a terminal, and unbounded retries."""
    violations: list[Violation] = []
    terminals = {sid for sid, s in machine.states.items() if s.kind in TERMINAL_KINDS}

    if not terminals:
        violations.append(Violation(validator="V2_exits", message="No terminal states exist"))
        return ValidationResult("V2_exits", False, violations)

    can_reach_terminal = _reachability_to_set(machine, terminals)

    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.kind in TERMINAL_KINDS:
            continue
        # ACTION states are checked too: V3 forces every screen state to have 00 -> ROOT, so
        # an ACTION with no way on is the only place a session can get stuck.
        if sid not in can_reach_terminal:
            violations.append(
                Violation(
                    validator="V2_exits",
                    state_id=sid,
                    message=f"State {sid} has no path to a terminal state",
                )
            )

    # Check retry bound
    if machine.max_retries > 10:
        violations.append(
            Violation(
                validator="V2_exits",
                message=f"Retry limit {machine.max_retries} is unreasonably high",
            )
        )

    return ValidationResult("V2_exits", len(violations) == 0, violations)


def _reachability_to_set(machine: Machine, targets: set[str]) -> set[str]:
    """Return states that can reach any of *targets* (reverse BFS)."""
    # Build reverse adjacency
    reverse: dict[str, set[str]] = {sid: set() for sid in machine.states}
    for sid, state in machine.states.items():
        for dest in state.transitions.values():
            if dest in reverse:
                reverse[dest].add(sid)

    visited = set(targets)
    queue = list(targets)
    while queue:
        sid = queue.pop(0)
        for pred in reverse.get(sid, set()):
            if pred not in visited:
                visited.add(pred)
                queue.append(pred)
    return visited
