# Contributing

Thanks for helping improve claude-ledger.

## Ground rules

- Runtime code uses the Python standard library only and must work on Python 3.9 or newer. `pytest` is the only development dependency.
- House style: no comments and no docstrings in `.py` files. Use clear names and type hints instead. A test enforces this.
- Work test-first. Add or extend a synthetic transcript in `tests/fixtures/` or build one in `tmp_path`, write the failing test, then the code.
- Never commit real transcripts, paths or project names. Fixtures must be synthetic.
- The tool stays read-only and offline. Changes that add network access or write to the projects directory will not be accepted.

## Workflow

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python3 -m pytest -q
```

If you change output formatting, regenerate the examples so they stay real:

```bash
for c in "report" "report --by agent" "report --by project" "daily --since 2026-11-01 --until 2026-11-05" "sessions" "tips"; do
  echo "\$ claude-ledger $c --dir tests/fixtures/projects --utc"; echo
  NO_COLOR=1 claude-ledger $c --dir tests/fixtures/projects --utc; echo
done > docs/example-report.txt
```

Then update the sample in `README.md` and the test count badge if it changed.

## Prices

Price changes go in `src/claude_ledger/prices.json` with a link to the published pricing in the pull request description.
