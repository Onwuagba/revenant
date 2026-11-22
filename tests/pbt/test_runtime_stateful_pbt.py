"""Stateful property test for the runtime machine (task 17, optional).

Random key presses (digits, 0, 00, invalid inputs; never ``*`` or ``#``)
against the compiled clinic bundle, through ``runtime/machine.py`` only.

Invariants checked after every press:
  - P8: stepwise state equals ``replay`` of the cumulative text.
  - every response starts with ``CON `` or ``END ``.
  - response length <= ``carrier_profile.max_chars``.
  - terminal states stay terminal (and answer ``END``).
  - the invalid-input count never decreases, and three invalid presses on the
    current state reach ``max_retries`` (the service turns that into ``END``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from revenant.compiler.emit import compile_app
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.subset import classify_app
from revenant.runtime.machine import (
    CON_PREFIX,
    END_PREFIX,
    get_screen,
    is_terminal,
    replay,
    replay_full,
    step,
)

_BUNDLE: dict | None = None


def _clinic_bundle() -> dict:
    global _BUNDLE
    if _BUNDLE is None:
        raw = Path("examples/specs/clinic.openapi.yaml").read_bytes()
        drafts, _ = ingest_openapi(raw)
        app, _ = classify_app(drafts, slug="clinic", title="Clinic Booking")
        _BUNDLE = compile_app(app)
    return _BUNDLE


# Keys: navigation, menu digits, ids/PIN-like tokens, adversarial text. No "*" or "#".
st_key = st.one_of(
    st.sampled_from(
        ["0", "00", "1", "2", "3", "4", "5", "6", "7", "8", "9", "99", "c1", "s1", "2468"]
    ),
    st.text(alphabet="abcXYZ0123456789 -", min_size=1, max_size=30),
)


class ClinicKeyPresses(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.bundle = _clinic_bundle()
        self.machine = self.bundle["machine"]
        self.max_chars = self.machine["carrier_profile"]["max_chars"]
        self.max_retries = self.machine.get("max_retries", 3)
        self.state = self.machine["root"]
        self.prefix = CON_PREFIX
        self.keys: list[str] = []
        self.last_invalid = 0

    @rule(key=st_key)
    def press(self, key: str) -> None:
        was_terminal = is_terminal(self.machine, self.state)
        before = self.state
        self.state, self.prefix = step(self.machine, self.state, key)
        self.keys.append(key)
        if was_terminal:
            assert self.state == before, "terminal state moved"
            assert self.prefix == END_PREFIX, "terminal state answered CON"

    @rule(key=st.sampled_from(["99", "zz", "7777777"]))
    def three_invalid_presses(self, key: str) -> None:
        """3 invalid inputs on one non-terminal state reach the retry limit."""
        if is_terminal(self.machine, self.state):
            return
        state = self.machine["states"][self.state]
        if key in state.get("transitions", {}) or "*" in state.get("transitions", {}):
            return  # not invalid here (menu key or free-input state)
        text_before = "*".join(self.keys)
        base = replay_full(self.bundle, text_before)
        text = "*".join([*self.keys, key, key, key])
        trace = replay_full(self.bundle, text)
        if trace.state_id == base.state_id:
            assert trace.invalid_count >= base.invalid_count + 3
            assert trace.invalid_count >= self.max_retries

    @invariant()
    def response_shape_and_length(self) -> None:
        assert self.prefix in (CON_PREFIX, END_PREFIX)
        response = self.prefix + get_screen(self.machine, self.state)
        assert response.startswith(("CON ", "END "))
        assert len(response) <= self.max_chars, f"{len(response)} > {self.max_chars}: {response!r}"

    @invariant()
    def stepwise_equals_replay(self) -> None:
        """P8 on the cumulative text of everything pressed so far."""
        state, _ = replay(self.machine, "*".join(self.keys))
        assert state == self.state, f"replay {state} != stepwise {self.state} for {self.keys!r}"

    @invariant()
    def invalid_count_monotonic(self) -> None:
        trace = replay_full(self.bundle, "*".join(self.keys))
        assert trace.invalid_count >= self.last_invalid
        self.last_invalid = trace.invalid_count


@pytest.mark.pbt
def test_P8_stateful_key_presses():
    """P8 (stateful): stepwise session output equals output rebuilt from cumulative text.

    Also checks CON/END prefix, carrier max_chars, terminal stickiness and the
    3-invalid retry limit over random key sequences.
    """
    # max_examples comes from the active profile (dev/ci/deep); hand edit, see the build log.
    cfg = settings(stateful_step_count=12, deadline=None)
    ClinicKeyPresses.TestCase.settings = cfg
    ClinicKeyPresses.TestCase("runTest").runTest()
