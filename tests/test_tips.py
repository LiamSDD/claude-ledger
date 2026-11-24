import json

import pytest

from claude_ledger.pricing import load_prices
from claude_ledger.report import Filters, build_ledger
from claude_ledger.tips import build_tips
from claude_ledger.transcripts import scan
from datetime import timezone


def tips_for(root, **filters):
    return build_tips(build_ledger(scan(root), load_prices(), Filters(**filters), timezone.utc))


def test_fixture_tips_are_backed_by_numbers(fixtures_dir):
    tips = {t.key: t for t in tips_for(fixtures_dir)}
    assert set(tips) == {"premium-exploration", "long-sessions", "large-outputs"}
    assert tips["premium-exploration"].saving == pytest.approx(0.047)
    assert tips["long-sessions"].saving == pytest.approx(0.054008)
    assert tips["large-outputs"].saving == pytest.approx(0.054)
    assert "Explore" in tips["premium-exploration"].detail


def test_tips_sorted_by_saving(fixtures_dir):
    savings = [t.saving for t in tips_for(fixtures_dir)]
    assert savings == sorted(savings, reverse=True)


def test_compacted_session_is_not_flagged(fixtures_dir):
    tips = {t.key: t for t in tips_for(fixtures_dir, project="api")}
    assert "1 session" in tips["long-sessions"].detail


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")


def _turn(i, model, usage, ts="2026-11-01T10:00:00Z", **extra):
    entry = {"type": "assistant", "sessionId": "s", "cwd": "/w", "timestamp": ts, "requestId": f"r{i}", "message": {"id": f"m{i}", "model": model, "usage": usage, "content": []}}
    entry.update(extra)
    return entry


def test_low_cache_hit_rate_tip(tmp_path):
    _write(tmp_path / "p" / "s.jsonl", [_turn(i, "claude-sonnet-5-5", {"input_tokens": 40000, "cache_read_input_tokens": 10000}) for i in range(3)])
    tips = {t.key: t for t in tips_for(str(tmp_path))}
    assert set(tips) == {"cache-hit-rate"}
    moved = 0.85 * 150000 - 30000
    assert tips["cache-hit-rate"].saving == pytest.approx(moved * (2.0 - 0.1) / 1e6)
    assert "20%" in tips["cache-hit-rate"].detail


def test_healthy_usage_produces_no_tips(tmp_path):
    _write(tmp_path / "p" / "s.jsonl", [_turn(i, "claude-sonnet-5-5", {"input_tokens": 100, "cache_read_input_tokens": 20000, "output_tokens": 300}) for i in range(5)])
    assert tips_for(str(tmp_path)) == []


def test_empty_ledger_has_no_tips(tmp_path):
    assert tips_for(str(tmp_path)) == []


def test_cheap_exploration_is_not_flagged(tmp_path):
    root = tmp_path / "p" / "s" / "subagents"
    _write(root / "agent-a.jsonl", [_turn(1, "claude-haiku-5-5", {"input_tokens": 100000, "output_tokens": 50000, "cache_read_input_tokens": 900000}, isSidechain=True)])
    (root / "agent-a.meta.json").write_text('{"agentType": "Explore"}')
    assert "premium-exploration" not in {t.key for t in tips_for(str(tmp_path))}


def test_read_only_tools_mark_custom_agent_as_exploration(tmp_path):
    root = tmp_path / "p" / "s" / "subagents"
    turn = _turn(1, "claude-opus-5-5", {"input_tokens": 1000, "output_tokens": 10000, "cache_read_input_tokens": 900000}, isSidechain=True)
    turn["message"]["content"] = [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}, {"type": "tool_use", "id": "t2", "name": "WebSearch", "input": {}}]
    _write(root / "agent-a.jsonl", [turn])
    (root / "agent-a.meta.json").write_text('{"agentType": "researcher"}')
    assert "premium-exploration" in {t.key for t in tips_for(str(tmp_path))}
