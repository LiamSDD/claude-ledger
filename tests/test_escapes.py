import csv
import io
import json
import os

import pytest

from claude_ledger.cli import main
from claude_ledger import transcripts

HOSTILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "hostile")
CONTROL = [chr(c) for c in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0)) if chr(c) != "\n"]


def run(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def assert_clean(out):
    found = sorted({repr(ch) for ch in out if ch in CONTROL})
    assert not found, found
    assert "[31m" not in out and "[2J" not in out and "pwned" not in out and "[8m" not in out


def test_clean_text_strips_escape_sequences_and_controls():
    assert transcripts.clean_text("claude-opus-5-5\x1b]0;pwned\x07\x1b[31m") == "claude-opus-5-5"
    assert transcripts.clean_text("/home/dev/\x1b[2J\x1b[1;1Hevil\r\b") == "/home/dev/evil"
    assert transcripts.clean_text("a\x9b31mb") == "ab"
    assert transcripts.clean_text("a\x1b]8;;http://x\x1b\\link\x1b]8;;\x1b\\b") == "alinkb"
    assert transcripts.clean_text("x\x1bcy\x1b(Bz") == "xyz"
    assert transcripts.clean_text("tab\tnew\nline\x7f") == "tabnewline"
    assert transcripts.clean_text("café → ok") == "café → ok"


@pytest.mark.parametrize("by", ["model", "project", "session", "agent", "day"])
def test_report_table_has_no_escapes(capsys, by):
    code, out, _ = run(capsys, "report", "--dir", HOSTILE, "--by", by, "--utc")
    assert code == 0
    assert_clean(out)


def test_report_table_shows_cleaned_values(capsys):
    _, out, _ = run(capsys, "report", "--dir", HOSTILE, "--utc")
    assert "claude-opus-5-5" in out
    _, out, _ = run(capsys, "report", "--dir", HOSTILE, "--by", "project", "--utc")
    assert "/home/dev/evil" in out
    _, out, _ = run(capsys, "report", "--dir", HOSTILE, "--by", "agent", "--utc")
    assert "Explore" in out
    _, out, _ = run(capsys, "report", "--dir", HOSTILE, "--by", "session", "--utc")
    assert "66666666" in out


def test_sessions_and_daily_tables_have_no_escapes(capsys):
    _, out, _ = run(capsys, "sessions", "--dir", HOSTILE, "--utc")
    assert_clean(out)
    assert "66666666" in out and "/home/dev/evil" in out and "opus-5-5" in out
    _, out, _ = run(capsys, "daily", "--dir", HOSTILE, "--utc", "--since", "2026-11-06", "--until", "2026-11-06")
    assert_clean(out)


def test_tips_have_no_escapes(capsys):
    _, out, _ = run(capsys, "tips", "--dir", HOSTILE)
    assert "Explore" in out
    assert_clean(out)


@pytest.mark.parametrize("by", ["model", "project", "session", "agent"])
def test_report_csv_has_no_escapes(capsys, by):
    _, out, _ = run(capsys, "report", "--dir", HOSTILE, "--by", by, "--csv")
    assert_clean(out)
    keys = {row[by] for row in csv.DictReader(io.StringIO(out))}
    assert keys <= {"claude-opus-5-5", "/home/dev/evil", "66666666-6666-4666-8666-666666666666", "main", "Explore"}


def test_sessions_csv_has_no_escapes(capsys):
    _, out, _ = run(capsys, "sessions", "--dir", HOSTILE, "--csv")
    assert_clean(out)
    row = next(csv.DictReader(io.StringIO(out)))
    assert row["session"] == "66666666-6666-4666-8666-666666666666"
    assert row["project"] == "/home/dev/evil"
    assert row["models"] == "claude-opus-5-5"


def test_json_values_are_cleaned(capsys):
    _, out, _ = run(capsys, "sessions", "--dir", HOSTILE, "--json")
    assert "\\u001b" not in out and "\\u009b" not in out
    session = json.loads(out)["sessions"][0]
    assert session["session"] == "66666666-6666-4666-8666-666666666666"
    assert session["project"] == "/home/dev/evil"
