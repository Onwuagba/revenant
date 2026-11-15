"""GSM 03.38 (GSM-7) charset utilities.

Minimal implementation for the classifier; expanded with full transliteration
and slot sanitisation in the state-machine-validators spec (render.py).

GSM-7 is the default alphabet for SMS and USSD. Characters outside it must be
transliterated or refused (``R_NON_GSM7``). The extension table characters cost
2 septets each but are still valid GSM-7.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GSM 03.38 default alphabet (basic table, 0x00–0x7F minus ESC 0x1B)
# ---------------------------------------------------------------------------
_GSM7_BASIC_CHARS = (
    "@\u00a3$\u00a5\u00e8\u00e9\u00f9\u00ec\u00f2\u00c7\n"
    "\u00d8\u00f8\r\u00c5\u00e5"
    "\u0394_\u03a6\u0393\u039b\u03a9\u03a0\u03a8\u03a3\u0398\u039e"
    "\u00c6\u00e6\u00df\u00c9"
    " !\"#\u00a4%&'()*+,-./0123456789:;<=>?"
    "\u00a1ABCDEFGHIJKLMNOPQRSTUVWXYZ\u00c4\u00d6\u00d1\u00dc\u00a7"
    "\u00bfabcdefghijklmnopqrstuvwxyz\u00e4\u00f6\u00f1\u00fc\u00e0"
)
GSM7_BASIC: frozenset[str] = frozenset(_GSM7_BASIC_CHARS)

# ---------------------------------------------------------------------------
# Extension table (entered via ESC 0x1B)
# ---------------------------------------------------------------------------
_GSM7_EXT_CHARS = "\f^{}\\[~]|\u20ac"
GSM7_EXTENSION: frozenset[str] = frozenset(_GSM7_EXT_CHARS)

GSM7_ALL: frozenset[str] = GSM7_BASIC | GSM7_EXTENSION


def is_gsm7(text: str) -> bool:
    """Return True if every character in *text* is representable in GSM-7."""
    return all(ch in GSM7_ALL for ch in text)


def septet_count(text: str) -> int:
    """Count GSM-7 septets: basic chars cost 1, extension chars cost 2."""
    total = 0
    for ch in text:
        total += 2 if ch in GSM7_EXTENSION else 1
    return total


# ---------------------------------------------------------------------------
# Basic transliteration (expanded in render.py / spec 3)
# ---------------------------------------------------------------------------
_TRANSLITERATIONS: dict[str, str] = {
    # Latin-1 supplement -> base ASCII
    "\u00e0": "a", "\u00e1": "a", "\u00e2": "a", "\u00e3": "a", "\u00e4": "a",
    "\u00e5": "a",
    "\u00e8": "e", "\u00e9": "e", "\u00ea": "e", "\u00eb": "e",
    "\u00ec": "i", "\u00ed": "i", "\u00ee": "i", "\u00ef": "i",
    "\u00f2": "o", "\u00f3": "o", "\u00f4": "o", "\u00f5": "o", "\u00f6": "o",
    "\u00f9": "u", "\u00fa": "u", "\u00fb": "u", "\u00fc": "u",
    "\u00e7": "c", "\u00c7": "C",
    "\u00f1": "n", "\u00d1": "N",
    # Curly quotes
    "\u2018": "'", "\u2019": "'", "\u201c": "'", "\u201d": "'",
    # Dashes
    "\u2013": "-", "\u2014": "-",
    # Ellipsis
    "\u2026": "...",
}


def transliterate(text: str) -> str:
    """Replace common non-GSM-7 characters with GSM-7 equivalents."""
    return "".join(_TRANSLITERATIONS.get(ch, ch) for ch in text)


def can_transliterate(text: str) -> bool:
    """Return True if *text* can be fully transliterated to GSM-7."""
    return is_gsm7(transliterate(text))


def strip_control_chars(text: str) -> str:
    """Remove control characters except newline and tab."""
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)


def sanitise_slot(value: str, max_len: int) -> str:
    """Sanitise a dynamic slot value for screen rendering.

    Strips control chars, collapses newlines, transliterates to GSM-7,
    and truncates to *max_len* characters.
    """
    cleaned = strip_control_chars(value)
    cleaned = " ".join(cleaned.split())  # collapse whitespace/newlines
    cleaned = transliterate(cleaned)
    # Guard against CON /END prefix injection
    cleaned = cleaned.replace("CON ", "CON_").replace("END ", "END_")
    return cleaned[:max_len]
