"""Validator self-test, strict form (state-machine-validators requirement 4).

Each mutation breaks exactly one thing in a valid bundle and must be flagged by exactly the
intended validator and no other (requirement 4.2). The six mutations from docs/TESTING.md are
here, plus a dead-end branch (none of the six isolates V2) and a refused operation (V8).
"""

from __future__ import annotations

import pytest
from revenant.compiler.ir import DraftOperation, DraftParam
from revenant.compiler.planner import Machine, Slot, State, StateKind
from revenant.compiler.render import render
from revenant.compiler.subset import classify_app
from revenant.compiler.validators import run_all

ITEM = DraftParam(name="item", json_schema={"type": "string", "enum": ["a", "b"]})
PIN = DraftParam(
    name="pin",
    json_schema={"type": "string", "x-revenant-secret": "pin", "minLength": 4, "maxLength": 6},
)


def _bundle() -> Machine:
    """Two operations: a read menu op and a write op with a PIN."""
    from revenant.compiler.planner import plan

    drafts = [
        DraftOperation(id="aread", title="Read", kind="read", params=[ITEM]),
        DraftOperation(id="bpay", title="Pay", kind="write", params=[ITEM, PIN]),
    ]
    app, _ = classify_app(drafts)
    machine = plan(app)
    render(machine, app)
    return machine


def _flagged(machine: Machine, refused: set[str] | None = None) -> list[str]:
    return sorted(r.validator for r in run_all(machine, None, refused or set()) if not r.passed)


def _small_screen(state: State) -> None:
    state.template = "Enter value\n0 Back\n00 Home"
    state.static_len = len(state.template)
    state.worst_case_len = state.static_len + 4


def test_unmutated_bundle_passes_every_validator():
    assert _flagged(_bundle()) == []


def test_delete_edge_flags_only_reachability():
    m = _bundle()
    entry = m.states["root"].transitions.pop("1")  # root no longer leads to op "aread"
    assert entry.startswith("aread")
    assert _flagged(m) == ["V1_reachability"]


def test_orphan_state_flags_only_reachability():
    m = _bundle()
    orphan = State(
        id="orphan",
        kind=StateKind.INPUT,
        prev="root",
        transitions={"*": "aread__result", "0": "root", "00": "root"},
    )
    _small_screen(orphan)
    m.states["orphan"] = orphan
    assert _flagged(m) == ["V1_reachability"]


def test_unbounded_retries_flags_only_exit_paths():
    """V2 covers two things: no path to a terminal, and unbounded invalid-input retries."""
    m = _bundle()
    m.max_retries = 1000
    assert _flagged(m) == ["V2_exits"]


def test_action_dead_end_is_caught_by_exit_paths():
    """An ACTION that leads nowhere is a stuck session (the only dead end V3 cannot rule out).
    Its result also becomes unreachable, so V1 fires too; V2 must be among the failures."""
    m = _bundle()
    m.states["aread__action"].transitions = {"*": "aread__action"}
    flagged = _flagged(m)
    assert "V2_exits" in flagged
    assert set(flagged) <= {"V1_reachability", "V2_exits"}


def test_back_loop_to_self_flags_only_back():
    m = _bundle()
    m.states["aread__step0_item"].transitions["0"] = "aread__step0_item"
    assert _flagged(m) == ["V3_back"]


def test_twelve_step_chain_flags_only_step_limit():
    m = _bundle()
    first = m.states["aread__step0_item"]
    action = first.transitions["1"]
    prev = first.id
    chain = [f"chain{i:02d}" for i in range(12)]
    for i, sid in enumerate(chain):
        nxt = chain[i + 1] if i + 1 < len(chain) else action
        st = State(id=sid, kind=StateKind.INPUT, op_id="aread", prev=prev)
        st.transitions = {"*": nxt, "0": prev, "00": "root"}
        _small_screen(st)
        m.states[sid] = st
        prev = sid
    for key in [k for k in first.transitions if k not in ("0", "00")]:
        first.transitions[key] = chain[0]
    m.states[action].prev = chain[-1]
    assert _flagged(m) == ["V4_steps"]


def test_200_char_label_flags_only_length():
    m = _bundle()
    root = m.states["root"]
    root.template = "x" * 200
    root.static_len = 200
    root.worst_case_len = 204
    assert _flagged(m) == ["V5_length"]


def test_pin_echo_slot_flags_only_pin_safety():
    m = _bundle()
    m.states["bpay__pin"].slots = [Slot(name="pin", max_len=0)]  # zero width: length unchanged
    assert _flagged(m) == ["V6_pin"]


def test_refused_operation_in_machine_flags_only_refusal_soundness():
    assert _flagged(_bundle(), refused={"aread"}) == ["V8_refusal_soundness"]


@pytest.mark.parametrize(
    "name",
    [
        "delete_edge",
        "orphan",
        "retries",
        "back_loop",
        "twelve_step",
        "long_label",
        "pin_echo",
    ],
)
def test_each_mutation_is_caught(name):
    """Guard against a vacuous validator: run_all must report at least one failure."""
    m = _bundle()
    {
        "delete_edge": lambda: m.states["root"].transitions.pop("1"),
        "orphan": lambda: m.states.__setitem__("orphan", State(id="orphan", kind=StateKind.INPUT)),
        "retries": lambda: setattr(m, "max_retries", 1000),
        "back_loop": lambda: m.states["aread__step0_item"].transitions.__setitem__(
            "0", "aread__step0_item"
        ),
        "twelve_step": lambda: setattr(m.carrier_profile, "max_steps", 1),
        "long_label": lambda: setattr(m.states["root"], "worst_case_len", 999),
        "pin_echo": lambda: setattr(m.states["bpay__pin"], "slots", [Slot(name="p", max_len=6)]),
    }[name]()
    assert _flagged(m) != []


def test_unbounded_result_field_flags_only_sms():
    """V7 mutation: a result field loses its bound; only V7 may fire (needs the IR ops)."""
    from revenant.compiler.ir import Operation, Result, ResultField, ResultShape

    m = _bundle()
    ops = [
        Operation(
            id="aread",
            title="Read",
            result=Result(
                shape=ResultShape.RECORD, fields=[ResultField(path="v", label="v", max_len=None)]
            ),
        )
    ]
    flagged = sorted(r.validator for r in run_all(m, ops, set()) if not r.passed)
    assert flagged == ["V7_sms"]
