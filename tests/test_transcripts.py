import os
from datetime import datetime, timezone

from claude_ledger.transcripts import Usage, find_transcripts, iter_entries, parse_timestamp, projects_root, scan, usage_from


def test_projects_root_respects_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert projects_root() == os.path.join(str(tmp_path), "projects")


def test_projects_root_defaults_to_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert projects_root() == os.path.join(str(tmp_path), ".claude", "projects")


def test_find_transcripts_is_recursive_and_only_jsonl(fixtures_dir):
    found = [os.path.relpath(p, fixtures_dir) for p in find_transcripts(fixtures_dir)]
    assert len(found) == 7
    assert all(p.endswith(".jsonl") for p in found)
    assert any("subagents" in p for p in found)


def test_find_transcripts_on_missing_dir_is_empty(tmp_path):
    assert find_transcripts(str(tmp_path / "missing")) == []


def test_iter_entries_skips_malformed_and_non_object_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(b'{"a": 1}\n{broken\n[1,2]\n\n\xff\xfe\n{"b": 2}\n{"c": ')
    assert list(iter_entries(str(path))) == [{"a": 1}, {"b": 2}]


def test_iter_entries_on_unreadable_path_yields_nothing(tmp_path):
    assert list(iter_entries(str(tmp_path / "missing.jsonl"))) == []


def test_usage_from_reads_split_cache_writes():
    usage = usage_from({"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 9, "cache_creation": {"ephemeral_5m_input_tokens": 4, "ephemeral_1h_input_tokens": 5}})
    assert (usage.input, usage.output, usage.cache_read, usage.cache_write_5m, usage.cache_write_1h, usage.requests) == (1, 2, 3, 4, 5, 1)


def test_usage_from_without_split_treats_writes_as_5m():
    usage = usage_from({"input_tokens": 1, "cache_creation_input_tokens": 7})
    assert (usage.cache_write_5m, usage.cache_write_1h) == (7, 0)


def test_usage_from_tolerates_garbage_values():
    usage = usage_from({"input_tokens": None, "output_tokens": "12", "cache_read_input_tokens": "x", "cache_creation": "nope", "cache_creation_input_tokens": -5})
    assert (usage.input, usage.output, usage.cache_read, usage.cache_write_5m) == (0, 12, 0, 0)


def test_usage_add_and_hit_rate():
    total = Usage()
    total.add(Usage(input=10, cache_read=80, cache_write_5m=10, requests=1))
    total.add(Usage(output=5, requests=1))
    assert total.requests == 2
    assert total.context == 100
    assert total.cache_hit_rate == 0.8
    assert Usage().cache_hit_rate == 0.0


def test_parse_timestamp_variants():
    assert parse_timestamp("2026-11-01T09:00:00.000Z") == datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    assert parse_timestamp("2026-11-01T09:00:00Z") == datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    assert parse_timestamp("2026-11-01T09:00:00.123456789Z").microsecond == 123456
    assert parse_timestamp("2026-11-01T10:00:00+01:00") == datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    assert parse_timestamp("garbage") is None
    assert parse_timestamp(None) is None


def _threads(fixtures_dir):
    return list(scan(fixtures_dir))


def test_scan_dedupes_message_ids_within_and_across_files(fixtures_dir):
    keys = [t.key for th in _threads(fixtures_dir) for t in th.turns]
    assert len(keys) == len(set(keys))
    assert len(keys) == 14


def test_scan_skips_synthetic_and_truncated_entries(fixtures_dir):
    models = {t.model for th in _threads(fixtures_dir) for t in th.turns}
    assert "<synthetic>" not in models
    assert "mystery-model-1" in models


def test_scan_marks_subagents_and_agent_types(fixtures_dir):
    threads = {os.path.basename(th.path): th for th in _threads(fixtures_dir)}
    explore = threads["agent-explore01.jsonl"]
    assert explore.subagent and explore.agent == "Explore"
    assert all(t.sidechain and t.agent == "Explore" for t in explore.turns)
    assert explore.session == "11111111-1111-4111-8111-111111111111"
    worker = threads["agent-worker02.jsonl"]
    assert worker.agent == "subagent"
    main = threads["11111111-1111-4111-8111-111111111111.jsonl"]
    assert not main.subagent
    inline = [t for t in main.turns if t.sidechain]
    assert [t.model for t in inline] == ["claude-haiku-5-5-20261001"]
    assert inline[0].agent == "subagent"


def test_scan_records_project_from_cwd(fixtures_dir):
    threads = _threads(fixtures_dir)
    labels = {th.project: th.project_label for th in threads}
    assert labels["-home-dev-webapp"] == "/home/dev/webapp"
    assert labels["-home-dev-api"] == "/home/dev/api"


def test_scan_records_tools_outputs_and_compaction(fixtures_dir):
    threads = {os.path.basename(th.path): th for th in _threads(fixtures_dir)}
    main = threads["11111111-1111-4111-8111-111111111111.jsonl"]
    assert main.turns[0].tools == ("Read",)
    assert [(o.chars, o.ordinal) for o in main.outputs] == [(40000, 1)]
    assert set(threads["agent-explore01.jsonl"].turns[0].tools) == {"Grep", "Read"}
    assert threads["44444444-4444-4444-8444-444444444444.jsonl"].compacted
    assert not threads["33333333-3333-4333-8333-333333333333.jsonl"].compacted


def test_scan_skips_files_older_than_since(fixtures_dir, tmp_path):
    old = tmp_path / "p" / "old.jsonl"
    old.parent.mkdir()
    old.write_text('{"type":"assistant","timestamp":"2020-01-01T00:00:00Z","message":{"id":"m","model":"claude-opus-5-5","usage":{"input_tokens":1}}}\n')
    os.utime(old, (1_577_836_800, 1_577_836_800))
    assert list(scan(str(tmp_path), since=datetime(2021, 1, 1, tzinfo=timezone.utc))) == []
    assert len(list(scan(str(tmp_path)))) == 1


def test_scan_without_message_id_counts_each_entry(tmp_path):
    path = tmp_path / "p" / "s.jsonl"
    path.parent.mkdir()
    line = '{"type":"assistant","uuid":"%s","message":{"model":"claude-opus-5-5","usage":{"input_tokens":1}}}\n'
    path.write_text(line % "u1" + line % "u2" + line % "u2")
    turns = [t for th in scan(str(tmp_path)) for t in th.turns]
    assert len(turns) == 2


def test_scan_keeps_last_usage_for_repeated_message(tmp_path):
    path = tmp_path / "p" / "s.jsonl"
    path.parent.mkdir()
    line = '{"type":"assistant","requestId":"r","message":{"id":"m","model":"claude-opus-5-5","usage":{"input_tokens":1,"output_tokens":%d}}}\n'
    path.write_text(line % 1 + line % 40)
    turns = [t for th in scan(str(tmp_path)) for t in th.turns]
    assert [t.usage.output for t in turns] == [40]


def test_small_tool_outputs_are_not_retained(tmp_path):
    path = tmp_path / "p" / "s.jsonl"
    path.parent.mkdir()
    small = '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t","content":"short"}]}}\n'
    big = '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t","content":[{"type":"text","text":"%s"}]}]}}\n' % ("z" * 25000)
    path.write_text(small + big)
    (thread,) = scan(str(tmp_path))
    assert [o.chars for o in thread.outputs] == [25000]
