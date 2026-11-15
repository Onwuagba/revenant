"""Hypothesis strategies for JSON Schema and Revenant IR (task 9).

Generators cover in-subset and out-of-subset shapes, including cyclic refs,
huge depth, and empty schemas. Used by property tests P7, P13, and later P1-P6.
"""

from __future__ import annotations

from hypothesis import strategies as st

from revenant.compiler.ir import DraftOperation, DraftParam

# ---------------------------------------------------------------------------
# Leaf JSON Schema strategies
# ---------------------------------------------------------------------------

# In-subset scalar schemas
st_boolean_schema = st.just({"type": "boolean"})

st_bounded_int_schema = st.builds(
    lambda lo, hi: {"type": "integer", "minimum": lo, "maximum": hi},
    st.integers(min_value=0, max_value=999),
    st.integers(min_value=1000, max_value=999_999_999),
)

st_enum_schema = st.builds(
    lambda vals: {"type": "string", "enum": vals},
    st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=5),
        min_size=1,
        max_size=36,
        unique=True,
    ),
)

st_token_pattern_schema = st.builds(
    lambda pat: {"type": "string", "pattern": pat},
    st.sampled_from(["^[A-Z0-9]+$", "^[a-z]+$", "^[0-9]{4,6}$"]),
)

st_token_maxlen_schema = st.builds(
    lambda ml: {"type": "string", "maxLength": ml},
    st.integers(min_value=1, max_value=20),
)

st_pin_schema = st.builds(
    lambda mn, mx: {"type": "string", "x-revenant-secret": "pin",
                    "minLength": mn, "maxLength": mx},
    st.just(4),
    st.just(6),
)

st_date_window_schema = st.builds(
    lambda w: {"type": "string", "format": "date", "x-revenant-date-window": w},
    st.integers(min_value=1, max_value=7),
)

st_phone_schema = st.just({"type": "string", "format": "phone"})

st_options_from_schema = st.builds(
    lambda op_id: {"type": "string", "x-revenant-options-from": {
        "op_id": op_id, "value_path": "id", "label_path": "name"}},
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10),
)

# Out-of-subset schemas
st_free_text_schema = st.just({"type": "string"})

st_unbounded_number_schema = st.sampled_from([
    {"type": "integer"},
    {"type": "number"},
    {"type": "integer", "minimum": 0},
    {"type": "number", "maximum": 100},
])

st_datetime_schema = st.sampled_from([
    {"type": "string", "format": "date-time"},
    {"type": "string", "format": "time"},
    {"type": "string", "format": "duration"},
    {"type": "string", "format": "date"},
])

st_binary_schema = st.sampled_from([
    {"type": "string", "format": "binary"},
    {"type": "string", "format": "byte"},
])

st_polymorphic_schema = st.sampled_from([
    {"oneOf": [{"type": "string"}, {"type": "integer"}]},
    {"anyOf": [{"type": "boolean"}, {"type": "string"}]},
    {"allOf": [{"type": "string"}]},
    {"type": "object", "discriminator": {"propertyName": "kind"}},
])

st_nested_object_schema = st.builds(
    lambda inner: {
        "type": "object",
        "properties": {
            "outer": {"type": "object", "properties": {inner: {"type": "string"}}},
        },
    },
    st.text(min_size=1, max_size=5, alphabet="abcdefghijklmnopqrstuvwxyz"),
)

st_array_of_objects_schema = st.just({
    "type": "array",
    "items": {"type": "object", "properties": {"x": {"type": "string"}}},
})

st_remote_ref_schema = st.sampled_from([
    {"$ref": "https://example.com/schema.json"},
    {"$ref": "http://internal.local/api.json"},
])

st_local_ref_schema = st.just({"$ref": "#/components/schemas/Missing"})

st_malformed_schema = st.sampled_from([
    None,
    True,
    False,
    {},
    {"type": "unknown"},
    {"type": "string", "enum": "not_a_list"},
])

# ---------------------------------------------------------------------------
# Combinations
# ---------------------------------------------------------------------------
st_in_subset_leaf = st.one_of(
    st_boolean_schema,
    st_bounded_int_schema,
    st_enum_schema,
    st_token_pattern_schema,
    st_token_maxlen_schema,
    st_pin_schema,
    st_date_window_schema,
    st_phone_schema,
    st_options_from_schema,
)

st_out_of_subset_leaf = st.one_of(
    st_free_text_schema,
    st_unbounded_number_schema,
    st_datetime_schema,
    st_binary_schema,
    st_polymorphic_schema,
    st_nested_object_schema,
    st_array_of_objects_schema,
    st_remote_ref_schema,
    st_local_ref_schema,
    st_malformed_schema,
)

#: Any JSON Schema — in-subset, out-of-subset, or edge case.
st_any_schema = st.one_of(st_in_subset_leaf, st_out_of_subset_leaf)


# ---------------------------------------------------------------------------
# Flat object schemas (1-6 scalar properties)
# ---------------------------------------------------------------------------
st_flat_object_schema = st.builds(
    lambda props: {
        "type": "object",
        "properties": {k: v for k, v in props},
    },
    st.lists(
        st.tuples(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
            st_in_subset_leaf,
        ),
        min_size=1,
        max_size=6,
        unique_by=lambda t: t[0],
    ),
)


# ---------------------------------------------------------------------------
# Deeply nested schema (for depth-cap testing)
# ---------------------------------------------------------------------------
@st.composite
def st_deep_nested_schema(draw, depth=st.integers(min_value=10, max_value=50)):
    n = draw(depth)
    schema = {"type": "boolean"}
    for _ in range(n):
        schema = {"type": "object", "properties": {"x": schema}}
    return schema


# ---------------------------------------------------------------------------
# Operation and App strategies
# ---------------------------------------------------------------------------
@st.composite
def st_draft_param(draw):
    name = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10))
    # DraftParam.schema must be a dict; filter out non-dict malformed schemas
    schema = draw(st_any_schema.filter(lambda s: isinstance(s, dict)))
    required = draw(st.booleans())
    return DraftParam(name=name, schema=schema, required=required)


@st.composite
def st_draft_operation(draw, op_id=None):
    if op_id is None:
        op_id = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12))
    title = draw(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20))
    kind = draw(st.sampled_from(["read", "write"]))
    n_params = draw(st.integers(min_value=0, max_value=5))
    params = [draw(st_draft_param()) for _ in range(n_params)]
    return DraftOperation(id=op_id, title=title, kind=kind, params=params)


@st.composite
def st_app(draw):
    n_ops = draw(st.integers(min_value=1, max_value=12))
    # Ensure unique operation ids so P13 can compare compiled vs refused sets
    ids = draw(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12),
            min_size=n_ops,
            max_size=n_ops,
            unique=True,
        )
    )
    ops = [draw(st_draft_operation(op_id=oid)) for oid in ids]
    return ops


# ---------------------------------------------------------------------------
# Label strategies (adversarial text for screen rendering tests)
# ---------------------------------------------------------------------------
st_label = st.text(
    alphabet=st.characters(
        min_codepoint=0x20,
        max_codepoint=0x7F,
    ),
    min_size=0,
    max_size=30,
)

st_adversarial_label = st.one_of(
    st.text(min_size=0, max_size=50),  # includes unicode
    st.just("CON injected"),
    st.just("END injected"),
    st.just("1*2*3"),
    st.just("a#b"),
    st.just("\x00\x01\x02"),
    st.text(alphabet="😀🎉", min_size=1, max_size=3),  # emoji
)

st_slot_fill = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x17F),
    min_size=0,
    max_size=50,
)
