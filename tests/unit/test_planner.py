"""Tests for planner.py — machine model, single/multi ops, writes/PIN, pagination."""

from revenant.compiler.ir import App, Operation, Param, ParamType, DraftOperation, DraftParam, OpKind
from revenant.compiler.subset import classify_app
from revenant.compiler.planner import plan, StateKind, Machine, MAX_ROOT_ENTRIES, MAX_RETRIES


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
        drafts = [_draft("get_price", "Get Price", params=[
            DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]}),
        ])]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert "get_price__item" in m.states
        assert m.states["get_price__item"].kind == StateKind.MENU
        assert "get_price__action" in m.states
        assert "get_price__result" in m.states

    def test_back_and_home_transitions(self):
        drafts = [_draft("get_price", params=[
            DraftParam(name="item", schema={"type": "string", "enum": ["a", "b"]}),
        ])]
        app, _ = classify_app(drafts)
        m = plan(app)
        item = m.states["get_price__item"]
        assert "0" in item.transitions  # back
        assert "00" in item.transitions  # home
        assert item.transitions["00"] == "root"

    def test_write_op_has_confirm(self):
        drafts = [_draft("book", "Book", kind="write", params=[
            DraftParam(name="name", schema={"type": "string", "maxLength": 10}),
        ])]
        app, _ = classify_app(drafts)
        m = plan(app)
        assert "book__confirm" in m.states
        assert m.states["book__confirm"].kind == StateKind.CONFIRM

    def test_pin_last_before_action(self):
        drafts = [_draft("pay", "Pay", kind="write", params=[
            DraftParam(name="amount", schema={"type": "integer", "minimum": 1, "maximum": 100}),
            DraftParam(name="pin", schema={"type": "string", "x-revenant-secret": "pin",
                       "minLength": 4, "maxLength": 6}),
        ])]
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
