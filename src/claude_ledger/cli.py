from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from . import __version__
from .pricing import PriceError, load_prices
from .render import (
    Style,
    daily_csv,
    daily_json,
    daily_markdown,
    dumps,
    render_daily,
    render_report,
    render_sessions,
    render_tips,
    report_csv,
    report_json,
    report_markdown,
    sessions_csv,
    sessions_json,
    sessions_markdown,
    supports_unicode,
    tips_csv,
    use_color,
)
from .report import DIMENSIONS, Filters, Ledger, build_ledger, parse_when
from .tips import build_tips, tips_json
from .transcripts import projects_root, scan

COMMANDS = ("report", "daily", "sessions", "tips")
VALUE_OPTIONS = {"--dir", "--prices", "--since", "--until", "--project", "--by", "--top"}
TAGLINE = "See where your Claude Code tokens and dollars go."


def _non_negative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a whole number") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def _formats(markdown: bool) -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    fmt = parent.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="machine-readable JSON output")
    fmt.add_argument("--csv", action="store_true", help="CSV output")
    if markdown:
        fmt.add_argument("--markdown", action="store_true", help="GitHub-flavoured Markdown tables for pull requests, issues and chat")
    return parent


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", metavar="PATH", help="projects directory to read (default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects)")
    common.add_argument("--prices", metavar="FILE", help="JSON price table that overrides or extends the bundled one")
    common.add_argument("--project", metavar="PATH|NAME", help="only count one project, by path, folder name or directory name")
    common.add_argument("--until", metavar="WHEN", help="end of the window: 24h, 7d, today, YYYY-MM-DD (inclusive) or YYYY-MM-DDTHH:MM")
    common.add_argument("--utc", action="store_true", help="group days and show times in UTC instead of local time")
    tables = [common, _formats(True)]

    parser = argparse.ArgumentParser(prog="claude-ledger", description=TAGLINE + " Reads local Claude Code transcripts; never sends anything anywhere.")
    parser.add_argument("--version", action="version", version=f"claude-ledger {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    report = sub.add_parser("report", parents=tables, help="totals plus a breakdown table (default command)")
    report.add_argument("--since", metavar="WHEN", help="start of the window: 24h, 7d, 30d, today or YYYY-MM-DD")
    report.add_argument("--by", choices=DIMENSIONS, default="model", help="breakdown dimension (default: model)")
    report.add_argument("--top", type=_non_negative, metavar="N", help="limit the breakdown to N rows (0 = all; tables default to 20)")

    daily = sub.add_parser("daily", parents=tables, help="one row per day with a bar chart of spend")
    daily.add_argument("--since", metavar="WHEN", default="30d", help="start of the window (default: 30d)")

    sessions = sub.add_parser("sessions", parents=tables, help="most expensive sessions")
    sessions.add_argument("--since", metavar="WHEN", help="start of the window")
    sessions.add_argument("--top", type=_non_negative, metavar="N", default=10, help="number of sessions (default: 10, 0 = all)")

    tips = sub.add_parser("tips", parents=[common, _formats(False)], help="savings advice backed by your numbers")
    tips.add_argument("--since", metavar="WHEN", help="start of the window")
    return parser


def normalize_argv(argv: Sequence[str]) -> List[str]:
    args = list(argv)
    skip = False
    for index, token in enumerate(args):
        if skip:
            skip = False
            continue
        if token == "--":
            break
        if token.startswith("-"):
            skip = token in VALUE_OPTIONS
            continue
        if token in COMMANDS:
            return [token] + args[:index] + args[index + 1:]
        return args
    if any(t in ("-h", "--help", "--version") for t in args):
        return args
    return ["report"] + args


def _filters(args: argparse.Namespace, parser: argparse.ArgumentParser, now: datetime) -> Filters:
    tz = timezone.utc if args.utc else None
    try:
        since = parse_when(args.since, now, tz) if args.since else None
        until = parse_when(args.until, now, tz, end=True) if args.until else None
    except ValueError as exc:
        parser.error(str(exc))
    if since and until and since >= until:
        parser.error("--since must be earlier than --until")
    return Filters(since=since, until=until, project=args.project)


def _output(args: argparse.Namespace, ledger: Ledger, style: Style, unicode: bool) -> str:
    if getattr(args, "markdown", False):
        if args.command == "daily":
            return daily_markdown(ledger)
        if args.command == "sessions":
            return sessions_markdown(ledger, args.top or None)
        return report_markdown(ledger, args.by, args.top)
    if args.command == "daily":
        return daily_json(ledger) if args.json else daily_csv(ledger) if args.csv else render_daily(ledger, style, unicode)
    if args.command == "sessions":
        top = args.top or None
        return sessions_json(ledger, top) if args.json else sessions_csv(ledger, top) if args.csv else render_sessions(ledger, top, style)
    if args.command == "tips":
        tips = build_tips(ledger)
        if args.json:
            return dumps({"tips": tips_json(tips), "total_cost_usd": round(ledger.total.cost, 6)})
        return tips_csv(tips) if args.csv else render_tips(ledger, tips, style)
    if args.json:
        return report_json(ledger, args.by, args.top)
    if args.csv:
        return report_csv(ledger, args.by, args.top)
    return render_report(ledger, args.by, args.top, style)


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    now = datetime.now(timezone.utc)
    filters = _filters(args, parser, now)
    root = os.path.expanduser(args.dir) if args.dir else projects_root()
    if not os.path.isdir(root):
        sys.stderr.write(f"claude-ledger: No Claude Code projects directory at {root}. Use --dir PATH or set CLAUDE_CONFIG_DIR.\n")
        return 1
    try:
        prices = load_prices(args.prices)
    except PriceError as exc:
        sys.stderr.write(f"claude-ledger: bad --prices file: {exc}\n")
        return 2
    ledger = build_ledger(scan(root, since=filters.since), prices, filters, timezone.utc if args.utc else None, now)
    out = sys.stdout
    if not ledger.total.usage.requests and not (args.json or args.csv):
        out.write(f"No usage found in {root} for the selected filters.\n")
        return 0
    style = Style(use_color(out, os.environ))
    out.write(_output(args, ledger, style, supports_unicode(out)))
    out.flush()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(argv)
    except BrokenPipeError:
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        return 130
