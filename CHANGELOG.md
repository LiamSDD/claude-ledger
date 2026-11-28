# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Match daily terminal and Markdown header dates to the displayed rows, including windows extending past the last day of usage.
- List all supported `--since` and `--until` formats in the CLI help and README.

## [0.2.0] - 2026-11-24

### Added

- `--markdown` output for `report`, `daily` and `sessions`: a short heading, a totals list and GitHub-flavoured Markdown tables, ready to paste into a pull request, issue or chat. Mutually exclusive with `--json` and `--csv`.

### Security

- Control characters and terminal escape sequences in transcript values (model IDs, project paths, session IDs, agent types) are stripped when read, so a crafted transcript cannot inject escapes into terminal output.
- CSV text cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with an apostrophe, so exports cannot run spreadsheet formulas.

### Added (repository)

- Security policy with private vulnerability reporting, issue forms and a pull request template.

## [0.1.0] - 2026-11-24

### Added

- `report` command (default): totals, cache hit rate, main versus subagent split, and breakdowns by model, project, day, session or agent type, with `--top`, `--json` and `--csv`.
- `daily` command: one row per day with a unicode bar chart of spend.
- `sessions` command: most expensive sessions with project, start time, duration, model mix and cost.
- `tips` command: savings advice with estimated dollar impact for low cache hit rates, premium models on read-only subagents, long sessions without compaction and large tool outputs.
- Time windows (`--since`, `--until`), project filter, `--dir`, `--utc` and `CLAUDE_CONFIG_DIR` support.
- Bundled price table with prefix and family matching, `--prices FILE` overrides, and explicit `unknown` cost for unpriced models.
- Exact de-duplication by message ID and request ID, within and across transcript files.
- Streaming reader that skips malformed lines and handles multi-gigabyte histories.
