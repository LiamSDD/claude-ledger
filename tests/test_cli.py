import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from claude_ledger import __version__
from claude_ledger.cli import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as handle:
        assert f'version = "{__version__}"' in handle.read()


@pytest.mark.parametrize("command", ["report", "daily", "sessions", "tips"])
def test_date_window_help(command, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    out, err = capsys.readouterr()
    assert not err

    options = {" ".join(option.split()) for option in out.split("\n  --")[1:]}
    since = next(option for option in options if option.startswith("since WHEN "))
    until = next(option for option in options if option.startswith("until WHEN "))
    formats = (
        "24h", "7d", "30d", "4w", "today", "YYYY-MM-DD,", "YYYY-MM-DDTHH:MM,",
        "YYYY-MM-DDTHH:MM:SS", "YYYY-MM-DD HH:MM",
    )
    for value in formats:
        assert value in since
        assert value in until
    assert ("default: 30d" in since) == (command == "daily")
    assert "exclusive end" in until
    assert "24 hours after the selected day starts" in until


def test_default_command_is_report(capsys, fixtures_dir):
    code, out, _ = run(capsys, "--dir", fixtures_dir, "--utc")
    assert code == 0
    assert "$1.54" in out
    assert "77.3%" in out
    assert "Subagents" in out
    assert "claude-opus-4-7" in out
    assert "unknown" in out
    assert "mystery-model-1" in out
    assert "\x1b[" not in out


def test_global_options_work_after_subcommand_and_before(capsys, fixtures_dir):
    a = run(capsys, "report", "--dir", fixtures_dir, "--utc")
    b = run(capsys, "--dir", fixtures_dir, "--utc", "report")
    assert a == b


def test_report_by_project_json(capsys, fixtures_dir):
    code, out, _ = run(capsys, "report", "--dir", fixtures_dir, "--by", "project", "--json", "--utc")
    data = json.loads(out)
    assert code == 0
    assert data["totals"]["requests"] == 14
    assert data["totals"]["cost_usd"] == pytest.approx(1.54066)
    assert data["totals"]["cache_hit_rate"] == pytest.approx(0.773, abs=1e-3)
    assert data["split"]["subagent"]["cost_usd"] == pytest.approx(0.1213)
    assert data["by"] == "project"
    assert [r["key"] for r in data["rows"]] == ["/home/dev/api", "/home/dev/webapp"]
    assert data["unpriced_models"] == ["mystery-model-1"]


def test_report_unknown_model_cost_is_null_in_json(capsys, fixtures_dir):
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--json")
    rows = {r["key"]: r for r in json.loads(out)["rows"]}
    assert rows["mystery-model-1"]["cost_usd"] is None
    assert rows["mystery-model-1"]["unpriced_requests"] == 1


def test_report_csv(capsys, fixtures_dir):
    code, out, _ = run(capsys, "report", "--dir", fixtures_dir, "--by", "day", "--csv", "--utc")
    rows = list(csv.DictReader(io.StringIO(out)))
    assert code == 0
    assert [r["day"] for r in rows] == ["2026-11-01", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert float(rows[0]["cost_usd"]) == pytest.approx(0.2765)
    assert rows[1]["cost_usd"] == "0.038"
    assert rows[1]["unpriced_requests"] == "1"


def test_report_top_limits_rows(capsys, fixtures_dir):
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--by", "model", "--top", "2", "--json")
    assert len(json.loads(out)["rows"]) == 2


def test_report_filters(capsys, fixtures_dir):
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--json", "--utc", "--since", "2026-11-04", "--until", "2026-11-05")
    assert json.loads(out)["totals"]["cost_usd"] == pytest.approx(1.22616)
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--json", "--project", "webapp")
    assert json.loads(out)["totals"]["cost_usd"] == pytest.approx(0.3145)


def test_report_agent_breakdown(capsys, fixtures_dir):
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--by", "agent")
    assert "Explore" in out and "main" in out


def test_daily_has_bars_and_gap_days(capsys, fixtures_dir):
    code, out, _ = run(capsys, "daily", "--dir", fixtures_dir, "--utc", "--since", "2026-11-01")
    assert code == 0
    assert "█" in out
    assert "2026-11-02" in out
    assert datetime.now().astimezone(timezone.utc).strftime("%Y-%m-%d") in out


def test_daily_json(capsys, fixtures_dir):
    _, out, _ = run(capsys, "daily", "--dir", fixtures_dir, "--utc", "--since", "2026-11-01", "--until", "2026-11-05", "--json")
    days = json.loads(out)["days"]
    assert [d["day"] for d in days] == ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert days[3]["cost_usd"] == pytest.approx(0.88408)


def test_sessions(capsys, fixtures_dir):
    code, out, _ = run(capsys, "sessions", "--dir", fixtures_dir, "--utc", "--top", "2")
    assert code == 0
    assert "33333333" in out and "11111111" in out
    assert "44444444" not in out
    assert "4h 00m" in out
    assert "2026-11-04 22:00" in out
    assert "/home/dev/api" in out


def test_sessions_json(capsys, fixtures_dir):
    _, out, _ = run(capsys, "sessions", "--dir", fixtures_dir, "--utc", "--json")
    sessions = json.loads(out)["sessions"]
    assert sessions[0]["session"].startswith("33333333")
    assert sessions[0]["duration_seconds"] == 14400
    assert sessions[0]["models"] == {"claude-opus-4-7": pytest.approx(1.18416)}


def test_tips(capsys, fixtures_dir):
    code, out, _ = run(capsys, "tips", "--dir", fixtures_dir)
    assert code == 0
    assert "Opus-class model" in out or "premium model" in out
    assert "$0.05" in out


def test_tips_json(capsys, fixtures_dir):
    _, out, _ = run(capsys, "tips", "--dir", fixtures_dir, "--json")
    tips = json.loads(out)["tips"]
    assert {t["key"] for t in tips} == {"premium-exploration", "long-sessions", "large-outputs"}
    assert all(t["saving_usd"] > 0 for t in tips)


def test_tips_when_nothing_to_say(capsys, tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "s.jsonl").write_text('{"type":"assistant","message":{"id":"m","model":"claude-haiku-5-5","usage":{"input_tokens":10,"output_tokens":10}}}\n')
    code, out, _ = run(capsys, "tips", "--dir", str(tmp_path))
    assert code == 0
    assert "No savings advice" in out


def test_prices_override(capsys, fixtures_dir, tmp_path):
    prices = tmp_path / "p.json"
    prices.write_text(json.dumps({"models": {"mystery-model-1": {"input": 1000, "output": 1000}}}))
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--json", "--prices", str(prices))
    data = json.loads(out)
    assert data["totals"]["cost_usd"] == pytest.approx(1.54066 + 2.0)
    assert data["unpriced_models"] == []


def test_bad_prices_file_is_an_error(capsys, fixtures_dir, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    code, _, err = run(capsys, "--dir", fixtures_dir, "--prices", str(bad))
    assert code == 2
    assert "prices" in err


def test_missing_dir_is_an_error(capsys, tmp_path):
    code, _, err = run(capsys, "--dir", str(tmp_path / "nope"))
    assert code == 1
    assert "No Claude Code projects directory" in err


def test_bad_since_is_a_usage_error(capsys, fixtures_dir):
    with pytest.raises(SystemExit) as exc:
        main(["--dir", fixtures_dir, "--since", "soon"])
    assert exc.value.code == 2


def test_json_and_csv_are_exclusive(capsys, fixtures_dir):
    with pytest.raises(SystemExit):
        main(["--dir", fixtures_dir, "--json", "--csv"])


def test_empty_window_reports_nothing_found(capsys, fixtures_dir):
    code, out, _ = run(capsys, "--dir", fixtures_dir, "--since", "2030-01-01")
    assert code == 0
    assert "No usage found" in out


def test_config_dir_env_is_used(capsys, monkeypatch, tmp_path, fixtures_dir):
    os.symlink(fixtures_dir, tmp_path / "projects")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    _, out, _ = run(capsys, "--json")
    assert json.loads(out)["totals"]["requests"] == 14


def test_python_dash_m_entry_point(fixtures_dir):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.run([sys.executable, "-m", "claude_ledger", "--dir", fixtures_dir, "--json"], capture_output=True, text=True, env=env, check=False)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["totals"]["requests"] == 14


def test_no_comments_or_docstrings_in_source():
    import ast
    import tokenize

    src = os.path.join(ROOT, "src", "claude_ledger")
    for name in os.listdir(src):
        if not name.endswith(".py"):
            continue
        path = os.path.join(src, name)
        with open(path, "rb") as fh:
            assert not [t for t in tokenize.tokenize(fh.readline) if t.type == tokenize.COMMENT], name
        tree = ast.parse(open(path).read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                assert ast.get_docstring(node) is None, name


def test_option_values_are_not_mistaken_for_commands():
    from claude_ledger.cli import normalize_argv

    assert normalize_argv(["--project", "daily"]) == ["report", "--project", "daily"]
    assert normalize_argv(["--dir", "x", "sessions", "--top", "3"]) == ["sessions", "--dir", "x", "--top", "3"]
    assert normalize_argv([]) == ["report"]
    assert normalize_argv(["--version"]) == ["--version"]


def test_since_after_until_is_rejected(fixtures_dir):
    with pytest.raises(SystemExit) as exc:
        main(["--dir", fixtures_dir, "--since", "2026-11-05", "--until", "2026-11-01"])
    assert exc.value.code == 2
