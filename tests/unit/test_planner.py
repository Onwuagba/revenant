"""Tests for planner.py — machine model, single/multi ops, writes/PIN, pagination."""

from revenant.compiler.ir import App, DraftOperation, DraftParam
from revenant.compiler.planner import MAX_RETRIES, StateKind, plan
from revenant.compiler.subset import classify_app


def _app(ops):
    return App(slug="test", title="Test", operations=ops)


def _draft(op_id, title="Op", kind="read", params=None):
    return DraftOperation(id=op_id, title=title, kind=kind, params=params or [])


class TestStateMachine:
    def test_root_menu_created(self):
        drafts = [_draft("get_price", "Get Price")]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert m.root == "root"
        assert m.states["root"].kind == StateKind.MENU

    def test_single_read_op_flow(self):
        drafts = [
            _draft(
                "get_price",
                "Get Price",
                params=[
                    DraftParam(name="item", json_schema={"type": "string", "enum": ["a", "b"]}),
                ],
            )
        ]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert "get_price__step0_item" in m.states
        assert m.states["get_price__step0_item"].kind == StateKind.MENU
        assert "get_price__action" in m.states
        assert "get_price__result" in m.states

    def test_back_and_home_transitions(self):
        drafts = [
            _draft(
                "get_price",
                params=[
                    DraftParam(name="item", json_schema={"type": "string", "enum": ["a", "b"]}),
                ],
            )
        ]
        app, _ = classify_app(drafts)
        m = plan(app)
        item = m.states["get_price__step0_item"]
        assert "0" in item.transitions  # back
        assert "00" in item.transitions  # home
        assert item.transitions["00"] == "root"

    def test_write_op_has_confirm(self):
        drafts = [
            _draft(
                "book",
                "Book",
                kind="write",
                params=[
                    DraftParam(name="name", json_schema={"type": "string", "maxLength": 10}),
                ],
            )
        ]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert "book__confirm" in m.states
        assert m.states["book__confirm"].kind == StateKind.CONFIRM

    def test_pin_last_before_action(self):
        drafts = [
            _draft(
                "pay",
                "Pay",
                kind="write",
                params=[
                    DraftParam(
                        name="amount", json_schema={"type": "integer", "minimum": 1, "maximum": 100}
                    ),
                    DraftParam(
                        name="pin",
                        json_schema={
                            "type": "string",
                            "x-revenant-secret": "pin",
                            "minLength": 4,
                            "maxLength": 6,
                        },
                    ),
                ],
            )
        ]
        app, _ = classify_app(drafts)
        m = plan(app)
        pin = m.states["pay__pin"]
        action = m.states["pay__action"]
        # PIN must transition to ACTION
        assert "*" in pin.transitions
        assert pin.transitions["*"] == "pay__action"
        # ACTION must transition to a terminal
        assert "*" in action.transitions
        result_id = action.transitions["*"]
        assert m.states[result_id].kind == StateKind.RESULT_END

    def test_multiple_ops_root_menu(self):
        drafts = [_draft(f"op{i}", f"Op {i}") for i in range(3)]
        app, _ = classify_app(drafts)
        m = plan(app)
        root = m.states["root"]
        # 3 operations = 3 entries
        menu_keys = [k for k in root.transitions if k not in ("0", "00", "8")]
        assert len(menu_keys) == 3

    def test_pagination(self):
        """Root menu with >7 entries paginates 5 per page."""
        drafts = [_draft(f"op{i:02d}", f"Op {i}") for i in range(10)]
        app, _ = classify_app(drafts)
        m = plan(app)
        # Should have paginated root: root_p0, root_p1
        assert "root_p0" in m.states
        assert "root_p1" in m.states
        # Page 0 has 5 items + 8 More
        p0 = m.states["root_p0"]
        menu_keys = [k for k in p0.transitions if k not in ("0", "00")]
        assert len(menu_keys) == 6  # 5 items + 8 More

    def test_error_end_state(self):
        drafts = [_draft("op", "Op")]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert "error_end" in m.states
        assert m.states["error_end"].kind == StateKind.ERROR_END

    def test_max_retries(self):
        drafts = [_draft("op", "Op")]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert m.max_retries == MAX_RETRIES

    def test_determinism(self):
        """Same input produces the same machine (P6)."""
        drafts = [_draft(f"op{i}", f"Op {i}") for i in range(5)]
        app1, _ = classify_app(drafts)
        app2, _ = classify_app(list(reversed(drafts)))
        m1 = plan(app1)
        m2 = plan(app2)
        assert m1.canonical_dict() == m2.canonical_dict()


class TestParamMenuPagination:
    """Planner requirement 1.3: menus with more than 5 items paginate 5 per page."""

    def _states(self, n):
        drafts = [
            _draft(
                "pick",
                "Pick",
                params=[
                    DraftParam(
                        name="c",
                        json_schema={"type": "string", "enum": [f"v{i}" for i in range(n)]},
                    )
                ],
            )
        ]
        app, _ = classify_app(drafts)
        return plan(app).states

    def test_five_values_do_not_paginate(self):
        s = self._states(5)
        assert "pick__step0_c_p1" not in s
        assert "8" not in s["pick__step0_c"].transitions

    def test_six_values_paginate_with_more_and_back(self):
        s = self._states(6)
        first, second = s["pick__step0_c"], s["pick__step0_c_p1"]
        assert first.transitions["8"] == second.id
        assert second.transitions["0"] == first.id  # Back from page 2 is page 1
        assert second.transitions["00"] == "root"
        assert second.options == ["v5"]

    def test_36_values_make_eight_pages(self):
        s = self._states(36)
        assert len([k for k in s if k.startswith("pick__step0_c")]) == 8


class TestRootMenuBoundary:
    def test_seven_operations_single_page_eight_paginate(self):
        def root_of(n):
            drafts = [_draft(f"op{i:02d}", f"Op {i}") for i in range(n)]
            app, _ = classify_app(drafts)
            return plan(app)

        seven = root_of(7)
        assert seven.root == "root"
        assert len([k for k in seven.states["root"].transitions if k not in ("0", "00")]) == 7
        eight = root_of(8)
        assert eight.root == "root_p0"
        assert "8" in eight.states["root_p0"].transitions


class TestPaginatedRootNavigation:
    """Regression: with >7 operations the root is root_p0; flows must point at real states."""

    def _bundle(self):
        from revenant.compiler.emit import compile_app

        drafts = [
            _draft(
                f"op{i:02d}",
                f"Op {i}",
                kind="write",
                params=[DraftParam(name="f", json_schema={"type": "boolean"})],
            )
            for i in range(9)
        ]
        app, _ = classify_app(drafts)
        return compile_app(app)

    def test_every_transition_targets_an_existing_state(self):
        states = self._bundle()["machine"]["states"]
        for sid, s in states.items():
            for key, dest in s["transitions"].items():
                assert dest in states, f"{sid} --{key}--> {dest} (missing)"

    def test_back_returns_to_the_page_that_listed_the_operation(self):
        from revenant.runtime.machine import replay_full

        b = self._bundle()
        assert replay_full(b, "8*2*0").state_id == "root_p1"
        assert replay_full(b, "8*2*0").invalid_count == 0

    def test_no_on_confirm_goes_home(self):
        from revenant.runtime.machine import replay_full

        b = self._bundle()
        assert replay_full(b, "8*2*1*2").state_id == b["machine"]["root"] == "root_p0"
