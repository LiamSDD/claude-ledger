# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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
