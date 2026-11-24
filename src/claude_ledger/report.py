from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from typing import Dict, Iterable, List, Optional, Tuple

from .pricing import PriceTable, cost
from .transcripts import Thread, Turn, Usage
from .tips import ThreadFacts, collect_facts

DIMENSIONS = ("model", "project", "day", "session", "agent")
DURATION = re.compile(r"(\d+)\s*([hdw])")


@dataclass
class Bucket:
    usage: Usage = field(default_factory=Usage)
    cost: float = 0.0
    unpriced: int = 0
    first: Optional[datetime] = None
    last: Optional[datetime] = None
    models: Dict[str, float] = field(default_factory=dict)

    def add(self, turn: Turn, turn_cost: Optional[float]) -> None:
        self.usage.add(turn.usage)
        if turn_cost is None:
            self.unpriced += turn.usage.requests
            self.models.setdefault(turn.model, 0.0)
        else:
            self.cost += turn_cost
            self.models[turn.model] = self.models.get(turn.model, 0.0) + turn_cost
        if turn.timestamp:
            self.first = turn.timestamp if self.first is None or turn.timestamp < self.first else self.first
            self.last = turn.timestamp if self.last is None or turn.timestamp > self.last else self.last

    @property
    def priced(self) -> bool:
        return self.usage.requests == 0 or self.unpriced < self.usage.requests

    @property
    def partial(self) -> bool:
        return 0 < self.unpriced < self.usage.requests

    def model_mix(self) -> List[Tuple[str, float]]:
        return sorted(self.models.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass
class Filters:
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    project: Optional[str] = None

    def time_ok(self, stamp: Optional[datetime]) -> bool:
        if self.since is None and self.until is None:
            return True
        if stamp is None:
            return False
        if self.since is not None and stamp < self.since:
            return False
        return not (self.until is not None and stamp >= self.until)

    def turn_ok(self, turn: Turn) -> bool:
        return self.time_ok(turn.timestamp)

    def project_ok(self, thread: Thread) -> bool:
        if not self.project:
            return True
        wanted = self.project.rstrip("/") or "/"
        label = thread.project_label.rstrip("/") or "/"
        if wanted in (thread.project, label, os.path.basename(label)):
            return True
        if "/" in wanted or wanted.startswith((".", "~")):
            path = os.path.abspath(os.path.expanduser(wanted))
            return path == label or re.sub(r"[^A-Za-z0-9]", "-", path) == thread.project
        return False


@dataclass
class SessionRow:
    session: str
    project: str
    bucket: Bucket

    @property
    def start(self) -> Optional[datetime]:
        return self.bucket.first

    @property
    def duration(self) -> Optional[timedelta]:
        if self.bucket.first is None or self.bucket.last is None:
            return None
        return self.bucket.last - self.bucket.first


class Ledger:
    def __init__(self, prices: PriceTable, filters: Filters, tz: Optional[tzinfo], now: Optional[datetime] = None):
        self.prices = prices
        self.filters = filters
        self.tz = tz
        self.now = now or datetime.now().astimezone()
        self.total = Bucket()
        self.main = Bucket()
        self.subagent = Bucket()
        self.groups: Dict[str, Dict[str, Bucket]] = {name: {} for name in DIMENSIONS}
        self.session_projects: Dict[str, str] = {}
        self.unpriced_models: set = set()
        self.files = 0
        self.facts: List[ThreadFacts] = []

    @property
    def sessions_count(self) -> int:
        return len(self.groups["session"])

    def day_of(self, stamp: Optional[datetime]) -> str:
        return stamp.astimezone(self.tz).strftime("%Y-%m-%d") if stamp else "unknown"

    def add_thread(self, thread: Thread) -> None:
        if not self.filters.project_ok(thread):
            return
        turns = [t for t in thread.turns if self.filters.turn_ok(t)]
        if not turns:
            return
        self.files += 1
        costs: List[Optional[float]] = []
        for turn in turns:
            rate = self.prices.lookup(turn.model)
            turn_cost = cost(turn.usage, rate) if rate else None
            costs.append(turn_cost)
            if turn_cost is None:
                self.unpriced_models.add(turn.model)
            keys = {
                "model": turn.model,
                "project": thread.project_label,
                "day": self.day_of(turn.timestamp),
                "session": turn.session,
                "agent": turn.agent,
            }
            for name, key in keys.items():
                self.groups[name].setdefault(key, Bucket()).add(turn, turn_cost)
            self.session_projects.setdefault(turn.session, thread.project_label)
            self.total.add(turn, turn_cost)
            (self.subagent if turn.sidechain else self.main).add(turn, turn_cost)
        self.facts.append(collect_facts(thread, turns, self.prices, self.filters.time_ok))

    def breakdown(self, by: str) -> List[Tuple[str, Bucket]]:
        if by not in self.groups:
            raise ValueError(f"unknown breakdown '{by}', choose from {', '.join(DIMENSIONS)}")
        items = list(self.groups[by].items())
        if by == "day":
            return sorted(items, key=lambda kv: (kv[0] == "unknown", kv[0]))
        return sorted(items, key=lambda kv: (-kv[1].cost, -kv[1].usage.requests, kv[0]))

    def daily(self) -> List[Tuple[str, Bucket]]:
        days = {k: v for k, v in self.groups["day"].items() if k != "unknown"}
        if self.filters.since is not None:
            start: Optional[date] = self.filters.since.astimezone(self.tz).date()
        else:
            start = min((date.fromisoformat(d) for d in days), default=None)
        if self.filters.until is not None:
            end: Optional[date] = (self.filters.until - timedelta(microseconds=1)).astimezone(self.tz).date()
        elif self.filters.since is not None:
            end = self.now.astimezone(self.tz).date()
        else:
            end = max((date.fromisoformat(d) for d in days), default=None)
        if start is None or end is None:
            return []
        out = []
        current = start
        while current <= end:
            key = current.isoformat()
            out.append((key, days.get(key, Bucket())))
            current += timedelta(days=1)
        return out

    def sessions(self, top: Optional[int] = None) -> List[SessionRow]:
        rows = [SessionRow(sid, self.session_projects.get(sid, ""), bucket) for sid, bucket in self.groups["session"].items()]
        rows.sort(key=lambda r: (-r.bucket.cost, -r.bucket.usage.requests, r.session))
        return rows[:top] if top else rows


def build_ledger(threads: Iterable[Thread], prices: PriceTable, filters: Optional[Filters] = None, tz: Optional[tzinfo] = None, now: Optional[datetime] = None) -> Ledger:
    ledger = Ledger(prices, filters or Filters(), tz, now)
    for thread in threads:
        ledger.add_thread(thread)
    return ledger


def _localize(naive: datetime, tz: Optional[tzinfo]) -> datetime:
    return naive.replace(tzinfo=tz) if tz is not None else naive.astimezone()


def parse_when(value: str, now: datetime, tz: Optional[tzinfo], end: bool = False) -> datetime:
    text = (value or "").strip().lower()
    match = DURATION.fullmatch(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        return now - {"h": timedelta(hours=amount), "d": timedelta(days=amount), "w": timedelta(weeks=amount)}[unit]
    if text == "today":
        midnight = _localize(datetime.combine(now.astimezone(tz).date(), datetime.min.time()), tz)
        return midnight + timedelta(days=1) if end else midnight
    for fmt, is_day in (("%Y-%m-%d", True), ("%Y-%m-%dt%H:%M", False), ("%Y-%m-%dt%H:%M:%S", False), ("%Y-%m-%d %H:%M", False)):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        moment = _localize(parsed, tz)
        return moment + timedelta(days=1) if is_day and end else moment
    raise ValueError(f"cannot understand '{value}': use 24h, 7d, 4w, today, YYYY-MM-DD or YYYY-MM-DDTHH:MM")
