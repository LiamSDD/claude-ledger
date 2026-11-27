from __future__ import annotations

import csv
import io
import json
import os
import re
import textwrap
from datetime import datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence

if TYPE_CHECKING:
    from .report import Bucket, Ledger, SessionRow
    from .tips import Tip

BLOCKS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
FULL_BLOCK = "█"
GAP = "   "
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LABELS = {"model": "Model", "project": "Project", "day": "Day", "session": "Session", "agent": "Agent"}
DEFAULT_TABLE_ROWS = 20


class Style:
    def __init__(self, color: bool):
        self.color = color

    def _wrap(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.color and text else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def accent(self, text: str) -> str:
        return self._wrap("36", text)


def use_color(stream: Any, env: Mapping[str, str]) -> bool:
    if "NO_COLOR" in env:
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def supports_unicode(stream: Any) -> bool:
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        (FULL_BLOCK + BLOCKS[1]).encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def money(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value == 0 or abs(value) >= 0.01:
        return f"${value:,.2f}"
    return f"${value:.4f}"


def tokens(n: float) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


def pct(fraction: float) -> str:
    return f"{fraction * 100:.1f}%"


def short_model(model: str) -> str:
    name = model[len("claude-"):] if model.startswith("claude-") else model
    return re.sub(r"-\d{8}$", "", name)


def short_path(path: str, width: int = 48) -> str:
    home = os.path.expanduser("~")
    if home and home != "/" and (path == home or path.startswith(home + os.sep)):
        path = "~" + path[len(home):]
    return path if len(path) <= width else "..." + path[-(width - 3):]


def cost_cell(bucket: "Bucket") -> str:
    if not bucket.priced:
        return "unknown"
    return money(bucket.cost) + ("*" if bucket.partial else "")


def bar(value: float, maximum: float, width: int, unicode: bool = True) -> str:
    if maximum <= 0 or value <= 0:
        return ""
    units = min(value / maximum, 1.0) * width
    full = int(units)
    if not unicode:
        return "#" * max(full, 1)
    part = BLOCKS[int((units - full) * 8)]
    text = FULL_BLOCK * full + part
    return text or BLOCKS[1]


def visible_len(text: str) -> int:
    return len(ANSI.sub("", text))


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], aligns: Sequence[str], style: Style, bold_last: bool = False) -> str:
    widths = [max([visible_len(h)] + [visible_len(r[i]) for r in rows]) for i, h in enumerate(headers)]

    def line(cells: Sequence[str]) -> str:
        parts = []
        for cell, width, align in zip(cells, widths, aligns):
            pad = " " * (width - visible_len(cell))
            parts.append(pad + cell if align == "r" else cell + pad)
        return GAP.join(parts).rstrip()

    out = [style.bold(line(headers)), style.dim(GAP.join("-" * w for w in widths))]
    for index, row in enumerate(rows):
        text = line(row)
        out.append(style.bold(text) if bold_last and index == len(rows) - 1 else text)
    return "\n".join(out)


def _range_text(ledger: "Ledger") -> str:
    tz = ledger.tz
    start = ledger.filters.since or ledger.total.first
    end = ledger.filters.until - timedelta(microseconds=1) if ledger.filters.until else ledger.total.last
    if start is None or end is None:
        return "all time"
    return f"{start.astimezone(tz):%Y-%m-%d} to {end.astimezone(tz):%Y-%m-%d}"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def _scope(ledger: "Ledger", date_range: Optional[str] = None) -> str:
    scope = f"{date_range or _range_text(ledger)}, {_plural(ledger.sessions_count, 'session')}, {_plural(ledger.files, 'transcript file')}"
    if ledger.filters.project:
        scope += f", project {ledger.filters.project}"
    return scope


def header(ledger: "Ledger", style: Style, date_range: Optional[str] = None) -> str:
    title = style.bold("Claude Code usage")
    return f"{title}  {style.dim(_scope(ledger, date_range))}"


def _unpriced_note(ledger: "Ledger") -> List[str]:
    if not ledger.total.unpriced:
        return []
    models = ", ".join(sorted(ledger.unpriced_models))
    return ["", f"* Costs exclude {_plural(ledger.total.unpriced, 'request')} on models with no known price: {models}. Add them with --prices FILE."]


def render_summary(ledger: "Ledger", style: Style) -> List[str]:
    total = ledger.total
    usage = total.usage
    cost_text = cost_cell(total)
    pairs = [
        ("Estimated cost", style.accent(cost_text)),
        ("Requests", f"{usage.requests:,}"),
        ("Input tokens", tokens(usage.input)),
        ("Output tokens", tokens(usage.output)),
        ("Cache read", tokens(usage.cache_read)),
        ("Cache write", f"{tokens(usage.cache_write)}  ({tokens(usage.cache_write_5m)} 5m, {tokens(usage.cache_write_1h)} 1h)"),
        ("Cache hit rate", pct(usage.cache_hit_rate)),
    ]
    lines = [f"  {label:<16}{value}" for label, value in pairs]
    lines.append("")
    for label, bucket in (("Main sessions", ledger.main), ("Subagents", ledger.subagent)):
        share = bucket.cost / total.cost if total.cost else 0.0
        lines.append(f"  {label:<16}{cost_cell(bucket):<12}{pct(share):>6}  {style.dim(_plural(bucket.usage.requests, 'request'))}")
    return lines


def _key_text(by: str, key: str) -> str:
    if by == "project":
        return short_path(key)
    if by == "session":
        return key[:8]
    return key


def render_report(ledger: "Ledger", by: str, top: Optional[int], style: Style) -> str:
    rows = ledger.breakdown(by)
    limit = DEFAULT_TABLE_ROWS if top is None else top
    shown = rows[:limit] if limit else rows
    total_cost = ledger.total.cost
    headers = [LABELS[by], "Requests", "Input", "Output", "Cache read", "Cache write", "Cost", "Share"]
    aligns = ["l", "r", "r", "r", "r", "r", "r", "r"]
    if by == "model":
        headers.insert(1, "Priced as")
        aligns.insert(1, "l")
    body = []
    for key, bucket in shown:
        u = bucket.usage
        share = pct(bucket.cost / total_cost) if total_cost and bucket.priced else "-"
        cells = [_key_text(by, key), f"{u.requests:,}", tokens(u.input), tokens(u.output), tokens(u.cache_read), tokens(u.cache_write), cost_cell(bucket), share]
        if by == "model":
            cells.insert(1, ledger.prices.resolve(key) or "unknown")
        body.append(cells)
    lines = [header(ledger, style), ""] + render_summary(ledger, style)
    lines += ["", style.bold(f"By {by}"), table(headers, body, aligns, style)]
    if len(shown) < len(rows):
        lines.append(style.dim(f"  ... {len(rows) - len(shown)} more (use --top 0 to show all)"))
    lines += _unpriced_note(ledger)
    return "\n".join(lines) + "\n"


def bucket_dict(bucket: "Bucket") -> Dict[str, Any]:
    u = bucket.usage
    return {
        "requests": u.requests,
        "input_tokens": u.input,
        "output_tokens": u.output,
        "cache_read_tokens": u.cache_read,
        "cache_write_tokens": u.cache_write,
        "cache_write_5m_tokens": u.cache_write_5m,
        "cache_write_1h_tokens": u.cache_write_1h,
        "cache_hit_rate": round(u.cache_hit_rate, 4),
        "cost_usd": round(bucket.cost, 6) if bucket.priced else None,
        "unpriced_requests": bucket.unpriced,
    }


def _iso(stamp: Optional[datetime], tz: Optional[tzinfo]) -> Optional[str]:
    return stamp.astimezone(tz).isoformat() if stamp else None


def _envelope(ledger: "Ledger") -> Dict[str, Any]:
    totals = bucket_dict(ledger.total)
    totals.update({"sessions": ledger.sessions_count, "files": ledger.files})
    return {
        "range": {"since": _iso(ledger.filters.since, ledger.tz), "until": _iso(ledger.filters.until, ledger.tz)},
        "project": ledger.filters.project,
        "totals": totals,
        "split": {"main": bucket_dict(ledger.main), "subagent": bucket_dict(ledger.subagent)},
        "unpriced_models": sorted(ledger.unpriced_models),
    }


def dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2) + "\n"


def report_json(ledger: "Ledger", by: str, top: Optional[int]) -> str:
    rows = ledger.breakdown(by)
    rows = rows[:top] if top else rows
    data = _envelope(ledger)
    data["by"] = by
    data["rows"] = [dict(key=key, **bucket_dict(bucket)) for key, bucket in rows]
    if by == "model":
        for row in data["rows"]:
            row["priced_as"] = ledger.prices.resolve(row["key"])
    return dumps(data)


CSV_FIELDS = ["requests", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_5m_tokens", "cache_write_1h_tokens", "cost_usd", "unpriced_requests"]


CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


class _SafeWriter:
    def __init__(self, buffer: io.StringIO) -> None:
        self._writer = csv.writer(buffer, lineterminator="\n")

    def writerow(self, row: List[Any]) -> None:
        self._writer.writerow([csv_safe(cell) for cell in row])

    def writerows(self, rows: List[List[Any]]) -> None:
        for row in rows:
            self.writerow(row)


def _csv(first: str, rows: List[List[Any]]) -> str:
    buffer = io.StringIO()
    writer = _SafeWriter(buffer)
    writer.writerow([first] + CSV_FIELDS)
    writer.writerows(rows)
    return buffer.getvalue()


def _csv_cells(bucket: "Bucket") -> List[Any]:
    data = bucket_dict(bucket)
    return ["" if data[f] is None else data[f] for f in CSV_FIELDS]


def report_csv(ledger: "Ledger", by: str, top: Optional[int]) -> str:
    rows = ledger.breakdown(by)
    rows = rows[:top] if top else rows
    return _csv(by, [[key] + _csv_cells(bucket) for key, bucket in rows])


def render_daily(ledger: "Ledger", style: Style, unicode: bool = True, width: int = 32) -> str:
    days = ledger.daily()
    peak = max((b.cost for _, b in days), default=0.0)
    body = []
    for day, bucket in days:
        u = bucket.usage
        cost_text = cost_cell(bucket) if u.requests else style.dim("-")
        body.append([day, f"{u.requests:,}" if u.requests else "-", tokens(u.input + u.output + u.cache_read + u.cache_write) if u.requests else "-", cost_text, style.accent(bar(bucket.cost, peak, width, unicode))])
    total = ledger.total
    body.append(["Total", f"{total.usage.requests:,}", tokens(total.usage.input + total.usage.output + total.usage.cache_read + total.usage.cache_write), cost_cell(total), ""])
    date_range = f"{days[0][0]} to {days[-1][0]}" if days else None
    lines = [header(ledger, style, date_range), "", table(["Day", "Requests", "Tokens", "Cost", "Spend"], body, ["l", "r", "r", "r", "l"], style, bold_last=True)]
    active = [b.cost for _, b in days if b.usage.requests]
    if active:
        lines += ["", style.dim(f"  {len(active)} active day(s), average {money(sum(active) / len(active))} per active day, peak {money(peak)}")]
    lines += _unpriced_note(ledger)
    return "\n".join(lines) + "\n"


def daily_json(ledger: "Ledger") -> str:
    data = _envelope(ledger)
    data["days"] = [dict(day=day, **bucket_dict(bucket)) for day, bucket in ledger.daily()]
    return dumps(data)


def daily_csv(ledger: "Ledger") -> str:
    return _csv("day", [[day] + _csv_cells(bucket) for day, bucket in ledger.daily()])


def duration_text(delta: Optional[timedelta]) -> str:
    if delta is None:
        return "-"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "<1m"
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days}d {hours:02d}h"
    if hours:
        return f"{hours}h {mins:02d}m"
    return f"{mins}m"


def model_mix_text(bucket: "Bucket") -> str:
    mix = bucket.model_mix()
    total = bucket.cost
    parts = []
    for model, value in mix[:2]:
        parts.append(f"{short_model(model)} {value / total:.0%}" if total and value else short_model(model))
    if len(mix) > 2:
        parts.append(f"+{len(mix) - 2}")
    return ", ".join(parts)


def render_sessions(ledger: "Ledger", top: Optional[int], style: Style) -> str:
    rows = ledger.sessions(top)
    body = []
    for row in rows:
        start = f"{row.start.astimezone(ledger.tz):%Y-%m-%d %H:%M}" if row.start else "-"
        body.append([row.session[:8], short_path(row.project, 36), start, duration_text(row.duration), model_mix_text(row.bucket), f"{row.bucket.usage.requests:,}", cost_cell(row.bucket)])
    title = f"Most expensive sessions (top {len(rows)} of {ledger.sessions_count})"
    lines = [header(ledger, style), "", style.bold(title)]
    lines.append(table(["Session", "Project", "Start", "Duration", "Models", "Requests", "Cost"], body, ["l", "l", "l", "r", "l", "r", "r"], style))
    lines += _unpriced_note(ledger)
    return "\n".join(lines) + "\n"


def sessions_json(ledger: "Ledger", top: Optional[int]) -> str:
    data = _envelope(ledger)
    data["sessions"] = [
        dict(
            session=row.session,
            project=row.project,
            start=_iso(row.start, ledger.tz),
            end=_iso(row.bucket.last, ledger.tz),
            duration_seconds=int(row.duration.total_seconds()) if row.duration is not None else None,
            models={m: round(c, 6) for m, c in row.bucket.model_mix()},
            **bucket_dict(row.bucket),
        )
        for row in ledger.sessions(top)
    ]
    return dumps(data)


def sessions_csv(ledger: "Ledger", top: Optional[int]) -> str:
    buffer = io.StringIO()
    writer = _SafeWriter(buffer)
    writer.writerow(["session", "project", "start", "duration_seconds", "models"] + CSV_FIELDS)
    for row in ledger.sessions(top):
        writer.writerow([row.session, row.project, _iso(row.start, ledger.tz) or "", int(row.duration.total_seconds()) if row.duration is not None else "", " ".join(m for m, _ in row.bucket.model_mix())] + _csv_cells(row.bucket))
    return buffer.getvalue()


def render_tips(ledger: "Ledger", tips: List["Tip"], style: Style, width: int = 96) -> str:
    lines = [header(ledger, style), ""]
    if not tips:
        lines.append("No savings advice: nothing in this usage stands out as wasteful.")
        return "\n".join(lines) + "\n"
    lines.append(style.bold(f"Savings advice for {cost_cell(ledger.total)} of spend, largest estimated impact first"))
    for index, tip in enumerate(tips, 1):
        lines += ["", f"{index}. {style.bold(tip.title)}  {style.accent('~' + money(tip.saving))}"]
        lines += textwrap.wrap(tip.detail, width, initial_indent="   ", subsequent_indent="   ")
        lines += textwrap.wrap("Fix: " + tip.fix, width, initial_indent="   ", subsequent_indent="        ")
    lines += ["", style.dim("Impacts are estimates from list prices; they overlap and should not be summed exactly.")]
    return "\n".join(lines) + "\n"


def tips_csv(tips: List["Tip"]) -> str:
    buffer = io.StringIO()
    writer = _SafeWriter(buffer)
    writer.writerow(["key", "title", "saving_usd", "detail", "fix"])
    for tip in tips:
        writer.writerow([tip.key, tip.title, round(tip.saving, 6), tip.detail, tip.fix])
    return buffer.getvalue()


MD_SPECIAL = re.compile(r"([\\|*_`<>\[\]])")


def md_cell(text: str) -> str:
    return MD_SPECIAL.sub(r"\\\1", " ".join(str(text).splitlines()))


def md_table(headers: Sequence[str], rows: Sequence[Sequence[str]], aligns: Sequence[str], bold_last: bool = False) -> str:
    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    out = [line([md_cell(h) for h in headers]), line(["---:" if a == "r" else ":---" for a in aligns])]
    for index, row in enumerate(rows):
        cells = [md_cell(c) for c in row]
        if bold_last and index == len(rows) - 1:
            cells = [f"**{c}**" if c else c for c in cells]
        out.append(line(cells))
    return "\n".join(out)


def _md_list(pairs: Sequence[Sequence[str]]) -> List[str]:
    return [f"- **{md_cell(label)}:** {md_cell(value)}" for label, value in pairs]


def _md_header(ledger: "Ledger", date_range: Optional[str] = None) -> List[str]:
    return ["## Claude Code usage", "", md_cell(_scope(ledger, date_range))]


def _md_unpriced(ledger: "Ledger") -> List[str]:
    return [md_cell(line) for line in _unpriced_note(ledger)]


def _md_summary(ledger: "Ledger") -> List[str]:
    total = ledger.total
    usage = total.usage
    pairs = [
        ("Estimated cost", cost_cell(total)),
        ("Requests", f"{usage.requests:,}"),
        ("Input tokens", tokens(usage.input)),
        ("Output tokens", tokens(usage.output)),
        ("Cache read", tokens(usage.cache_read)),
        ("Cache write", f"{tokens(usage.cache_write)} ({tokens(usage.cache_write_5m)} 5m, {tokens(usage.cache_write_1h)} 1h)"),
        ("Cache hit rate", pct(usage.cache_hit_rate)),
    ]
    for label, bucket in (("Main sessions", ledger.main), ("Subagents", ledger.subagent)):
        share = bucket.cost / total.cost if total.cost else 0.0
        pairs.append((label, f"{cost_cell(bucket)} ({pct(share)}, {_plural(bucket.usage.requests, 'request')})"))
    return _md_list(pairs)


def report_markdown(ledger: "Ledger", by: str, top: Optional[int]) -> str:
    rows = ledger.breakdown(by)
    limit = DEFAULT_TABLE_ROWS if top is None else top
    shown = rows[:limit] if limit else rows
    total_cost = ledger.total.cost
    headers = [LABELS[by], "Requests", "Input", "Output", "Cache read", "Cache write", "Cost", "Share"]
    aligns = ["l", "r", "r", "r", "r", "r", "r", "r"]
    if by == "model":
        headers.insert(1, "Priced as")
        aligns.insert(1, "l")
    body = []
    for key, bucket in shown:
        u = bucket.usage
        share = pct(bucket.cost / total_cost) if total_cost and bucket.priced else "-"
        cells = [_key_text(by, key), f"{u.requests:,}", tokens(u.input), tokens(u.output), tokens(u.cache_read), tokens(u.cache_write), cost_cell(bucket), share]
        if by == "model":
            cells.insert(1, ledger.prices.resolve(key) or "unknown")
        body.append(cells)
    lines = _md_header(ledger) + [""] + _md_summary(ledger)
    lines += ["", f"### By {by}", "", md_table(headers, body, aligns)]
    if len(shown) < len(rows):
        lines += ["", md_cell(f"... {len(rows) - len(shown)} more (use --top 0 to show all)")]
    lines += _md_unpriced(ledger)
    return "\n".join(lines) + "\n"


def daily_markdown(ledger: "Ledger") -> str:
    days = ledger.daily()
    body = []
    for day, bucket in days:
        u = bucket.usage
        if u.requests:
            body.append([day, f"{u.requests:,}", tokens(u.input + u.output + u.cache_read + u.cache_write), cost_cell(bucket)])
        else:
            body.append([day, "-", "-", "-"])
    total = ledger.total
    body.append(["Total", f"{total.usage.requests:,}", tokens(total.usage.input + total.usage.output + total.usage.cache_read + total.usage.cache_write), cost_cell(total)])
    date_range = f"{days[0][0]} to {days[-1][0]}" if days else None
    lines = _md_header(ledger, date_range) + ["", md_table(["Day", "Requests", "Tokens", "Cost"], body, ["l", "r", "r", "r"], bold_last=True)]
    active = [b.cost for _, b in days if b.usage.requests]
    if active:
        pairs = [
            ("Active days", f"{len(active):,}"),
            ("Average per active day", money(sum(active) / len(active))),
            ("Peak day", money(max(active))),
        ]
        lines += [""] + _md_list(pairs)
    lines += _md_unpriced(ledger)
    return "\n".join(lines) + "\n"


def sessions_markdown(ledger: "Ledger", top: Optional[int]) -> str:
    rows = ledger.sessions(top)
    body = []
    for row in rows:
        start = f"{row.start.astimezone(ledger.tz):%Y-%m-%d %H:%M}" if row.start else "-"
        body.append([row.session[:8], short_path(row.project, 36), start, duration_text(row.duration), model_mix_text(row.bucket), f"{row.bucket.usage.requests:,}", cost_cell(row.bucket)])
    lines = _md_header(ledger) + ["", f"### Most expensive sessions (top {len(rows)} of {ledger.sessions_count})", ""]
    lines.append(md_table(["Session", "Project", "Start", "Duration", "Models", "Requests", "Cost"], body, ["l", "l", "l", "r", "l", "r", "r"]))
    lines += _md_unpriced(ledger)
    return "\n".join(lines) + "\n"
