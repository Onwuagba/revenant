"""Unit tests for refusals.py — 12 codes and Refusal model (tasks 2)."""

from revenant.compiler.refusals import HINTS, MESSAGES, Refusal, RefusalCode

EXPECTED_CODES = {
    "R_NESTED_OBJECT",
    "R_POLYMORPHIC",
    "R_FREE_TEXT",
    "R_DATETIME",
    "R_UNBOUNDED_NUMBER",
    "R_TOO_MANY_PARAMS",
    "R_BINARY",
    "R_AUTH_SCHEME",
    "R_CALLBACK",
    "R_NON_GSM7",
    "R_REF_UNRESOLVED",
    "R_RECURSIVE",
}


def test_enum_has_exactly_12_codes():
    codes = {c.value for c in RefusalCode}
    assert codes == EXPECTED_CODES
    assert len(RefusalCode) == 12


def test_every_code_has_message_and_hint():
    for code in RefusalCode:
        assert code in MESSAGES, f"missing message for {code}"
        assert code in HINTS, f"missing hint for {code}"
        assert MESSAGES[code], f"empty message for {code}"
        assert HINTS[code], f"empty hint for {code}"


def test_refusal_make_uses_defaults():
    r = Refusal.make("op1", "#/x", RefusalCode.R_NESTED_OBJECT)
    assert r.op_id == "op1"
    assert r.path == "#/x"
    assert r.code == RefusalCode.R_NESTED_OBJECT
    assert r.message == MESSAGES[RefusalCode.R_NESTED_OBJECT]
    assert r.hint == HINTS[RefusalCode.R_NESTED_OBJECT]


def test_refusal_make_custom_message_hint():
    r = Refusal.make("op1", "#/x", RefusalCode.R_FREE_TEXT,
                     message="custom msg", hint="custom hint")
    assert r.message == "custom msg"
    assert r.hint == "custom hint"


def test_refusal_code_is_str_enum():
    assert RefusalCode.R_NESTED_OBJECT == "R_NESTED_OBJECT"
    assert isinstance(RefusalCode.R_FREE_TEXT.value, str)


def test_refusal_serialises():
    r = Refusal.make("op1", "#/x", RefusalCode.R_BINARY)
    data = r.model_dump(mode="json")
    assert data["code"] == "R_BINARY"
    assert "message" in data
    assert "hint" in data
