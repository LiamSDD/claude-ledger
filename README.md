# claude-ledger

**See where your Claude Code tokens and dollars go.**

A zero-dependency CLI that reads your local Claude Code transcripts and breaks spend down by model, project, day, session and subagent.

[![Python](https://img.shields.io/badge/python-3.9%2B-334155)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/dependencies-0-16a34a)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-334155)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-136%20passing-16a34a)](tests)

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

The output above is real: it is the tool run against the synthetic transcripts in [`tests/fixtures`](tests/fixtures). The full set of example outputs is in [`docs/example-report.txt`](docs/example-report.txt).

## Contents

- [Why](#why)
- [Install](#install)
- [Usage](#usage)
- [How costs are computed](#how-costs-are-computed)
- [Privacy](#privacy)
- [FAQ](#faq)
- [Relation to Claude Code Harness Pro Max](#relation-to-claude-code-harness-pro-max)
- [Development](#development)
- [License](#license)

## Why

Claude Code writes a full transcript of every session to disk, including the exact token usage the API reported for every request. That data answers questions the usage screens do not:

- Which project, day or session actually cost the most?
- How much of the bill is subagents, and which agent types?
- Is prompt caching working, or am I paying full price for the same context again and again?
- Which model IDs did I really use, including dated and older ones?

`claude-ledger` reads those transcripts, counts every request exactly once, prices it from a transparent price table and prints the answer in a few hundred milliseconds. It is a single small Python package with no dependencies, so it installs anywhere Python 3.9 or newer runs.

## Install

With pipx (recommended for CLI tools):

```bash
pipx install git+https://github.com/LiamSDD/claude-ledger
```

With pip:

```bash
pip install git+https://github.com/LiamSDD/claude-ledger
```

Both install a `claude-ledger` command. `python -m claude_ledger` works as well.

## Usage

`report` is the default command, so `claude-ledger` on its own prints the all-time report.

### Options shared by every command

| Option | Meaning |
| --- | --- |
| `--since WHEN` | Start of the window: `24h`, `7d`, `30d`, `4w`, `today`, `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` |
| `--until WHEN` | End of the window, same formats; a plain date includes that whole day |
| `--project PATH\|NAME` | Only one project: its path (`~/code/api`), its folder name (`api`) or its encoded directory name |
| `--dir PATH` | Read another projects directory instead of the default |
| `--prices FILE` | Override or extend the bundled price table (see below) |
| `--utc` | Group days and show times in UTC instead of local time |
| `--json` / `--csv` | Machine-readable output instead of tables |
| `--markdown` | GitHub-flavoured Markdown tables for pull requests, issues and chat (`report`, `daily` and `sessions`) |
| `--version` | Print the version |

By default transcripts are read from `~/.claude/projects`, or from `$CLAUDE_CONFIG_DIR/projects` when `CLAUDE_CONFIG_DIR` is set. Subfolders are scanned recursively, so subagent transcripts are included.

### report

```bash
claude-ledger report [--since 7d] [--until ...] [--project PATH|NAME] [--by model|project|day|session|agent] [--top N] [--json|--csv|--markdown]
```

Totals (requests, input, output, cache read, cache write and estimated cost), the cache hit rate, the split between main sessions and subagents, and one breakdown table:

- `--by model` (default): every raw model ID, with the price-table entry it was priced as.
- `--by project`: one row per working directory.
- `--by day`: one row per calendar day.
- `--by session`: one row per session; subagent work is rolled into its parent session.
- `--by agent`: `main` versus each subagent type (`Explore`, `Plan`, your own agents), read from Claude Code's agent metadata.

Tables show the top 20 rows by default; `--top N` changes that and `--top 0` shows everything. JSON and CSV include every row unless `--top` is given.

### daily

```bash
claude-ledger daily [--since 30d] [--json|--csv|--markdown]
```

One row per day, including days with no usage, with a bar chart of spend:

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

### sessions

```bash
claude-ledger sessions [--top 10] [--json|--csv|--markdown]
```

The most expensive sessions with project, start time, duration, model mix (share of the session's cost per model) and cost.

### tips

```bash
claude-ledger tips [--since 30d]
```

Savings advice derived from your own numbers. Each tip states what was measured and an estimated dollar impact, and a tip only appears when the data supports it (and its impact is at least one cent):

| Tip | Fires when | Estimated impact |
| --- | --- | --- |
| Low prompt-cache hit rate | Under 60% of context tokens came from cache | Cost difference if 85% had been cache reads |
| Read-only subagents on a premium model | `Explore`/`Plan` agents, or agents that only used read-only tools, ran on a model priced above Sonnet | Same tokens repriced at the Sonnet rate |
| Long sessions without compaction | A session passed 150k tokens of context and never compacted | Cache-read cost of the context above 100k on every request |
| Large tool outputs | Tool results over 20k characters entered the context | Cache write of that content plus its re-reads on later requests |

The impacts overlap, so treat them as a ranking, not a sum.

### Output formats

Tables use colour only when stdout is a terminal and `NO_COLOR` is not set; piped output is plain text. `--json` and `--csv` give stable, scriptable output with raw token counts. A model without a known price has `"cost_usd": null` in JSON and an empty cost in CSV.

```bash
claude-ledger --since 30d --by project --csv > spend.csv
claude-ledger --json | jq '.totals.cost_usd'
```

`--markdown` (for `report`, `daily` and `sessions`) prints a short heading, the totals as a bullet list and the table as GitHub-flavoured Markdown, ready to paste into a pull request, issue or chat message. It is mutually exclusive with `--json` and `--csv`, and follows the same row limits as the plain tables. Markdown control characters in values are escaped, and `daily` leaves out the bar chart.

```bash
claude-ledger sessions --top 2 --markdown | pbcopy
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

## How costs are computed

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

**Price table.** List prices per million tokens, bundled in [`src/claude_ledger/prices.json`](src/claude_ledger/prices.json):

| Model | Input | Output | Cache read | Cache write 5m | Cache write 1h |
| --- | ---: | ---: | ---: | ---: | ---: |
| `claude-fable-5-2` | $8.00 | $40.00 | $0.20 | $10.00 | $16.00 |
| `claude-opus-5-5` | $4.00 | $20.00 | $0.20 | $5.00 | $8.00 |
| `claude-sonnet-5-5` | $2.00 | $10.00 | $0.10 | $2.50 | $4.00 |
| `claude-haiku-5-5` | $0.10 | $0.50 | $0.01 | $0.125 | $0.20 |

Model IDs are matched exactly first, then by prefix (so `claude-opus-5-5-20261101` uses the `claude-opus-5-5` price), then by family word: any other ID containing `fable`, `opus`, `sonnet` or `haiku`, including older generations such as `claude-opus-4-7` or `claude-3-5-sonnet-20241022` and provider-prefixed IDs, is priced at the current price for that family. The `--by model` table shows which entry each ID was priced as. A model that matches nothing is reported with cost `unknown` and is never counted as zero: totals carry an asterisk and a note listing the unpriced models.

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

## Privacy

`claude-ledger` is read-only and fully offline.

- It only opens files under the projects directory you point it at, plus an optional `--prices` file, and never writes to them.
- It makes no network connections of any kind: no telemetry, no update checks, no price downloads.
- It reads token counts, model IDs, timestamps, session IDs, working directories and tool names. Prompt and response text is never printed or stored.
- It has no runtime dependencies, so there is no third-party code to audit beyond the Python standard library.

## FAQ

**Why do the numbers differ from my bill?**
These are estimates computed from list prices and the usage recorded in your local transcripts. Your bill can differ because of negotiated or regional pricing, batch or priority tiers, price changes, server-side tools billed separately, requests made outside Claude Code, or transcripts you have deleted. If you use Claude Code through a Pro or Max plan subscription, you are not billed per token at all: the figures show what the same usage would cost at API list prices, which is useful for comparing usage, not for reconciling a bill.

**A model shows as `unknown`. What do I do?**
Its ID did not match any entry or family in the price table. Add it with `--prices FILE`; the run's note lists every unpriced model.

**Are subagents included?**
Yes. Subagent transcripts in nested folders are scanned, counted in the subagent half of the split, and rolled into their parent session in `--by session` and `sessions`.

**How fast is it on large histories?**
Files are streamed line by line and only lines that carry usage, tool results or compaction markers are parsed, so memory stays flat as history grows. In testing on a laptop, synthetic single-file transcripts of 1.8 GB and 2.3 GB took about 6 and 16 seconds, with peak memory under 500 MB; with `--since`, files last modified before the window are skipped without being opened.

**Which day does a request belong to?**
Its local calendar day, from the transcript timestamp. Use `--utc` to group by UTC days.

## Relation to Claude Code Harness Pro Max

[Claude Code Harness Pro Max](https://github.com/LiamSDD/claude-code-harness-pro-max) includes an in-session version of this accounting: it meters cost live inside Claude Code and offers recommendations while you work. `claude-ledger` is the standalone tool built from the same transcript parsing, usage model and pricing logic. It needs no hooks, no installation into Claude Code and no configuration, and is meant for looking back over your whole history.

## Development

```bash
git clone https://github.com/LiamSDD/claude-ledger
cd claude-ledger
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python3 -m pytest -q
```

The tests run against synthetic transcripts in `tests/fixtures/`; no real user data is used. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 LiamSDD
