import io

from claude_ledger.render import bar, money, pct, short_model, table, tokens, use_color, Style


def test_money_formats():
    assert money(0) == "$0.00"
    assert money(1234.5) == "$1,234.50"
    assert money(0.0003) == "$0.0003"
    assert money(None) == "unknown"


def test_tokens_formats():
    assert tokens(999) == "999"
    assert tokens(1500) == "1.5k"
    assert tokens(2_500_000) == "2.5M"
    assert tokens(3_000_000_000) == "3.0B"


def test_pct():
    assert pct(0.773) == "77.3%"
    assert pct(0) == "0.0%"


def test_short_model():
    assert short_model("claude-opus-5-5-20261101") == "opus-5-5"
    assert short_model("claude-haiku-5-5") == "haiku-5-5"
    assert short_model("mystery-model-1") == "mystery-model-1"


def test_table_aligns_columns():
    out = table(["Name", "Cost"], [["a", "$1.00"], ["longer", "$10.00"]], ["l", "r"], Style(False))
    lines = out.splitlines()
    assert lines[0] == "Name       Cost"
    assert lines[2] == "a         $1.00"
    assert lines[3] == "longer   $10.00"
    assert set(lines[1]) <= {"-", " "}
    assert len({len(l) for l in lines}) == 1


def test_table_has_no_ansi_without_colour():
    assert "\x1b[" not in table(["A"], [["b"]], ["l"], Style(False))
    assert "\x1b[" in table(["A"], [["b"]], ["l"], Style(True))


def test_bar_scales_and_uses_partial_blocks():
    assert bar(10, 10, 10) == "█" * 10
    assert bar(0, 10, 10) == ""
    assert bar(5, 10, 10) == "█" * 5
    assert bar(0.55, 10, 10) == "▌"
    assert bar(1, 0, 10) == ""


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def test_use_color_rules():
    assert use_color(FakeTTY(), {}) is True
    assert use_color(FakeTTY(), {"NO_COLOR": "1"}) is False
    assert use_color(io.StringIO(), {}) is False
