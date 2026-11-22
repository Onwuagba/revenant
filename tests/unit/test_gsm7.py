"""gsm7 module (state-machine-validators requirements 2.3 and 2.4)."""

import pytest
from revenant.compiler.gsm7 import (
    is_gsm7,
    sanitise_slot,
    septet_count,
    strip_control_chars,
    transliterate,
    unmappable_chars,
)


class TestTransliterate:
    def test_accents_and_quotes_become_gsm7(self):
        out = transliterate("Café “Ñame” – Zoë…")
        assert is_gsm7(out)

    def test_report_characters_it_cannot_map(self):
        assert unmappable_chars("ok") == []
        assert unmappable_chars("Kés 😀 Привет") == sorted(set("😀Привет"))

    def test_extension_chars_cost_two_septets(self):
        assert septet_count("a€") == 3
        assert is_gsm7("[x]")


class TestControlChars:
    @pytest.mark.parametrize("ch", ["\x00", "\x07", "\x1b", "\x7f", "\x85", "\x9f"])
    def test_control_chars_removed(self, ch):
        assert strip_control_chars(f"a{ch}b") == "ab"

    def test_newline_and_tab_kept(self):
        assert strip_control_chars("a\nb\tc") == "a\nb\tc"


class TestSanitiseSlot:
    def test_collapses_newlines_and_truncates(self):
        assert sanitise_slot("line1\n\nline2   end", 10) == "line1 line"

    @pytest.mark.parametrize("value", ["CON hacked", "END early", "x CON y END z"])
    def test_prefix_injection_neutralised(self, value):
        out = sanitise_slot(value, 40)
        assert "CON " not in out and "END " not in out

    def test_untransliterable_replaced_not_passed_through(self):
        out = sanitise_slot("Kés 😀 Привет", 40)
        assert is_gsm7(out)
        assert out.startswith("Kes ?")
