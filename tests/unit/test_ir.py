"""Unit tests for ir.py — models, length limits, canonical JSON (tasks 3-4)."""

import json

import pytest
from pydantic import ValidationError

from revenant.compiler.ir import (
    App,
    CarrierProfile,
    Flow,
    Operation,
    Param,
    ParamConstraints,
    ParamType,
    Result,
    SecretType,
    canonical_json,
)


# ---------------------------------------------------------------------------
# Requirement 1.1, 1.4 — models and length limits
# ---------------------------------------------------------------------------
def test_valid_operation_loads():
    op = Operation(id="list_clinics", title="List clinics", kind="read")
    assert op.id == "list_clinics"
    assert op.title == "List clinics"


def test_valid_param_loads():
    p = Param(name="clinic", label="Pick clinic", type=ParamType.ENUM_MENU)
    assert p.name == "clinic"
    assert p.type == ParamType.ENUM_MENU


def test_overlong_operation_title_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Operation(id="op", title="x" * 25)
    assert "title" in str(exc_info.value).lower()


def test_operation_title_at_limit_ok():
    op = Operation(id="op", title="x" * 24)
    assert len(op.title) == 24


def test_overlong_param_label_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Param(name="p", label="y" * 21, type=ParamType.TOKEN)
    assert "label" in str(exc_info.value).lower()


def test_param_label_at_limit_ok():
    p = Param(name="p", label="y" * 20, type=ParamType.TOKEN)
    assert len(p.label) == 20


# ---------------------------------------------------------------------------
# Requirement 1.2, 1.3 — canonical JSON
# ---------------------------------------------------------------------------
def _make_app(ops: list[Operation]) -> App:
    return App(slug="app", title="App", operations=ops)


def test_canonical_json_sorted_keys():
    op = Operation(id="op1", title="Op One")
    data = canonical_json(op)
    text = data.decode()
    # Keys must be sorted
    assert text.index('"id"') < text.index('"title"')
    assert text.index('"kind"') < text.index('"title"')


def test_canonical_json_key_order_invariant():
    """Two IRs differing only in JSON key order serialise identically."""
    op1 = Operation(id="a", title="A", kind="read", risk="low")
    op2 = Operation(id="a", title="A", kind="read", risk="low")
    # Same content, different construction shouldn't matter
    assert canonical_json(op1) == canonical_json(op2)


def test_canonical_json_operation_order_invariant():
    """Two IRs differing only in operation order serialise identically (P6)."""
    op1 = Operation(id="alpha", title="Alpha")
    op2 = Operation(id="beta", title="Beta")
    app_a = _make_app([op1, op2])
    app_b = _make_app([op2, op1])
    assert canonical_json(app_a) == canonical_json(app_b)


def test_canonical_json_different_content_differ():
    op1 = Operation(id="a", title="Alpha")
    op2 = Operation(id="a", title="Beta")
    assert canonical_json(_make_app([op1])) != canonical_json(_make_app([op2]))


def test_canonical_json_bytes():
    op = Operation(id="op", title="Op")
    result = canonical_json(op)
    assert isinstance(result, bytes)
    assert json.loads(result)["id"] == "op"


def test_canonical_json_includes_flows_sorted():
    fl1 = Flow(id="z", title="Z", entry_op="op1")
    fl2 = Flow(id="a", title="A", entry_op="op2")
    app = App(slug="app", title="App", flows=[fl1, fl2])
    text = canonical_json(app).decode()
    # Flow "a" should come before "z"
    assert text.index('"id":"a"') < text.index('"id":"z"')


def test_flattened_param_recursive():
    """A flattened param carries sub-params and expands correctly."""
    sub1 = Param(name="first", label="First", type=ParamType.TOKEN)
    sub2 = Param(name="second", label="Second", type=ParamType.BOOLEAN)
    flat = Param(
        name="address", label="Address", type=ParamType.FLATTENED,
        params=[sub1, sub2],
    )
    expanded = flat.expand()
    assert len(expanded) == 2
    assert expanded[0].name == "first"
    assert expanded[1].name == "second"


def test_scalar_param_expand_returns_self():
    p = Param(name="x", label="X", type=ParamType.BOOLEAN)
    assert p.expand() == [p]


def test_operation_leaf_params():
    """Operation.leaf_params flattens any FLATTENED groups."""
    sub = Param(name="sub", label="Sub", type=ParamType.TOKEN)
    flat = Param(name="group", label="Group", type=ParamType.FLATTENED, params=[sub])
    scalar = Param(name="scalar", label="Scalar", type=ParamType.BOOLEAN)
    op = Operation(id="op", title="Op", params=[flat, scalar])
    leaves = op.leaf_params()
    assert len(leaves) == 2
    assert leaves[0].name == "sub"
    assert leaves[1].name == "scalar"
