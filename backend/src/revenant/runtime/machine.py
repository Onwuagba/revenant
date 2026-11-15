"""Pure machine step and replay — no I/O, no LLM (steering tech.md rule 1).

``step(bundle, state_id, key)`` advances the state machine by one input.
``replay(bundle, text)`` rebuilds state from cumulative ``text`` split on ``*``.

Replay equivalence (P8): stateful session output equals output rebuilt from
cumulative text.
"""

from __future__ import annotations

from typing import Any

from ..compiler.planner import StateKind, TERMINAL_KINDS

#: Prefix lengths
CON_PREFIX = "CON "
END_PREFIX = "END "


def step(
    machine_data: dict[str, Any],
    state_id: str,
    key: str,
) -> tuple[str, str]:
    """Advance the machine one step. Returns (next_state_id, response_prefix).

    The response_prefix is either ``CON `` or ``END `` — the caller adds the
    screen template. Returns the same state_id if the key is invalid (retry).
    """
    states = machine_data["states"]
    state = states.get(state_id)
    if state is None:
        return "error_end", END_PREFIX

    # Terminal states: no transitions
    if state["kind"] in (k.value for k in TERMINAL_KINDS):
        return state_id, END_PREFIX

    transitions = state.get("transitions", {})

    # Check if the key is valid
    if key in transitions:
        next_id = transitions[key]
        next_state = states.get(next_id)
        if next_state is None:
            return "error_end", END_PREFIX
        if next_state["kind"] in (k.value for k in TERMINAL_KINDS):
            return next_id, END_PREFIX
        return next_id, CON_PREFIX

    # Special keys
    if key in ("0", "00") and key in transitions:
        next_id = transitions[key]
        return next_id, CON_PREFIX

    # Invalid key — stay on same state (retry)
    return state_id, CON_PREFIX


def get_screen(machine_data: dict[str, Any], state_id: str) -> str:
    """Return the template for a state (the screen body without prefix)."""
    states = machine_data["states"]
    state = states.get(state_id)
    if state is None:
        return "Session ended. Try again later."
    return state.get("template", "")


def is_terminal(machine_data: dict[str, Any], state_id: str) -> bool:
    """Return True if the state is terminal."""
    state = machine_data["states"].get(state_id)
    if state is None:
        return True
    return state["kind"] in (k.value for k in TERMINAL_KINDS)


def replay(
    machine_data: dict[str, Any],
    text: str,
) -> tuple[str, int]:
    """Rebuild the machine state from cumulative ``text`` split on ``*``.

    Returns (state_id, invalid_count). Starts from root and applies each
    segment as a key press. Invalid keys increment the count but stay on the
    same state (retry mechanism).
    """
    root = machine_data["root"]
    if not text:
        return root, 0

    segments = text.split("*")
    current = root
    invalid_count = 0

    for segment in segments:
        if not segment:
            continue
        # Reject inputs containing * or # (AT separators/terminators)
        if "*" in segment or "#" in segment:
            invalid_count += 1
            continue

        next_id, _ = step(machine_data, current, segment)
        if next_id == current:
            invalid_count += 1
        else:
            current = next_id

    return current, invalid_count


def render_response(
    machine_data: dict[str, Any],
    state_id: str,
    prefix: str,
) -> str:
    """Render the full response: prefix + screen template."""
    template = get_screen(machine_data, state_id)
    return f"{prefix}{template}"
