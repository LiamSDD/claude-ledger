from datetime import datetime, timedelta, timezone

import pytest

from claude_ledger.pricing import load_prices
from claude_ledger.report import Filters, build_ledger, parse_when
from claude_ledger.transcripts import scan

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def ledger_for(fixtures_dir, **filters):
    return build_ledger(scan(fixtures_dir), load_prices(), Filters(**filters), UTC)


def test_totals_match_hand_computed_values(fixtures_dir):
    ledger = ledger_for(fixtures_dir)
    total = ledger.total
    assert total.usage.requests == 14
    assert total.usage.input == 17840
    assert total.usage.output == 14600
    assert total.usage.cache_read == 810000
    assert total.usage.cache_write == 220000
    assert total.cost == pytest.approx(1.54066)
    assert total.usage.cache_hit_rate == pytest.approx(810000 / 1047840)
    assert total.unpriced == 1
    assert ledger.unpriced_models == {"mystery-model-1"}
    assert ledger.sessions_count == 4
    assert ledger.files == 6


def test_main_vs_subagent_split(fixtures_dir):
    ledger = ledger_for(fixtures_dir)
    assert ledger.subagent.cost == pytest.approx(0.1213)
    assert ledger.main.cost == pytest.approx(1.41936)
    assert ledger.subagent.usage.requests == 4


def test_breakdown_by_model_uses_raw_ids_sorted_by_cost(fixtures_dir):
    rows = ledger_for(fixtures_dir).breakdown("model")
    assert rows[0][0] == "claude-opus-4-7"
    assert rows[0][1].cost == pytest.approx(1.18416)
    costs = dict((k, b.cost) for k, b in rows)
    assert costs["claude-opus-5-5"] == pytest.approx(0.1552 + 0.094)
    assert costs["claude-haiku-5-5-20261001"] == pytest.approx(0.0003)
    assert rows[-1][0] == "mystery-model-1"
    assert rows[-1][1].priced is False


def test_breakdown_by_project(fixtures_dir):
    rows = dict(ledger_for(fixtures_dir).breakdown("project"))
    assert rows["/home/dev/api"].cost == pytest.approx(1.22616)
    assert rows["/home/dev/webapp"].cost == pytest.approx(0.3145)
    assert rows["/home/dev/webapp"].unpriced == 1


def test_breakdown_by_day_is_chronological(fixtures_dir):
    rows = ledger_for(fixtures_dir).breakdown("day")
    assert [k for k, _ in rows] == ["2026-11-01", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert rows[0][1].cost == pytest.approx(0.2765)
    assert rows[3][1].cost == pytest.approx(0.34208)


def test_breakdown_by_agent(fixtures_dir):
    rows = dict(ledger_for(fixtures_dir).breakdown("agent"))
    assert set(rows) == {"main", "Explore", "subagent"}
    assert rows["Explore"].cost == pytest.approx(0.094)
    assert rows["subagent"].cost == pytest.approx(0.0273)


def test_breakdown_by_session_rolls_subagents_into_parent(fixtures_dir):
    rows = dict(ledger_for(fixtures_dir).breakdown("session"))
    assert rows["11111111-1111-4111-8111-111111111111"].cost == pytest.approx(0.2765)


def test_unknown_breakdown_raises(fixtures_dir):
    with pytest.raises(ValueError):
        ledger_for(fixtures_dir).breakdown("colour")


def test_daily_fills_gaps(fixtures_dir):
    days = ledger_for(fixtures_dir).daily()
    assert [d for d, _ in days] == ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert days[1][1].usage.requests == 0


def test_daily_fill_starts_at_since(fixtures_dir):
    days = ledger_for(fixtures_dir, since=datetime(2026, 10, 30, tzinfo=UTC)).daily()
    assert days[0][0] == "2026-10-30"


def test_sessions_ranked_with_duration_and_mix(fixtures_dir):
    sessions = ledger_for(fixtures_dir).sessions(10)
    assert [s.session[:8] for s in sessions] == ["33333333", "11111111", "44444444", "22222222"]
    top = sessions[0]
    assert top.project == "/home/dev/api"
    assert top.start == datetime(2026, 11, 4, 22, tzinfo=UTC)
    assert top.duration == timedelta(hours=4)
    assert top.bucket.cost == pytest.approx(1.18416)
    s1 = sessions[1]
    assert s1.duration == timedelta(minutes=30)
    assert [m for m, _ in s1.bucket.model_mix()] == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5-20261001"]
    assert ledger_for(fixtures_dir).sessions(2)[-1].session.startswith("11111111")


def test_filters_by_time_window(fixtures_dir):
    ledger = ledger_for(fixtures_dir, since=datetime(2026, 11, 4, tzinfo=UTC), until=datetime(2026, 11, 6, tzinfo=UTC))
    assert ledger.total.usage.requests == 5
    assert ledger.total.cost == pytest.approx(1.22616)
    assert ledger.sessions_count == 2


@pytest.mark.parametrize("project", ["api", "/home/dev/api", "-home-dev-api", "/home/dev/api/"])
def test_filters_by_project_name_or_path(fixtures_dir, project):
    ledger = ledger_for(fixtures_dir, project=project)
    assert ledger.total.cost == pytest.approx(1.22616)


def test_project_filter_with_no_match_is_empty(fixtures_dir):
    assert ledger_for(fixtures_dir, project="nope").total.usage.requests == 0


def test_parse_when_durations_and_dates():
    assert parse_when("24h", NOW, UTC) == NOW - timedelta(hours=24)
    assert parse_when("7d", NOW, UTC) == NOW - timedelta(days=7)
    assert parse_when("2w", NOW, UTC) == NOW - timedelta(weeks=2)
    assert parse_when("2026-11-01", NOW, UTC) == datetime(2026, 11, 1, tzinfo=UTC)
    assert parse_when("2026-11-01", NOW, UTC, end=True) == datetime(2026, 11, 2, tzinfo=UTC)
    assert parse_when("2026-11-01T10:30", NOW, UTC) == datetime(2026, 11, 1, 10, 30, tzinfo=UTC)
    assert parse_when("2026-11-01T10:30:15", NOW, UTC) == datetime(2026, 11, 1, 10, 30, 15, tzinfo=UTC)
    assert parse_when("2026-11-01 10:30", NOW, UTC) == datetime(2026, 11, 1, 10, 30, tzinfo=UTC)
    assert parse_when("today", NOW, UTC) == datetime(2026, 11, 24, tzinfo=UTC)
    assert parse_when("today", NOW, UTC, end=True) == datetime(2026, 11, 25, tzinfo=UTC)


def test_parse_when_honours_timezone():
    tz = timezone(timedelta(hours=-5))
    assert parse_when("2026-11-01", NOW, tz) == datetime(2026, 11, 1, 5, tzinfo=UTC)


@pytest.mark.parametrize("value", ["yesterday-ish", "7x", "2026-13-01", ""])
def test_parse_when_rejects_garbage(value):
    with pytest.raises(ValueError):
        parse_when(value, NOW, UTC)


def test_days_follow_display_timezone(fixtures_dir):
    tz = timezone(timedelta(hours=12))
    ledger = build_ledger(scan(fixtures_dir), load_prices(), Filters(), tz)
    days = [d for d, _ in ledger.breakdown("day")]
    assert days == ["2026-11-01", "2026-11-04", "2026-11-05"]
