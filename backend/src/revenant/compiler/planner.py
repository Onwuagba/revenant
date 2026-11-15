"""Planner: converts IR (App) into a navigable USSD state machine.

Pure and deterministic (P6). Produces ``machine.json`` with states of kinds
MENU, INPUT, CONFIRM, PIN, ACTION, RESULT_END, RESULT_CON, SMS_END, ERROR_END.

Global keys: ``0`` back, ``00`` home (root). Items numbered 1-9; ``8`` is
More only on paginated menus. 3 invalid inputs on one state -> ERROR_END.

Source: ``architecture/IR_AND_TYPE_SUBSET.md`` section 6; requirements 1-5.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .ir import App, CarrierProfile, Operation, Param, ParamType, OpKind

#: Items per page on paginated menus.
ITEMS_PER_PAGE = 5

#: Max entries on the root menu (keys 1-7, with 8=More).
MAX_ROOT_ENTRIES = 7

#: Max retries (invalid inputs) before ERROR_END.
MAX_RETRIES = 3


class StateKind(str, Enum):
    MENU = "MENU"
    INPUT = "INPUT"
    CONFIRM = "CONFIRM"
    PIN = "PIN"
    ACTION = "ACTION"
    RESULT_END = "RESULT_END"
    RESULT_CON = "RESULT_CON"
    SMS_END = "SMS_END"
    ERROR_END = "ERROR_END"


TERMINAL_KINDS = frozenset({StateKind.RESULT_END, StateKind.SMS_END, StateKind.ERROR_END})

SCREEN_KINDS = frozenset({
    StateKind.MENU, StateKind.INPUT, StateKind.CONFIRM, StateKind.PIN,
    StateKind.RESULT_END, StateKind.RESULT_CON, StateKind.SMS_END, StateKind.ERROR_END,
})


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    max_len: int


class State(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: StateKind
    op_id: str = ""
    title: str = ""
    transitions: dict[str, str] = Field(default_factory=dict)
    template: str = ""
    slots: list[Slot] = Field(default_factory=list)
    static_len: int = 0
    worst_case_len: int = 0
    next_page: str | None = None
    param_name: str = ""
    prev: str = ""


class Machine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str = "root"
    states: dict[str, State] = Field(default_factory=dict)
    carrier_profile: CarrierProfile = Field(default_factory=CarrierProfile)
    max_retries: int = MAX_RETRIES
    refused_op_ids: set[str] = Field(default_factory=set)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "states": {sid: self.states[sid].model_dump(mode="json")
                       for sid in sorted(self.states)},
            "carrier_profile": self.carrier_profile.model_dump(mode="json"),
            "max_retries": self.max_retries,
            "refused_op_ids": sorted(self.refused_op_ids),
        }


def _param_kind(p: Param) -> StateKind:
    """Determine the state kind for a parameter."""
    if p.type == ParamType.PIN:
        return StateKind.PIN
    if p.type in (ParamType.ENUM_MENU, ParamType.DYNAMIC_CHOICE,
                  ParamType.DATE_WINDOW, ParamType.BOOLEAN):
        return StateKind.MENU
    return StateKind.INPUT


def plan(app: App, refused_op_ids: set[str] | None = None) -> Machine:
    """Convert an IR App into a navigable state machine (deterministic, P6)."""
    machine = Machine(carrier_profile=app.carrier_profile)
    if refused_op_ids:
        machine.refused_op_ids = refused_op_ids

    ops = app.sorted_operations()
    if not ops:
        machine.states["root"] = State(
            id="root", kind=StateKind.MENU, title="No services available")
        return machine

    # Build each op's flow, record entry state id
    entry_ids: dict[str, str] = {}
    for op in ops:
        entry_ids[op.id] = _build_op_flow(machine, op)

    # Build root menu
    _build_root_menu(machine, ops, entry_ids)

    # Error end
    machine.states["error_end"] = State(
        id="error_end", kind=StateKind.ERROR_END,
        title="Session ended. Try again later.")

    _add_back_navigation(machine)
    return machine


def _build_root_menu(
    machine: Machine, ops: list[Operation], entry_ids: dict[str, str]
) -> None:
    sorted_ops = sorted(ops, key=lambda o: o.id)

    if len(sorted_ops) <= MAX_ROOT_ENTRIES:
        transitions = {}
        for i, op in enumerate(sorted_ops):
            transitions[str(i + 1)] = entry_ids[op.id]
        machine.states["root"] = State(
            id="root", kind=StateKind.MENU, title="Select service",
            transitions=transitions)
        machine.root = "root"
        return

    _build_paginated_root(machine, sorted_ops, entry_ids)


def _build_paginated_root(
    machine: Machine, ops: list[Operation], entry_ids: dict[str, str]
) -> str:
    total = len(ops)
    num_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    first_page = "root_p0"

    for page in range(num_pages):
        page_id = f"root_p{page}"
        start = page * ITEMS_PER_PAGE
        end = min(start + ITEMS_PER_PAGE, total)
        page_ops = ops[start:end]

        transitions: dict[str, str] = {}
        for i, op in enumerate(page_ops):
            transitions[str(i + 1)] = entry_ids[op.id]

        next_page = None
        if page < num_pages - 1:
            transitions["8"] = f"root_p{page + 1}"
            next_page = f"root_p{page + 1}"

        machine.states[page_id] = State(
            id=page_id, kind=StateKind.MENU, title="Select service",
            transitions=transitions, next_page=next_page)

    machine.root = first_page
    return first_page


def _build_op_flow(machine: Machine, op: Operation) -> str:
    """Build the state flow for one operation. Returns the first state id."""
    leaf = op.leaf_params()
    pin_params = [p for p in leaf if p.type == ParamType.PIN]
    other = [p for p in leaf if p.type != ParamType.PIN]

    flow: list[tuple[str, StateKind, str]] = []
    for i, p in enumerate(other):
        flow.append((f"{op.id}__step{i}_{p.name}", _param_kind(p), p.name))
    if op.kind == OpKind.WRITE:
        flow.append((f"{op.id}__confirm", StateKind.CONFIRM, ""))
    if pin_params:
        flow.append((f"{op.id}__pin", StateKind.PIN, pin_params[0].name))
    flow.append((f"{op.id}__action", StateKind.ACTION, ""))
    flow.append((f"{op.id}__result", StateKind.RESULT_END, ""))

    root = machine.root or "root"

    for i, (sid, kind, pname) in enumerate(flow):
        # prev = root for the first state, otherwise the previous state
        prev = root if i == 0 else flow[i - 1][0]
        state = State(id=sid, kind=kind, op_id=op.id, param_name=pname,
                      title=op.title, prev=prev)
        if i < len(flow) - 1:
            nxt = flow[i + 1][0]
            if kind in (StateKind.INPUT, StateKind.PIN, StateKind.ACTION):
                state.transitions["*"] = nxt
            elif kind == StateKind.MENU:
                state.transitions["1"] = nxt
            elif kind == StateKind.CONFIRM:
                state.transitions["1"] = nxt
                state.transitions["2"] = root
        machine.states[sid] = state

    return flow[0][0] if flow else f"{op.id}__result"


def _add_back_navigation(machine: Machine) -> None:
    """Add 0 (back) and 00 (home) transitions using the prev field set during flow building."""
    root_id = machine.root

    for state_id, state in machine.states.items():
        if state_id == root_id:
            continue
        if state.kind in TERMINAL_KINDS or state.kind == StateKind.ACTION:
            continue
        # 0 = back to previous state (already set in prev field)
        if state.prev and state.prev in machine.states:
            state.transitions["0"] = state.prev
        # 00 = home (root)
        state.transitions["00"] = root_id

    # Paginated menu pages: next page's 0 goes back to current page
    for state_id, state in machine.states.items():
        if state.next_page and state_id != root_id:
            nxt = machine.states.get(state.next_page)
            if nxt:
                nxt.transitions["0"] = state_id
