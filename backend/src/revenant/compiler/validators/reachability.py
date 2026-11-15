"""V1 Reachability: every state must be reachable from ROOT."""

from __future__ import annotations

from ..planner import Machine, StateKind
from . import ValidationResult, Violation


def validate_reachability(machine: Machine) -> ValidationResult:
    """V1: report any state not reachable from ROOT.

    ERROR_END is implicitly reachable from any non-terminal state via the
    retry mechanism (3 invalid inputs), so it is excluded from the check.
    """
    violations: list[Violation] = []
    reachable = _bfs(machine)

    for sid in sorted(machine.states):
        # ERROR_END is implicitly reachable via retries
        if machine.states[sid].kind == StateKind.ERROR_END:
            continue
        if sid not in reachable:
            violations.append(Violation(
                validator="V1_reachability", state_id=sid,
                message=f"State {sid} is not reachable from ROOT",
            ))

    return ValidationResult(
        validator="V1_reachability",
        passed=len(violations) == 0,
        violations=violations,
    )


def _bfs(machine: Machine) -> set[str]:
    """Breadth-first search from root, returning all reachable state ids."""
    visited: set[str] = set()
    queue = [machine.root]
    visited.add(machine.root)

    while queue:
        sid = queue.pop(0)
        state = machine.states.get(sid)
        if state is None:
            continue
        for dest in state.transitions.values():
            if dest not in visited and dest in machine.states:
                visited.add(dest)
                queue.append(dest)

    return visited
