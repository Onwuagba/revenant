"""P10 (pagination) applied to parameter menus: enum and date-window options.

P10: concatenated pages contain every item exactly once; each page within budget.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from revenant.compiler.emit import compile_app
from revenant.compiler.ir import DraftOperation, DraftParam
from revenant.compiler.subset import classify_app
from revenant.runtime.machine import replay_full

PER_PAGE = 5


def _bundle(enum):
    drafts = [
        DraftOperation(
            id="pick",
            title="Pick",
            params=[DraftParam(name="c", json_schema={"type": "string", "enum": enum})],
        )
    ]
    app, _ = classify_app(drafts, slug="pbt", title="PBT")
    assert app.operations, "enum of <=36 values must compile"
    return compile_app(app)


def _pages(bundle):
    states = bundle["machine"]["states"]
    page_id = "pick__step0_c"
    pages = []
    while page_id:
        pages.append(states[page_id])
        page_id = states[page_id].get("next_page")
    return pages


st_enum = st.integers(min_value=1, max_value=36).map(lambda n: [f"v{i}" for i in range(n)])


@pytest.mark.pbt
@given(enum=st_enum)
@settings(max_examples=36)
def test_P10_param_menu_pages_cover_every_value_once(enum):
    """P10: every enum value is on exactly one page; pages hold at most 5; each fits the budget."""
    b = _bundle(enum)
    pages = _pages(b)
    seen = [v for p in pages for v in p["options"]]
    assert seen == enum
    assert all(len(p["options"]) <= PER_PAGE for p in pages)
    max_chars = b["machine"]["carrier_profile"]["max_chars"]
    assert all(p["worst_case_len"] <= max_chars for p in pages)
    assert b["report"]["all_passed"]
    for i, p in enumerate(pages):
        assert ("8" in p["transitions"]) == (i < len(pages) - 1)
        assert ("8 More" in p["template"]) == (i < len(pages) - 1)


@pytest.mark.pbt
@given(enum=st_enum, data=st.data())
@settings(max_examples=40)
def test_P10_param_menu_selection_returns_the_chosen_value(enum, data):
    """Pressing More n times then a key selects exactly that option, never the key 8."""
    b = _bundle(enum)
    idx = data.draw(st.integers(min_value=0, max_value=len(enum) - 1))
    page, key = divmod(idx, PER_PAGE)
    text = "*".join(["1"] + ["8"] * page + [str(key + 1)])
    trace = replay_full(b, text)
    assert trace.params == {"c": enum[idx]}
    assert trace.state_id == "pick__action"
    assert trace.invalid_count == 0


@pytest.mark.pbt
@given(window=st.integers(min_value=1, max_value=7))
@settings(max_examples=7)
def test_P10_date_window_offers_every_day(window):
    """A date window of N days offers N days (the old cap silently dropped days 6 and 7)."""
    drafts = [
        DraftOperation(
            id="pick",
            title="Pick",
            params=[
                DraftParam(
                    name="d",
                    json_schema={
                        "type": "string",
                        "format": "date",
                        "x-revenant-date-window": window,
                    },
                )
            ],
        )
    ]
    app, _ = classify_app(drafts, slug="pbt", title="PBT")
    b = compile_app(app)
    states = b["machine"]["states"]
    sid, offered = "pick__step0_d", []
    while sid:
        offered += states[sid]["options"]
        sid = states[sid].get("next_page")
    assert offered == [f"+{i}" for i in range(window)]
