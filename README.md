# claude-ledger

**Shows where your Claude Code tokens and dollars go, then suggests savings with their impact.**

<a href="https://github.com/LiamSDD/LiamSDD/blob/main/assets/demos/claude-ledger-demo.mp4"><img src="https://raw.githubusercontent.com/LiamSDD/LiamSDD/main/assets/demos/claude-ledger-loop.gif" alt="claude-ledger demo: savings tips with their dollar impact, from sample transcripts" width="100%"></a>

[![Python](https://img.shields.io/badge/python-3.9%2B-334155)](pyproject.toml) [![Dependencies](https://img.shields.io/badge/dependencies-0-16a34a)](pyproject.toml) [![License](https://img.shields.io/badge/license-MIT-334155)](LICENSE) [![Tests](https://img.shields.io/badge/tests-149%20passing-16a34a)](tests)

## Why

- **Find the cost.** Spend by model, project, day, session and subagent, from your local transcripts.
- **Check your cache.** See whether prompt caching works or you pay full price for the same context.
- **Get savings tips** with an estimated dollar impact, based on your own numbers.
- **Private and light.** Read-only, offline, zero dependencies, Python 3.9+.

## Quick start

```bash
pipx install git+https://github.com/LiamSDD/claude-ledger
claude-ledger              # all-time report
claude-ledger tips --since 30d
```

[Watch the demo](https://github.com/LiamSDD/LiamSDD/blob/main/assets/demos/claude-ledger-demo.mp4) · [Example outputs](docs/example-report.txt) · [How costs are computed](#how-costs-are-computed) · [FAQ](#faq)

Also works with `pip install git+https://github.com/LiamSDD/claude-ledger` or `python -m claude_ledger`.

## Example

Real output, from the synthetic transcripts in [`tests/fixtures`](tests/fixtures):

```text
$ claude-ledger
Claude Code usage  2026-11-01 to 2026-11-05, 4 sessions, 6 transcript files

  Estimated cost  $1.54*
  Requests        14
  Input tokens    17.8k
  Output tokens   14.6k
  Cache read      810.0k
  Cache write     220.0k  (216.0k 5m, 4.0k 1h)
  Cache hit rate  77.3%

  Main sessions   $1.42*       92.1%  10 requests
  Subagents       $0.12         7.9%  4 requests

By model
Model                        Priced as           Requests   Input   Output   Cache read   Cache write      Cost   Share
--------------------------   -----------------   --------   -----   ------   ----------   -----------   -------   -----
claude-opus-4-7              claude-opus-5-5            4      40     4.5k       470.0k        200.0k     $1.18   76.9%
claude-opus-5-5              claude-opus-5-5            5    7.3k     3.8k       160.0k         20.0k     $0.25   16.2%
claude-fable-5-2             claude-fable-5-2           1     500      100       170.0k             0     $0.04    2.7%
claude-sonnet-5-5-20261015   claude-sonnet-5-5          1    4.0k     3.0k            0             0     $0.04    2.5%
claude-sonnet-5-5            claude-sonnet-5-5          1    3.0k     2.0k        10.0k             0     $0.03    1.8%
claude-haiku-5-5-20261001    claude-haiku-5-5           1    2.0k      200            0             0   $0.0003    0.0%
mystery-model-1              unknown                    1    1.0k     1.0k            0             0   unknown       -

* Costs exclude 1 request on models with no known price: mystery-model-1. Add them with --prices FILE.
```

## Commands

`report` is the default, so `claude-ledger` on its own prints the all-time report.

| Command | What it shows |
| --- | --- |
| `report [--by model\|project\|day\|session\|agent] [--top N]` | Totals, cache hit rate, main vs subagent split and one breakdown table |
| `daily [--since 30d]` | One row per day, including empty days, with a spend bar chart |
| `sessions [--top 10]` | The most expensive sessions: project, start, duration, model mix and cost |
| `tips [--since 30d]` | Savings advice with an estimated dollar impact |

**`report --by`**

- `model` (default): every raw model ID, with the price-table entry it was priced as.
- `project`: one row per working directory.
- `day`: one row per calendar day.
- `session`: one row per session; subagent work is rolled into its parent.
- `agent`: `main` versus each subagent type (`Explore`, `Plan`, your own agents), from Claude Code's agent metadata.

Tables show the top 20 rows; `--top N` changes that and `--top 0` shows everything. JSON and CSV include every row unless `--top` is given.

### Options for every command

| Option | Meaning |
| --- | --- |
| `--since WHEN` | Start of the window: `24h`, `7d`, `30d`, `4w`, `today`, `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM`, `YYYY-MM-DDTHH:MM:SS` or `'YYYY-MM-DD HH:MM'`. Defaults to `30d` for `daily`. |
| `--until WHEN` | Exclusive end of the window, with the same formats as `--since` |
| `--project PATH\|NAME` | Only one project: its path (`~/code/api`), its folder name (`api`) or its encoded directory name |
| `--dir PATH` | Read another projects directory instead of the default |
| `--prices FILE` | Override or extend the bundled price table (see below) |
| `--utc` | Group days and show times in UTC instead of local time |
| `--json` / `--csv` | Machine-readable output instead of tables |
| `--markdown` | GitHub-flavoured Markdown tables for pull requests, issues and chat (`report`, `daily` and `sessions`) |
| `--version` | Print the version |

Dates and timestamps use local time by default and UTC with `--utc`. For `today` and plain dates, `--since` starts at midnight and `--until` ends 24 hours after the selected day starts. For timestamps and relative durations, each option uses the specified time or the computed instant directly. The start is inclusive and the end is exclusive. If omitted, `--until` leaves the window open-ended.

Transcripts are read from `~/.claude/projects`, or `$CLAUDE_CONFIG_DIR/projects` when `CLAUDE_CONFIG_DIR` is set. Subfolders are scanned, so subagent transcripts are included.

### Tips

A tip appears only when the data supports it and its impact is at least one cent.

| Tip | Fires when | Estimated impact |
| --- | --- | --- |
| Low prompt-cache hit rate | Under 60% of context tokens came from cache | Cost difference if 85% had been cache reads |
| Read-only subagents on a premium model | `Explore`/`Plan` agents, or agents that only used read-only tools, ran on a model priced above Sonnet | Same tokens repriced at the Sonnet rate |
| Long sessions without compaction | A session passed 150k tokens of context and never compacted | Cache-read cost of the context above 100k on every request |
| Large tool outputs | Tool results over 20k characters entered the context | Cache write of that content plus its re-reads on later requests |

The impacts overlap, so treat them as a ranking, not a sum.

### Output formats

- Colour only when stdout is a terminal and `NO_COLOR` is not set.
- `--json` and `--csv` give stable output with raw token counts. An unpriced model has `"cost_usd": null` in JSON and an empty cost in CSV.
- `--markdown` (`report`, `daily`, `sessions`) prints a heading, totals as bullets and the table as GFM. It excludes `--json` and `--csv`, keeps the same row limits, escapes Markdown control characters, and `daily` leaves out the bar chart.

```bash
claude-ledger --since 30d --by project --csv > spend.csv
claude-ledger --json | jq '.totals.cost_usd'
claude-ledger sessions --top 2 --markdown | pbcopy
```

<details>
<summary><b>Sample <code>daily</code> and <code>--markdown</code> output</b></summary>

```text
Claude Code usage  2026-11-01 to 2026-11-05, 4 sessions, 6 transcript files

Day          Requests   Tokens     Cost   Spend
----------   --------   ------   ------   --------------------------------
2026-11-01          7   208.3k    $0.28   ██████████
2026-11-02          -        -        -
2026-11-03          2     9.0k   $0.04*   █▍
2026-11-04          2   283.0k    $0.88   ████████████████████████████████
2026-11-05          3   562.1k    $0.34   ████████████▍
Total              14     1.1M   $1.54*

  4 active day(s), average $0.39 per active day, peak $0.88
```

```markdown
## Claude Code usage

2026-11-01 to 2026-11-05, 4 sessions, 6 transcript files

### Most expensive sessions (top 2 of 4)

| Session | Project | Start | Duration | Models | Requests | Cost |
| :--- | :--- | :--- | ---: | :--- | ---: | ---: |
| 33333333 | /home/dev/api | 2026-11-04 22:00 | 4h 00m | opus-4-7 100% | 4 | $1.18 |
| 11111111 | /home/dev/webapp | 2026-11-01 09:00 | 30m | opus-5-5 90%, sonnet-5-5 10%, +1 | 7 | $0.28 |

\* Costs exclude 1 request on models with no known price: mystery-model-1. Add them with --prices FILE.
```

</details>

## How costs are computed

- **One count per request**, keyed on `message.id` plus `requestId`, de-duplicated across files.
- **Main vs subagent** from `isSidechain` and `subagents/` transcripts.
- **List prices** per million tokens, bundled in [`src/claude_ledger/prices.json`](src/claude_ledger/prices.json) and overridable with `--prices FILE`.
- **Unknown models are never counted as zero**: totals carry an asterisk and a note.

<details>
<summary><b>Full method: de-duplication, token classes, price table, overrides</b></summary>

**One count per request.** Claude Code writes one transcript line per content block, so a single API response can appear on several lines with the same usage. `claude-ledger` counts usage once per `message.id` plus `requestId`, keeps the final usage reported for that message, and also de-duplicates across files, because resumed sessions can copy earlier messages into a new transcript. Lines without a message ID fall back to the entry's `uuid`. Malformed or truncated lines are skipped.

**Main versus subagent.** Entries marked `isSidechain: true`, and everything in a `subagents/` transcript, count as subagent work. The agent type comes from the `agent-*.meta.json` file Claude Code writes next to each subagent transcript; when it is missing the type is shown as `subagent`.

**Token classes.** Each request is priced as

```text
input × input rate
+ output × output rate
+ cache read × cache read rate
+ 5-minute cache write × 1.25 × input rate
+ 1-hour cache write × 2 × input rate
```

When a transcript reports cache writes without the 5-minute/1-hour split, they are treated as 5-minute writes. Cache hit rate is `cache_read / (cache_read + input + cache_write)`.

**Price table.** List prices per million tokens:

| Model | Input | Output | Cache read | Cache write 5m | Cache write 1h |
| --- | ---: | ---: | ---: | ---: | ---: |
| `claude-fable-5-2` | $8.00 | $40.00 | $0.20 | $10.00 | $16.00 |
| `claude-opus-5-5` | $4.00 | $20.00 | $0.20 | $5.00 | $8.00 |
| `claude-sonnet-5-5` | $2.00 | $10.00 | $0.10 | $2.50 | $4.00 |
| `claude-haiku-5-5` | $0.10 | $0.50 | $0.01 | $0.125 | $0.20 |

**Model matching.** Exact ID first, then prefix (`claude-opus-5-5-20261101` uses `claude-opus-5-5`), then family word: any other ID containing `fable`, `opus`, `sonnet` or `haiku`, including older generations such as `claude-opus-4-7` or `claude-3-5-sonnet-20241022` and provider-prefixed IDs, is priced at the current price for that family. The `--by model` table shows which entry each ID was priced as. A model that matches nothing is reported as `unknown`, never as zero.

**Overriding prices.** Pass `--prices FILE` with a JSON file in the same format. Entries replace or add to the bundled table; anything not listed keeps its bundled price.

```json
{
  "models": {
    "claude-opus-4-7": { "input": 5.0, "output": 25.0 },
    "my-gateway-model": { "input": 1.0, "output": 4.0, "cache_read": 0.1 }
  },
  "families": { "opus": "claude-opus-5-5" },
  "cache_write_5m_multiplier": 1.25,
  "cache_write_1h_multiplier": 2.0
}
```

`input` and `output` are required for each model. `cache_read` defaults to 0.1 × input, and `cache_write_5m` and `cache_write_1h` default to the multipliers above; all three can be set explicitly. A flat `{ "model-id": { ... } }` object without the `models` key is accepted too.

</details>

## Privacy

Read-only and fully offline.

- Opens only files under the projects directory you point it at, plus an optional `--prices` file, and never writes to them.
- No network connections: no telemetry, no update checks, no price downloads.
- Reads token counts, model IDs, timestamps, session IDs, working directories and tool names. Prompt and response text is never printed or stored.
- No runtime dependencies, so nothing to audit beyond the Python standard library.

## FAQ

<details>
<summary><b>Why do the numbers differ from my bill?</b></summary>

These are estimates from list prices and the usage in your local transcripts. Your bill can differ because of negotiated or regional pricing, batch or priority tiers, price changes, server-side tools billed separately, requests made outside Claude Code, or deleted transcripts. On a Pro or Max plan you are not billed per token at all: the figures show what the same usage would cost at API list prices, useful for comparing usage, not for reconciling a bill.
</details>

<details>
<summary><b>A model shows as <code>unknown</code>. What do I do?</b></summary>

Its ID did not match any entry or family in the price table. Add it with `--prices FILE`; the run's note lists every unpriced model.
</details>

<details>
<summary><b>Are subagents included?</b></summary>

Yes. Subagent transcripts in nested folders are scanned, counted in the subagent half of the split, and rolled into their parent session in `--by session` and `sessions`.
</details>

<details>
<summary><b>How fast is it on large histories?</b></summary>

Files are streamed line by line and only lines that carry usage, tool results or compaction markers are parsed, so memory stays flat as history grows. In testing on a laptop, synthetic single-file transcripts of 1.8 GB and 2.3 GB took about 6 and 16 seconds, with peak memory under 500 MB; with `--since`, files last modified before the window are skipped without being opened.
</details>

<details>
<summary><b>Which day does a request belong to?</b></summary>

Its local calendar day, from the transcript timestamp. Use `--utc` to group by UTC days.
</details>

## Relation to Claude Code Harness Pro Max

- [Claude Code Harness Pro Max](https://github.com/LiamSDD/claude-code-harness-pro-max) meters cost live inside Claude Code while you work.
- `claude-ledger` is the standalone tool built from the same transcript parsing, usage model and pricing logic.
- It needs no hooks and no configuration, and looks back over your whole history.

## Development

```bash
git clone https://github.com/LiamSDD/claude-ledger
cd claude-ledger
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python3 -m pytest -q
```

Tests use the synthetic transcripts in `tests/fixtures/`; no real user data. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 LiamSDD
