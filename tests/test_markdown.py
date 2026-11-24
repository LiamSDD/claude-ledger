import pytest

from claude_ledger.cli import main
from claude_ledger.render import md_cell, md_table


def run(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def table_rows(out, first_header):
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"| {first_header} |"))
    rows = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


def test_md_cell_escapes_markdown_syntax():
    assert md_cell("a|b") == "a\\|b"
    assert md_cell("$1.54*") == "$1.54\\*"
    assert md_cell("x\ny") == "x y"
    assert md_cell("<b>") == "\\<b\\>"


def test_md_table_layout():
    out = md_table(["Name", "Cost"], [["a", "$1.00"]], ["l", "r"])
    assert out.splitlines() == ["| Name | Cost |", "| :--- | ---: |", "| a | $1.00 |"]


def test_report_markdown(capsys, fixtures_dir):
    code, out, _ = run(capsys, "report", "--dir", fixtures_dir, "--utc", "--markdown")
    assert code == 0
    assert out.startswith("## Claude Code usage\n")
    assert "2026-11-01 to 2026-11-05, 4 sessions, 6 transcript files" in out
    assert "- **Estimated cost:** $1.54\\*" in out
    assert "- **Cache hit rate:** 77.3%" in out
    assert "- **Subagents:** $0.12 (7.9%, 4 requests)" in out
    assert "### By model" in out
    rows = table_rows(out, "Model")
    assert rows[0] == "| Model | Priced as | Requests | Input | Output | Cache read | Cache write | Cost | Share |"
    assert rows[1] == "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    assert rows[2].startswith("| claude-opus-4-7 | claude-opus-5-5 | 4 |")
    assert "| mystery-model-1 | unknown | 1 |" in out
    assert "mystery-model-1. Add them with --prices FILE." in out
    assert "\x1b[" not in out


def test_report_markdown_by_project_and_top(capsys, fixtures_dir):
    _, out, _ = run(capsys, "--dir", fixtures_dir, "--by", "project", "--top", "1", "--markdown")
    rows = table_rows(out, "Project")
    assert len(rows) == 3
    assert "/home/dev/api" in rows[2]
    assert "1 more (use --top 0 to show all)" in out


def test_daily_markdown(capsys, fixtures_dir):
    code, out, _ = run(capsys, "daily", "--dir", fixtures_dir, "--utc", "--since", "2026-11-01", "--until", "2026-11-05", "--markdown")
    assert code == 0
    assert out.startswith("## Claude Code usage\n")
    rows = table_rows(out, "Day")
    assert rows[0] == "| Day | Requests | Tokens | Cost |"
    assert len(rows) == 2 + 5 + 1
    assert rows[3] == "| 2026-11-02 | - | - | - |"
    assert rows[-1] == "| **Total** | **14** | **1.1M** | **$1.54\\*** |"
    assert "- **Active days:** 4" in out
    assert "- **Peak day:** $0.88" in out


def test_sessions_markdown(capsys, fixtures_dir):
    code, out, _ = run(capsys, "sessions", "--dir", fixtures_dir, "--utc", "--top", "2", "--markdown")
    assert code == 0
    assert "### Most expensive sessions (top 2 of 4)" in out
    rows = table_rows(out, "Session")
    assert rows[0] == "| Session | Project | Start | Duration | Models | Requests | Cost |"
    assert len(rows) == 4
    assert rows[2] == "| 33333333 | /home/dev/api | 2026-11-04 22:00 | 4h 00m | opus-4-7 100% | 4 | $1.18 |"
    assert "44444444" not in out


@pytest.mark.parametrize("other", ["--json", "--csv"])
def test_markdown_is_exclusive_with_other_formats(fixtures_dir, other):
    with pytest.raises(SystemExit) as exc:
        main(["--dir", fixtures_dir, "--markdown", other])
    assert exc.value.code == 2


def test_markdown_is_not_offered_for_tips(fixtures_dir):
    with pytest.raises(SystemExit) as exc:
        main(["tips", "--dir", fixtures_dir, "--markdown"])
    assert exc.value.code == 2
