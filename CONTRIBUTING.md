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
git clone https://github.com/LiamSDD/claude-ledger && cd claude-ledger
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -e ".[dev]"
python3 -m pytest -q
claude-ledger --dir tests/fixtures/projects --utc
```

The `pip` upgrade matters on older interpreters: the pip that ships with Python 3.9 (21.2) cannot do an editable install from `pyproject.toml`. The last command runs the CLI against the synthetic fixtures, so you can see your change without touching real transcripts.

If you change output formatting, regenerate the examples so they stay real:

```bash
for c in "report" "report --by agent" "report --by project" "daily --since 2026-11-01 --until 2026-11-05" "sessions" "tips"; do
  echo "\$ claude-ledger $c --dir tests/fixtures/projects --utc"; echo
  NO_COLOR=1 sh -c "claude-ledger $c --dir tests/fixtures/projects --utc"; echo
done > docs/example-report.txt
```

The loop works in both bash and zsh (`sh -c` splits the arguments the same way in each). If nothing changed, `git status` shows `docs/example-report.txt` unmodified. Then update the sample in `README.md` and the test count badge if it changed.

## Prices

Price changes go in `src/claude_ledger/prices.json` with a link to the published pricing in the pull request description.

## Proposing a change

1. For anything bigger than a small fix, open an issue first (bug report or feature request) so the approach can be agreed before you write code. Questions go to [Discussions](https://github.com/LiamSDD/claude-ledger/discussions).
2. Issues labelled [`good first issue`](https://github.com/LiamSDD/claude-ledger/labels/good%20first%20issue) are small, scoped and have acceptance criteria.
3. Fork the repository, create a branch from `main` (for example `fix/daily-utc-boundary` or `feat/tips-markdown`) and keep each pull request to one change.
4. Fill in the pull request template. Add an entry under `Unreleased` in `CHANGELOG.md` for anything a user would notice.
5. Pull requests are squash-merged once the tests pass and the review is done.

## Commit messages

Write the subject as a short imperative sentence in plain English, capitalised and without a trailing full stop, saying what changed for the user: `Neutralise spreadsheet formulas in CSV output`, `Add --markdown output for report, daily and sessions`. Use the body to explain why. The squash merge appends the pull request number.

## Code of conduct and security

Everyone taking part is expected to follow the [code of conduct](CODE_OF_CONDUCT.md). Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), never in a public issue.
