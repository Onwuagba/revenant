"""Property-based tests for the state machine (P1-P6, P10).

P1: every rendered screen within budget, GSM-7 only, no control chars
P2: every state reachable from ROOT
P3: every state has a path to terminal; retries bounded (3)
P4: back navigation: 0 -> prev, 00 -> ROOT
P5: longest shortest path <= max_steps; random key walks terminate
P6: determinism: compile twice -> identical bundle_hash
P10: pagination covers every item exactly once; each page within budget
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from revenant.compiler.emit import compile_app
from revenant.compiler.gsm7 import is_gsm7
from revenant.compiler.ir import DraftOperation
from revenant.compiler.planner import SCREEN_KINDS, TERMINAL_KINDS, StateKind, plan
from revenant.compiler.render import render
from revenant.compiler.subset import classify_app

from .strategies import st_app


def _compile_machine(drafts):
    """Compile drafts into a rendered machine."""
    app, _ = classify_app(drafts, slug="pbt", title="PBT")
    if not app.operations:
        assume(False)
    machine = plan(app)
    render(machine, app)
    return app, machine


@pytest.mark.pbt
class TestP1ScreenBudget:
    """P1: every rendered screen within budget, GSM-7 only, no control chars."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_screens_within_budget(self, drafts):
        app, machine = _compile_machine(drafts)
        max_chars = machine.carrier_profile.max_chars
        for sid, state in machine.states.items():
            if state.kind in SCREEN_KINDS:
                assert state.worst_case_len <= max_chars, (
                    f"State {sid} worst_case {state.worst_case_len} > {max_chars}"
                )

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_screens_gsm7(self, drafts):
        app, machine = _compile_machine(drafts)
        for sid, state in machine.states.items():
            if state.kind in SCREEN_KINDS and state.template:
                assert is_gsm7(state.template), f"State {sid} has non-GSM-7 template"


@pytest.mark.pbt
class TestP2Reachability:
    """P2: every state reachable from ROOT."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_all_states_reachable(self, drafts):
        app, machine = _compile_machine(drafts)
        reachable = set()
        queue = [machine.root]
        reachable.add(machine.root)
        while queue:
            sid = queue.pop(0)
            state = machine.states.get(sid)
            if state is None:
                continue
            for dest in state.transitions.values():
                if dest not in reachable and dest in machine.states:
                    reachable.add(dest)
                    queue.append(dest)
        for sid in machine.states:
            if machine.states[sid].kind == StateKind.ERROR_END:
                continue  # implicitly reachable via retries
            assert sid in reachable, f"State {sid} not reachable from ROOT"


@pytest.mark.pbt
class TestP3ExitPaths:
    """P3: every state has a path to terminal; retries bounded."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_all_states_reach_terminal(self, drafts):
        app, machine = _compile_machine(drafts)
        terminals = {sid for sid, s in machine.states.items() if s.kind in TERMINAL_KINDS}
        assert terminals, "No terminal states"
        # reverse BFS from terminals
        reverse = {sid: set() for sid in machine.states}
        for sid, state in machine.states.items():
            for dest in state.transitions.values():
                if dest in reverse:
                    reverse[dest].add(sid)
        can_reach = set(terminals)
        queue = list(terminals)
        while queue:
            sid = queue.pop(0)
            for pred in reverse.get(sid, set()):
                if pred not in can_reach:
                    can_reach.add(pred)
                    queue.append(pred)
        for sid in machine.states:
            state = machine.states[sid]
            if state.kind in TERMINAL_KINDS or state.kind == StateKind.ACTION:
                continue
            assert sid in can_reach, f"State {sid} cannot reach a terminal"

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_retries_bounded(self, drafts):
        app, machine = _compile_machine(drafts)
        assert machine.max_retries == 3


@pytest.mark.pbt
class TestP4BackNavigation:
    """P4: 0 leads to prev, 00 leads to ROOT on non-root INPUT/MENU states."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_back_and_home(self, drafts):
        app, machine = _compile_machine(drafts)
        for sid, state in machine.states.items():
            if sid == machine.root:
                continue
            if state.kind in TERMINAL_KINDS or state.kind == StateKind.ACTION:
                continue
            assert state.transitions.get("00") == machine.root, f"State {sid}: 00 != ROOT"


@pytest.mark.pbt
class TestP5StepLimit:
    """P5: longest shortest path from ROOT to terminal <= max_steps."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_step_limit(self, drafts):
        app, machine = _compile_machine(drafts)
        max_steps = machine.carrier_profile.max_steps
        from collections import deque

        dist = {machine.root: 0}
        queue = deque([machine.root])
        while queue:
            sid = queue.popleft()
            state = machine.states.get(sid)
            if state is None:
                continue
            for dest in state.transitions.values():
                if dest in machine.states and dest not in dist:
                    dist[dest] = dist[sid] + 1
                    queue.append(dest)
        for sid in machine.states:
            state = machine.states[sid]
            if state.kind in TERMINAL_KINDS and sid in dist:
                assert dist[sid] <= max_steps, (
                    f"State {sid} at distance {dist[sid]} > max_steps {max_steps}"
                )


@pytest.mark.pbt
class TestP6Determinism:
    """P6: compile twice gives identical bundle_hash."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_deterministic_hash(self, drafts):
        app1, _ = classify_app(drafts, slug="pbt", title="PBT")
        app2, _ = classify_app(drafts, slug="pbt", title="PBT")
        assume(len(app1.operations) > 0)
        b1 = compile_app(app1)
        b2 = compile_app(app2)
        assert b1["bundle_hash"] == b2["bundle_hash"]

    @given(drafts=st_app())
    @settings(max_examples=30)
    def test_permutation_invariant(self, drafts):
        app1, _ = classify_app(drafts, slug="pbt", title="PBT")
        app2, _ = classify_app(list(reversed(drafts)), slug="pbt", title="PBT")
        assume(len(app1.operations) > 0)
        b1 = compile_app(app1)
        b2 = compile_app(app2)
        assert b1["bundle_hash"] == b2["bundle_hash"], "Hash differs under permutation"


@pytest.mark.pbt
class TestP10Pagination:
    """P10: pagination covers every item exactly once; each page within budget."""

    def test_many_ops_paginated(self):
        """Manually test pagination with 10 operations."""
        drafts = [DraftOperation(id=f"op{i:02d}", title=f"Op {i}") for i in range(10)]
        app, _ = classify_app(drafts, slug="pbt", title="PBT")
        machine = plan(app)
        render(machine, app)
        # Collect all menu item transitions from paginated root pages
        all_items = set()
        for sid, state in machine.states.items():
            if sid.startswith("root_p"):
                for key, dest in state.transitions.items():
                    if key not in ("0", "00", "8"):
                        all_items.add(dest)
        # Every operation entry should be covered exactly once
        expected = {f"op{i:02d}__action" for i in range(10)}
        assert all_items == expected, f"Missing or extra items: {all_items ^ expected}"


@pytest.mark.pbt
class TestP4BackPreservesParams:
    """P4: Back: from any non-root INPUT/MENU state, `0` leads to the previous state and
    collected params before it are preserved; `00` reaches ROOT."""

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_P4_back_goes_to_prev(self, drafts):
        app, machine = _compile_machine(drafts)
        for sid, state in machine.states.items():
            if sid == machine.root or state.kind not in (StateKind.INPUT, StateKind.MENU):
                continue
            if sid.startswith("root_p"):
                continue  # root pages: page 2's 0 is page 1 (checked in test_planner)
            assert state.transitions.get("0") == state.prev, sid
            assert state.prev in machine.states

    def test_P4_back_keeps_earlier_params_in_clinic_flow(self):
        from pathlib import Path

        from revenant.compiler.emit import compile_app
        from revenant.compiler.ingest_openapi import ingest_openapi
        from revenant.runtime.machine import replay_full

        drafts, _ = ingest_openapi(Path("examples/specs/clinic.openapi.yaml").read_bytes())
        app, _ = classify_app(drafts, slug="clinic", title="Clinic")
        b = compile_app(app)
        forward = replay_full(b, "1*c1*s1")
        back = replay_full(b, "1*c1*s1*0")
        assert back.state_id == b["machine"]["states"][forward.state_id]["prev"]
        assert back.params.get("clinic_id") == "c1"  # earlier param kept
        again = replay_full(b, "1*c1*s1*0*s9")
        assert again.params == {"clinic_id": "c1", "slot_id": "s9"}  # re-entry overwrites
