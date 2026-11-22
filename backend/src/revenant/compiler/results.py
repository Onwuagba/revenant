"""Result formatting and sizing, shared by the compiler (V7, renderer) and the runtime.

One formatter builds the text a user sees on screen or receives by SMS, so the compile-time
worst case that V7 checks is the same text the runtime sends:

- record / list results: one ``label: value`` line per declared field; list items are separated
  by a newline and capped at the schema's ``maxItems``;
- text results (no declared fields, e.g. an MCP tool without ``outputSchema``): the text itself,
  cut to the SMS segment budget with a trailing ``...`` when it is longer (stated limit, the only
  lossy path; declared fields are never cut beyond their own ``maxLength``).

Pure functions, no I/O.
"""

from __future__ import annotations

from typing import Any

from .gsm7 import GSM7_EXTENSION, sanitise_slot, septet_count
from .ir import Operation, Result, ResultShape

SINGLE_SEGMENT = 160
CONCAT_SEGMENT = 153

#: Marker appended when a text result is cut to the segment budget.
CUT_MARKER = "..."

#: Fallback slot width for a field with no declared bound (only reachable in a bundle that
#: failed V7; a verified bundle has a bound for every field).
UNBOUNDED_FALLBACK = 40

#: A worst-case slot character: printable, kept by sanitise_slot, two septets (extension table).
_WORST_CHAR = "\u20ac"
assert _WORST_CHAR in GSM7_EXTENSION


def septet_budget(segments: int) -> int:
    """Septets available in *segments* SMS segments (160 single, 153 each concatenated)."""
    if segments <= 0:
        return 0
    return SINGLE_SEGMENT if segments == 1 else CONCAT_SEGMENT * segments


def segment_count(body: str) -> int:
    n = septet_count(body)
    return 1 if n <= SINGLE_SEGMENT else (n + CONCAT_SEGMENT - 1) // CONCAT_SEGMENT


def _dig(item: Any, path: str) -> str:
    cur = item
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return ""
    return "" if cur is None else str(cur)


def _field(f: Any, key: str) -> Any:
    return f.get(key) if isinstance(f, dict) else getattr(f, key)


def format_items(fields: list[Any], items: list[Any]) -> str:
    """Render items as ``label: value`` lines; each value sanitised to its field's width."""
    blocks = []
    for item in items:
        lines = []
        for f in fields:
            width = _field(f, "max_len")
            width = UNBOUNDED_FALLBACK if width is None else int(width)
            lines.append(
                f"{_field(f, 'label')}: {sanitise_slot(_dig(item, _field(f, 'path')), width)}"
            )
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def truncate_to_septets(text: str, max_septets: int) -> str:
    """Cut *text* so it fits *max_septets*, appending CUT_MARKER when anything was cut."""
    if septet_count(text) <= max_septets:
        return text
    room = max(max_septets - septet_count(CUT_MARKER), 0)
    out, used = [], 0
    for ch in text:
        cost = septet_count(ch)
        if used + cost > room:
            break
        out.append(ch)
        used += cost
    return "".join(out) + CUT_MARKER


def bound_problems(result: Result) -> list[str]:
    """Reasons a result cannot be sized at compile time (empty when it can)."""
    if not result.fields:
        return []  # text-shaped: cut to the budget at runtime (documented)
    problems = [
        f"result field '{f.path}' has no maximum length; add maxLength (or an enum) to the schema"
        for f in result.fields
        if f.max_len is None
    ]
    if result.shape == ResultShape.LIST and result.max_items is None:
        problems.append("list result has no maxItems; add maxItems to the array schema")
    return problems


def worst_case_body(result: Result) -> str | None:
    """The longest result text the runtime can produce, or None when it is unbounded."""
    if not result.fields or bound_problems(result):
        return None
    worst_item = {f.path: _WORST_CHAR * int(f.max_len or 0) for f in result.fields}
    count = result.max_items if result.shape == ResultShape.LIST else 1
    fields = [{"path": f.path, "label": f.label, "max_len": f.max_len} for f in result.fields]
    # Paths may be dotted; build nested worst items so _dig finds them.
    item: dict[str, Any] = {}
    for path, value in worst_item.items():
        cur = item
        parts = path.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
    return format_items(fields, [item] * int(count or 1))


def worst_case_screen_len(result: Result) -> int | None:
    """Worst-case screen length (characters, including the 4-char prefix), or None."""
    body = worst_case_body(result)
    return None if body is None else len(body) + 4


def check_operation(op: Operation, sms_segments: int) -> list[tuple[str, int | None]]:
    """V7 for one operation: (message, measured segments) per problem."""
    out: list[tuple[str, int | None]] = [(p, None) for p in bound_problems(op.result)]
    body = worst_case_body(op.result)
    if body is None:
        return out
    segs = segment_count(body)
    if segs > sms_segments:
        out.append(
            (
                f"worst-case SMS is {septet_count(body)} septets ({segs} segments), over the "
                f"{sms_segments}-segment budget; lower maxItems or field maxLength",
                segs,
            )
        )
    for f in op.result.fields:
        if f"{f.label}: " not in body:
            out.append((f"SMS omits declared result field '{f.path}'", None))
    return out
