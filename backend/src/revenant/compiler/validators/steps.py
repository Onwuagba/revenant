"""V4 Step limit: longest shortest path from ROOT to any terminal <= max_steps."""

from __future__ import annotations

from collections import deque

from ..planner import TERMINAL_KINDS, Machine
from . import ValidationResult, Violation


def validate_steps(machine: Machine) -> ValidationResult:
    """V4: report if the longest shortest path exceeds max_steps."""
    violations: list[Violation] = []
    max_steps = machine.carrier_profile.max_steps

    # BFS from root, computing shortest distance to each state
    dist: dict[str, int] = {machine.root: 0}
    queue: deque[str] = deque([machine.root])

    while queue:
        sid = queue.popleft()
        state = machine.states.get(sid)
        if state is None:
            continue
        for dest in state.transitions.values():
            if dest in machine.states and dest not in dist:
                dist[dest] = dist[sid] + 1
                queue.append(dest)

    # Find longest shortest path to a terminal
    longest = 0
    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.kind in TERMINAL_KINDS and sid in dist:
            longest = max(longest, dist[sid])

    if longest > max_steps:
        violations.append(
            Violation(
                validator="V4_steps",
                message=f"Longest path to terminal is {longest}, exceeds max_steps {max_steps}",
                measured=longest,
            )
        )

    return ValidationResult("V4_steps", len(violations) == 0, violations)
