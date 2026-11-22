"""Renderer: fills screen templates, slot budgets and worst-case lengths.

Computes ``worst_case_len = static_len + sum(slot max_len) + 4`` (prefix)
and checks it against ``carrier_profile.max_chars`` (requirement 2.1-2.2).
Results that exceed the budget become ``SMS_END``.

Source: ``architecture/IR_AND_TYPE_SUBSET.md`` section 6; carrier rules.
"""

from __future__ import annotations

from .gsm7 import is_gsm7
from .ir import App, Operation, Param
from .planner import Machine, Slot, State, StateKind

PREFIX_LEN = 4  # "CON " or "END "


def render(machine: Machine, app: App) -> Machine:
    """Fill in templates, slots, static_len and worst_case_len for every state.

    Results that exceed the budget are converted to ``SMS_END``.
    """
    max_chars = machine.carrier_profile.max_chars
    ops_by_id = {op.id: op for op in app.operations}

    for state in machine.states.values():
        if state.kind == StateKind.MENU:
            _render_menu(state, machine, app, ops_by_id, max_chars)
        elif state.kind == StateKind.INPUT:
            _render_input(state, machine, ops_by_id, max_chars)
        elif state.kind == StateKind.CONFIRM:
            _render_confirm(state, machine, ops_by_id, max_chars)
        elif state.kind == StateKind.PIN:
            _render_pin(state, max_chars)
        elif state.kind == StateKind.RESULT_END:
            _render_result(state, machine, ops_by_id, max_chars)
        elif state.kind == StateKind.ERROR_END:
            _render_error(state, max_chars)

    return machine


def _compute_worst_case(state: State, max_chars: int) -> bool:
    """Compute worst_case_len. Returns True if it fits within budget."""
    slot_total = sum(s.max_len for s in state.slots)
    state.worst_case_len = state.static_len + slot_total + PREFIX_LEN
    return state.worst_case_len <= max_chars


def _check_gsm7(state: State) -> bool:
    """Check template is GSM-7 and has no control chars."""
    return is_gsm7(state.template)


def _render_menu(
    state: State, machine: Machine, app: App, ops_by_id: dict[str, Operation], max_chars: int
) -> None:
    """Render a menu state (root or operation selection)."""
    if state.id == machine.root or state.id.startswith("root"):
        # Root menu: list operations by their titles
        lines = ["Select service"]
        # Collect menu items from transitions (skip 0, 00, 8)
        items = []
        for key in sorted(state.transitions, key=lambda k: (len(k), k)):
            if key in ("0", "00", "8"):
                continue
            dest = state.transitions[key]
            op_id = dest.split("__")[0] if "__" in dest else ""
            op = ops_by_id.get(op_id)
            label = op.title if op else dest
            items.append(f"{key} {label}")
        lines.extend(items)
        if "0" in state.transitions:
            lines.append("0 Back")
        if "00" in state.transitions:
            lines.append("00 Home")
        if "8" in state.transitions:
            lines.append("8 More")
    else:
        # Operation param menu (enum, date window, dynamic choice)
        op = ops_by_id.get(state.op_id)
        param = _find_param(op, state.param_name) if op else None
        label = param.label if param else state.param_name
        lines = [f"Select {label}"]
        from .planner import menu_label

        for i, val in enumerate(state.options):
            lines.append(f"{i + 1} {menu_label(val)}")
        if "8" in state.transitions:
            lines.append("8 More")
        if "0" in state.transitions:
            lines.append("0 Back")
        if "00" in state.transitions:
            lines.append("00 Home")

    state.template = "\n".join(lines)
    state.static_len = len(state.template)
    state.slots = []
    _compute_worst_case(state, max_chars)


def _render_input(
    state: State, machine: Machine, ops_by_id: dict[str, Operation], max_chars: int
) -> None:
    """Render an input prompt state."""
    op = ops_by_id.get(state.op_id)
    param = _find_param(op, state.param_name) if op else None
    label = param.label if param else state.param_name
    hint = ""
    if param and param.constraints:
        if param.constraints.min is not None and param.constraints.max is not None:
            hint = f" ({param.constraints.min}-{param.constraints.max})"
        elif param.constraints.max_len is not None:
            hint = f" (max {param.constraints.max_len} chars)"
    state.template = f"Enter {label}{hint}"
    if "0" in state.transitions:
        state.template += "\n0 Back"
    if "00" in state.transitions:
        state.template += "\n00 Home"
    state.static_len = len(state.template)
    state.slots = []
    _compute_worst_case(state, max_chars)


def _render_confirm(
    state: State, machine: Machine, ops_by_id: dict[str, Operation], max_chars: int
) -> None:
    """Render a confirmation screen."""
    op = ops_by_id.get(state.op_id)
    title = op.title if op else "Confirm"
    state.template = f"{title}?\n1 Yes 2 No"
    if "0" in state.transitions:
        state.template += "\n0 Back"
    if "00" in state.transitions:
        state.template += "\n00 Home"
    state.static_len = len(state.template)
    state.slots = []
    _compute_worst_case(state, max_chars)


def _render_pin(state: State, max_chars: int) -> None:
    """Render a PIN entry prompt (never echoes the PIN)."""
    state.template = "Enter PIN"
    if "0" in state.transitions:
        state.template += "\n0 Back"
    if "00" in state.transitions:
        state.template += "\n00 Home"
    state.static_len = len(state.template)
    state.slots = []  # No slots — PIN is never rendered
    _compute_worst_case(state, max_chars)


def _render_result(
    state: State, machine: Machine, ops_by_id: dict[str, Operation], max_chars: int
) -> None:
    """Render a result screen from the shared formatter; SMS_END when the worst case is too long.

    The template shows one item (``label: {path}`` per field); ``worst_case_len`` covers every
    item up to ``maxItems``, so it is the real longest screen, not one row of it.
    """
    from .results import worst_case_screen_len

    op = ops_by_id.get(state.op_id)
    result = op.result if op else None
    if result and result.template:
        template = result.template
    elif result and result.fields:
        template = "\n".join(f"{f.label}: {{{f.path}}}" for f in result.fields)
    else:
        template = "Done"
    state.template = template
    state.slots = [
        Slot(name=f.path, max_len=f.max_len if f.max_len is not None else max_chars)
        for f in (result.fields if result else [])
    ]
    state.static_len = len(state.template)
    _compute_worst_case(state, max_chars)
    if result and result.fields:
        worst = worst_case_screen_len(result)
        state.worst_case_len = worst if worst is not None else max_chars + 1  # unbounded
    if state.worst_case_len > max_chars:
        state.kind = StateKind.SMS_END
        state.template = "Details sent by SMS"
        state.slots = []
        state.static_len = len(state.template)
        _compute_worst_case(state, max_chars)


def _render_error(state: State, max_chars: int) -> None:
    state.template = "Session ended. Try again later."
    state.static_len = len(state.template)
    state.slots = []
    _compute_worst_case(state, max_chars)


def _find_param(op: Operation | None, name: str) -> Param | None:
    """Find a leaf param by name in an operation."""
    if op is None:
        return None
    for p in op.leaf_params():
        if p.name == name:
            return p
    return None
