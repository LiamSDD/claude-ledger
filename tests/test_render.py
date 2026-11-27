import io
from datetime import datetime, timedelta, timezone

import pytest

from claude_ledger.pricing import load_prices
from claude_ledger.report import Filters, build_ledger
from claude_ledger.transcripts import scan
from claude_ledger.render import daily_markdown, header, render_daily

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


@pytest.mark.parametrize("tz", [timezone.utc, timezone(timedelta(hours=5, minutes=30))])
@pytest.mark.parametrize("since,until", [(None, None), ("2026-11-01", None), (None, "2026-11-10"), ("2026-11-01", "2026-11-10")])
def test_daily_header_matches_displayed_days(fixtures_dir, tz, since, until):
    filters = Filters(
        since=datetime.fromisoformat(since).replace(tzinfo=tz) if since else None,
        until=datetime.fromisoformat(until).replace(tzinfo=tz) if until else None,
    )
    ledger = build_ledger(scan(fixtures_dir), load_prices(), filters, tz, datetime(2026, 11, 27, 22, tzinfo=timezone.utc))
    days = ledger.daily()
    expected = f"{days[0][0]} to {days[-1][0]}"
    assert expected in render_daily(ledger, Style(False)).splitlines()[0]
    assert expected in daily_markdown(ledger).splitlines()[2]
    if since and not until:
        assert "to 2026-11-05" in header(ledger, Style(False))


def test_daily_header_handles_empty_ledger():
    ledger = build_ledger([], load_prices(), tz=timezone.utc)
    assert "all time" in render_daily(ledger, Style(False)).splitlines()[0]
    assert "all time" in daily_markdown(ledger).splitlines()[2]
