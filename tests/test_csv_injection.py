import csv
import io

from claude_ledger import render


def test_csv_safe_neutralises_formula_prefixes():
    for value in ["=HYPERLINK(\"http://x\")", "+1+1", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"]:
        assert render.csv_safe(value) == "'" + value


def test_csv_safe_keeps_ordinary_values():
    assert render.csv_safe("/home/dev/webapp") == "/home/dev/webapp"
    assert render.csv_safe("claude-opus-5-5") == "claude-opus-5-5"
    assert render.csv_safe(-1.5) == -1.5
    assert render.csv_safe(42) == 42
    assert render.csv_safe("") == ""


def test_csv_tables_never_start_a_text_cell_with_a_formula():
    text = render._csv("project", [["=cmd|' /C calc'!A0", 1, 2, 3, 4, 5, 6, 0.5, 0]])
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[1][0] == "'=cmd|' /C calc'!A0"
    assert rows[1][1] == "1"
