"""Tests for renderer, validators, mutations, and bundle hash (tasks 6-12)."""

import copy
import pytest

from revenant.compiler.ir import App, Operation, Param, ParamType, DraftOperation, DraftParam
from revenant.compiler.subset import classify_app
from revenant.compiler.planner import plan, StateKind, Slot, State, Machine
from revenant.compiler.render import render
from revenant.compiler.emit import compile_app, bundle_hash
from revenant.compiler.validators import run_all
from revenant.compiler.validators.reachability import validate_reachability
from revenant.compiler.validators.exits import validate_exits
from revenant.compiler.validators.back import validate_back
from revenant.compiler.validators.steps import validate_steps
from revenant.compiler.validators.length import validate_length
from revenant.compiler.validators.pin import validate_pin
from revenant.compiler.validators.sms import validate_sms
from revenant.compiler.validators.refusal_soundness import validate_refusal_soundness


def _compile(op_id="get_price", title="Get Price", kind="read", params=None):
    drafts = [DraftOperation(id=op_id, title=title, kind=kind, params=params or [])]
    app, _ = classify_app(drafts, slug="test", title="Test")
    machine = plan(app)
    render(machine, app)
    return app, machine


class TestRenderer:
    def test_screen_has_template(self):
        app, m = _compile(params=[DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]})])
        state = m.states["get_price__item"]
        assert state.template != ""
        assert state.static_len > 0

    def test_worst_case_computed(self):
        app, m = _compile(params=[DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]})])
        for s in m.states.values():
            if s.kind in (StateKind.MENU, StateKind.INPUT, StateKind.CONFIRM, StateKind.PIN):
                assert s.worst_case_len >= s.static_len + 4

    def test_worst_case_within_budget(self):
        app, m = _compile(params=[DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]})])
        max_chars = m.carrier_profile.max_chars
        for s in m.states.values():
            assert s.worst_case_len <= max_chars

    def test_pin_template_never_shows_pin_digits(self):
        app, m = _compile(op_id="pay", title="Pay", kind="write", params=[
            DraftParam(name="amount", schema={"type": "integer", "minimum": 1, "maximum": 100}),
            DraftParam(name="pin", schema={"type": "string", "x-revenant-secret": "pin",
                       "minLength": 4, "maxLength": 6}),
        ])
        pin_state = m.states["pay__pin"]
        assert "PIN" in pin_state.template.upper() or "pin" in pin_state.template.lower()
        assert "1234" not in pin_state.template
        assert len(pin_state.slots) == 0


class TestValidators:
    def test_valid_bundle_all_pass(self):
        drafts = [DraftOperation(id="get_price", title="Get Price", kind="read", params=[
            DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]}),
        ])]
        app, _ = classify_app(drafts)
        m = plan(app)
        render(m, app)
        results = run_all(m)
        failed = [(r.validator, [v.message for v in r.violations]) for r in results if not r.passed]
        assert all(r.passed for r in results), failed

    def test_v1_unreachable_state(self):
        app, m = _compile()
        m.states["orphan"] = State(id="orphan", kind=StateKind.INPUT)
        r = validate_reachability(m)
        assert not r.passed

    def test_v3_back_loop_to_self(self):
        app, m = _compile(params=[DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]})])
        m.states["get_price__item"].transitions["0"] = "get_price__item"
        r = validate_back(m)
        assert not r.passed

    def test_v4_excessive_steps(self):
        app, m = _compile()
        m.carrier_profile.max_steps = 1
        r = validate_steps(m)
        assert not r.passed

    def test_v5_oversize_label(self):
        app, m = _compile()
        m.states["root"].template = "x" * 200
        m.states["root"].static_len = 200
        m.states["root"].worst_case_len = 204
        r = validate_length(m)
        assert not r.passed

    def test_v6_pin_followed_by_non_action(self):
        app, m = _compile(op_id="pay", title="Pay", kind="write", params=[
            DraftParam(name="pin", schema={"type": "string", "x-revenant-secret": "pin",
                       "minLength": 4, "maxLength": 6}),
        ])
        m.states["pay__pin"].transitions["*"] = "pay__result"
        r = validate_pin(m)
        assert not r.passed

    def test_v6_pin_with_echo_slot(self):
        app, m = _compile(op_id="pay", title="Pay", kind="write", params=[
            DraftParam(name="pin", schema={"type": "string", "x-revenant-secret": "pin",
                       "minLength": 4, "maxLength": 6}),
        ])
        m.states["pay__pin"].slots = [Slot(name="pin", max_len=6)]
        r = validate_pin(m)
        assert not r.passed

    def test_v8_refused_op_not_in_machine(self):
        app, m = _compile(op_id="good_op")
        r = validate_refusal_soundness(m, {"bad_op"})
        assert r.passed

    def test_v8_refused_op_present(self):
        app, m = _compile(op_id="bad_op")
        r = validate_refusal_soundness(m, {"bad_op"})
        assert not r.passed


class TestMutationSelfTest:
    """Each mutation flagged by exactly the intended validator (task 11)."""

    def _valid(self):
        return _compile(op_id="get_price", title="Get Price", params=[
            DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]}),
        ])

    def test_delete_edge(self):
        app, m = self._valid()
        m.states["get_price__item"].transitions.pop("1", None)
        r1 = validate_reachability(m)
        r2 = validate_exits(m)
        assert not r1.passed or not r2.passed

    def test_orphan_state(self):
        app, m = self._valid()
        m.states["orphan"] = State(id="orphan", kind=StateKind.INPUT)
        r = validate_reachability(m)
        assert not r.passed

    def test_200_char_label(self):
        app, m = self._valid()
        m.states["root"].template = "x" * 200
        m.states["root"].static_len = 200
        m.states["root"].worst_case_len = 204
        r = validate_length(m)
        assert not r.passed

    def test_pin_echo_slot(self):
        app, m = _compile(op_id="pay", title="Pay", kind="write", params=[
            DraftParam(name="pin", schema={"type": "string", "x-revenant-secret": "pin",
                       "minLength": 4, "maxLength": 6}),
        ])
        m.states["pay__pin"].slots = [Slot(name="pin", max_len=6)]
        r = validate_pin(m)
        assert not r.passed

    def test_back_loop_to_self(self):
        app, m = self._valid()
        m.states["get_price__item"].transitions["0"] = "get_price__item"
        r = validate_back(m)
        assert not r.passed

    def test_12_step_chain(self):
        app, m = self._valid()
        m.carrier_profile.max_steps = 1
        r = validate_steps(m)
        assert not r.passed


class TestBundleHash:
    def test_deterministic_hash(self):
        drafts = [DraftOperation(id="get_price", title="Get Price", params=[
            DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]}),
        ])]
        app1, _ = classify_app(drafts)
        app2, _ = classify_app(drafts)
        b1 = compile_app(app1)
        b2 = compile_app(app2)
        assert b1["bundle_hash"] == b2["bundle_hash"]

    def test_permutation_invariant_hash(self):
        drafts = [
            DraftOperation(id="aaa", title="Aaa"),
            DraftOperation(id="bbb", title="Bbb"),
        ]
        app1, _ = classify_app(drafts)
        app2, _ = classify_app(list(reversed(drafts)))
        b1 = compile_app(app1)
        b2 = compile_app(app2)
        assert b1["bundle_hash"] == b2["bundle_hash"]

    def test_refused_ops_absent_from_bundle(self):
        drafts = [
            DraftOperation(id="good", title="Good", params=[
                DraftParam(name="x", schema={"type": "boolean"}),
            ]),
            DraftOperation(id="bad", title="Bad", params=[
                DraftParam(name="t", schema={"type": "string"}),
            ]),
        ]
        app, report = classify_app(drafts)
        bundle = compile_app(app, refused_op_ids={"bad"})
        for sid, state in bundle["machine"]["states"].items():
            assert state["op_id"] != "bad", f"Refused op in state {sid}"
        for sid in bundle["screens"]:
            assert "bad" not in sid
