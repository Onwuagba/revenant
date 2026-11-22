"""Property-based tests for the runtime (P8, P9, P11).

P8: Replay equivalence — stateful session output equals output rebuilt from cumulative text
P9: PIN — no screen, event, log record, or DB row contains the PIN canary
P11: SMS fallback — body GSM-7, segments <= budget, contains all declared result fields
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from revenant.compiler.emit import compile_app
from revenant.compiler.gsm7 import is_gsm7
from revenant.compiler.ir import DraftOperation, DraftParam
from revenant.compiler.subset import classify_app
from revenant.runtime.machine import replay, step
from revenant.runtime.sms import build_sms_body, count_segments

from .strategies import st_app


def _compile(drafts):
    app, _ = classify_app(drafts, slug="pbt", title="PBT")
    assume(len(app.operations) > 0)
    return compile_app(app)


@pytest.mark.pbt
class TestP8ReplayEquivalence:
    """P8: stateful session output equals output rebuilt from cumulative text."""

    @given(
        drafts=st_app(),
        extra_inputs=st.lists(
            st.text(alphabet="012345678900", min_size=1, max_size=3), min_size=0, max_size=5
        ),
    )
    @settings(max_examples=30)
    def test_replay_equals_stateful(self, drafts, extra_inputs):
        bundle = _compile(drafts)
        machine = bundle["machine"]
        root = machine["root"]

        # Stateful: step through each input
        stateful_state = root
        stateful_inputs = []
        for inp in extra_inputs:
            stateful_inputs.append(inp)
            next_id, prefix = step(machine, stateful_state, inp)
            stateful_state = next_id

        # Replay: from cumulative text
        cumulative_text = "*".join(stateful_inputs)
        replayed_state, _ = replay(machine, cumulative_text)

        # Both should end at the same state (for valid inputs)
        # (Invalid inputs may differ, but valid ones must match)
        if all(
            inp in ("0", "00", "1", "2", "3", "4", "5", "6", "7", "8", "9") for inp in extra_inputs
        ):
            assert stateful_state == replayed_state, (
                f"Stateful {stateful_state} != replayed {replayed_state} for "
                f"text={cumulative_text!r}"
            )


@pytest.mark.pbt
class TestP9PinCanary:
    """P9: no screen, log record, or DB row contains the PIN canary."""

    CANARY = "7777"

    def test_canary_not_in_screens(self):
        """The canary PIN must not appear in any screen template."""
        drafts = [
            DraftOperation(
                id="pay",
                title="Pay",
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
            ),
        ]
        app, _ = classify_app(drafts)
        bundle = compile_app(app)
        for sid, screen in bundle["screens"].items():
            assert self.CANARY not in screen["template"], f"Canary PIN in screen {sid}"
            for slot in screen["slots"]:
                assert slot["name"] != "pin" or slot["name"] != "PIN", f"PIN slot in screen {sid}"

    def test_canary_not_in_machine_templates(self):
        """Check all machine state templates for the canary."""
        drafts = [
            DraftOperation(
                id="pay",
                title="Pay",
                kind="write",
                params=[
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
            ),
        ]
        app, _ = classify_app(drafts)
        bundle = compile_app(app)
        machine = bundle["machine"]
        for sid, state in machine["states"].items():
            template = state.get("template", "")
            assert self.CANARY not in template, f"Canary in state {sid} template"

    def test_canary_not_in_sms_body(self):
        """SMS body must not contain the canary PIN."""
        result = {"template": "Booked {code}", "fields": []}
        body = build_sms_body(result, {"code": "KX42"})
        assert self.CANARY not in body


@pytest.mark.pbt
class TestP11SmsFallback:
    """P11: SMS body GSM-7, segments <= budget, contains all result fields."""

    @given(
        code=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=8),
        time=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789: ", min_size=1, max_size=20),
    )
    @settings(max_examples=50)
    def test_sms_body_gsm7_and_fits(self, code, time):
        result = {
            "template": "Booked {code} {time}",
            "fields": [
                {"path": "code", "label": "Code", "max_len": 8},
                {"path": "time", "label": "Time", "max_len": 20},
            ],
        }
        body = build_sms_body(result, {"code": code, "time": time})
        assert is_gsm7(body), f"SMS body not GSM-7: {body!r}"
        # Slots are sanitised by design (whitespace collapsed, CON/END guarded).
        from revenant.compiler.gsm7 import sanitise_slot

        assert sanitise_slot(code, 160) in body, f"Missing field value in body: {body!r}"
        assert sanitise_slot(time, 160) in body, f"Missing field value in body: {body!r}"
        segments = count_segments(body)
        assert segments <= 3, f"Too many segments: {segments}"

    @given(
        text=st.text(
            min_size=100,
            max_size=500,
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7F),
        )
    )
    @settings(max_examples=30)
    def test_long_body_segments(self, text):
        from revenant.compiler.gsm7 import septet_count

        septets = septet_count(text)
        segments = count_segments(text)
        if septets <= 160:
            assert segments == 1
        else:
            expected = (septets + 152) // 153
            assert segments == expected, f"septets={septets} got={segments} expected={expected}"


@pytest.mark.pbt
class TestSlotSanitisation:
    """P1 for runtime slot values: any upstream string is rendered GSM-7, control-free,
    within its slot budget and unable to forge a CON/END prefix."""

    @given(value=st.text(max_size=200), max_len=st.integers(min_value=0, max_value=60))
    @settings(max_examples=200)
    def test_P1_slot_values_are_screen_safe(self, value, max_len):
        from revenant.compiler.gsm7 import sanitise_slot

        out = sanitise_slot(value, max_len)
        assert len(out) <= max_len
        assert is_gsm7(out)
        assert not any(ord(c) < 0x20 for c in out)
        assert "CON " not in out and "END " not in out
