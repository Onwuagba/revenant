"""Pure machine step and replay — no I/O, no LLM (steering tech.md rule 1).

``step(bundle, state_id, key)`` advances the state machine by one input.
``replay(bundle, text)`` rebuilds state from cumulative ``text`` split on ``*``.

Replay equivalence (P8): stateful session output equals output rebuilt from
cumulative text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
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

    # Wildcard: free input (INPUT / PIN states) accepts anything except the
    # global navigation keys 0 and 00.
    if "*" in transitions and key not in ("0", "00") and key != "":
        next_id = transitions["*"]
        next_state = states.get(next_id)
        if next_state is None:
            return "error_end", END_PREFIX
        if next_state["kind"] in (k.value for k in TERMINAL_KINDS):
            return next_id, END_PREFIX
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


#: Default max length for a free-text value when the IR gives none.
DEFAULT_MAX_INPUT = 20


def _menu_value(state: dict[str, Any], key: str, today: date | None) -> str:
    """Map a menu key press to the option value (enum value, bool, ISO date)."""
    opts = state.get("options") or []
    if not key.isdigit() or not (1 <= int(key) <= len(opts)):
        return key
    val = opts[int(key) - 1]
    if val.startswith("+") and val[1:].isdigit():
        return ((today or date.today()) + timedelta(days=int(val[1:]))).isoformat()
    return val


@dataclass
class Trace:
    """Result of a full replay: where we are and what was collected.

    ``params`` and ``pin`` live in memory only; they must never be logged,
    stored or rendered (PIN safety, P9).
    """

    state_id: str
    invalid_count: int = 0
    params: dict[str, str] = field(default_factory=dict)
    pin: str | None = None
    op_id: str = ""


def _param_spec(bundle: dict[str, Any], op_id: str, name: str) -> dict[str, Any]:
    for op in bundle.get("ir", {}).get("operations", []):
        if op.get("id") == op_id:
            for prm in op.get("params", []):
                if prm.get("name") == name:
                    return prm
    return {}


def _valid_input(spec: dict[str, Any], value: str) -> bool:
    if not value or "#" in value or "*" in value:
        return False
    cons = spec.get("constraints") or {}
    if len(value) > (cons.get("max_len") or DEFAULT_MAX_INPUT):
        return False
    enum = cons.get("enum")
    if enum and value not in [str(e) for e in enum]:
        return False
    return True


def replay_full(bundle: dict[str, Any], text: str, today: date | None = None) -> Trace:
    """Replay ``text`` over ``bundle['machine']``, collecting parameters.

    Pure: no I/O. Invalid inputs (bad length/enum, unknown menu key) keep the
    state and bump ``invalid_count``. Stops advancing once an ACTION state is
    reached (the caller runs the action).
    """
    machine = bundle["machine"]
    states = machine["states"]
    trace = Trace(state_id=machine["root"])
    if not text:
        return trace

    for segment in text.split("*"):
        if segment == "":
            continue
        state = states.get(trace.state_id)
        if state is None or state["kind"] == "ACTION" or state["kind"] in (
            k.value for k in TERMINAL_KINDS
        ):
            break
        kind = state["kind"]
        transitions = state.get("transitions", {})
        is_free = kind in ("INPUT", "PIN") and segment not in ("0", "00")
        if is_free:
            if kind == "PIN":
                ok = segment.isdigit() and 4 <= len(segment) <= 6
            else:
                ok = _valid_input(
                    _param_spec(bundle, state.get("op_id", ""), state.get("param_name", "")),
                    segment,
                )
            if not ok:
                trace.invalid_count += 1
                continue
        next_id, _ = step(machine, trace.state_id, segment)
        if next_id == trace.state_id:
            trace.invalid_count += 1
            continue
        if is_free:
            if kind == "PIN":
                trace.pin = segment
            else:
                trace.params[state["param_name"]] = segment
        elif (kind == "MENU" and state.get("param_name") and segment in transitions
              and segment not in ("0", "00")):
            trace.params[state["param_name"]] = _menu_value(state, segment, today)
        trace.state_id = next_id
        trace.op_id = states[next_id].get("op_id", "") or trace.op_id
    return trace
