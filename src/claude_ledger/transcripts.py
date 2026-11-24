from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

USAGE_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "requests")
TIMESTAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?$")
MARKERS = (b'"usage"', b'"tool_result"', b"compact")
LARGE_OUTPUT_CHARS = 20_000
ESCAPES = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]|(?:\x1b[\]PX^_]|[\x90\x98\x9d\x9e\x9f])[^\x07\x1b\x9c]*(?:\x07|\x1b\\|\x9c)?|\x1b[ -/]*[0-~]")
CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    requests: int = 0

    def add(self, other: "Usage") -> None:
        for name in USAGE_FIELDS:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def cache_write(self) -> int:
        return self.cache_write_5m + self.cache_write_1h

    @property
    def context(self) -> int:
        return self.input + self.cache_read + self.cache_write

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_read / self.context if self.context else 0.0


@dataclass
class Turn:
    key: str
    model: str
    timestamp: Optional[datetime]
    session: str
    agent: str
    sidechain: bool
    usage: Usage
    ordinal: int
    tools: Tuple[str, ...] = ()


@dataclass
class ToolOutput:
    chars: int
    ordinal: int
    timestamp: Optional[datetime]


@dataclass
class Thread:
    path: str
    project: str
    project_label: str
    session: str
    agent: str
    subagent: bool
    compacted: bool = False
    turns: List[Turn] = field(default_factory=list)
    outputs: List[ToolOutput] = field(default_factory=list)


def clean_text(value: str) -> str:
    return CONTROLS.sub("", ESCAPES.sub("", value))


def projects_root() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def find_transcripts(root: str) -> List[str]:
    found: List[str] = []
    for current, dirs, files in os.walk(root):
        dirs.sort()
        found.extend(os.path.join(current, name) for name in files if name.endswith(".jsonl"))
    return sorted(found)


def iter_entries(path: str) -> Iterator[Dict[str, Any]]:
    yield from (entry for _, entry in _iter_relevant(path, ()))


def _iter_relevant(path: str, markers: Tuple[bytes, ...]) -> Iterator[Tuple[int, Dict[str, Any]]]:
    try:
        with open(path, "rb") as fh:
            for number, raw in enumerate(fh):
                if markers and not any(m in raw for m in markers):
                    continue
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    yield number, entry
    except OSError:
        return


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def usage_from(raw: Dict[str, Any]) -> Usage:
    usage = Usage(requests=1)
    usage.input = _int(raw.get("input_tokens"))
    usage.output = _int(raw.get("output_tokens"))
    usage.cache_read = _int(raw.get("cache_read_input_tokens"))
    creation = raw.get("cache_creation")
    if isinstance(creation, dict) and ("ephemeral_5m_input_tokens" in creation or "ephemeral_1h_input_tokens" in creation):
        usage.cache_write_5m = _int(creation.get("ephemeral_5m_input_tokens"))
        usage.cache_write_1h = _int(creation.get("ephemeral_1h_input_tokens"))
    else:
        usage.cache_write_5m = _int(raw.get("cache_creation_input_tokens"))
    return usage


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    match = TIMESTAMP.match(value.strip())
    if not match:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    try:
        stamp = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second or 0), int((fraction or "0")[:6].ljust(6, "0")))
    except ValueError:
        return None
    if not zone or zone == "Z":
        return stamp.replace(tzinfo=timezone.utc)
    sign = 1 if zone[0] == "+" else -1
    digits = zone[1:].replace(":", "")
    offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return (stamp - sign * offset).replace(tzinfo=timezone.utc)


def _output_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(block["text"]) for block in content if isinstance(block, dict) and isinstance(block.get("text"), str))
    return 0


def _agent_type(path: str) -> str:
    meta = path[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return "subagent"
    kind = data.get("agentType") if isinstance(data, dict) else None
    kind = clean_text(kind) if isinstance(kind, str) else ""
    return kind or "subagent"


def read_thread(path: str, root: str) -> Thread:
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    project = parts[0] if len(parts) > 1 else "(root)"
    subagent = "subagents" in parts[1:-1] or parts[-1].startswith("agent-")
    stem = os.path.splitext(parts[-1])[0]
    thread = Thread(path, project, "", "", _agent_type(path) if subagent else "main", subagent)
    turns: Dict[str, Turn] = {}
    for number, entry in _iter_relevant(path, MARKERS):
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary" or entry.get("isCompactSummary"):
            thread.compacted = True
        if not thread.session and isinstance(entry.get("sessionId"), str):
            thread.session = clean_text(entry["sessionId"])
        if not thread.project_label and isinstance(entry.get("cwd"), str):
            thread.project_label = clean_text(entry["cwd"])
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        kind = entry.get("type")
        if kind == "assistant":
            _add_turn(thread, turns, entry, message, number)
        elif kind == "user" and isinstance(message.get("content"), list):
            for block in message["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    chars = _output_chars(block.get("content"))
                    if chars >= LARGE_OUTPUT_CHARS:
                        thread.outputs.append(ToolOutput(chars, len(turns), parse_timestamp(entry.get("timestamp"))))
    thread.session = thread.session or clean_text(stem)
    thread.project_label = thread.project_label or clean_text(project)
    thread.turns = list(turns.values())
    return thread


def _add_turn(thread: Thread, turns: Dict[str, Turn], entry: Dict[str, Any], message: Dict[str, Any], number: int) -> None:
    raw = message.get("usage")
    model = message.get("model")
    if not isinstance(raw, dict) or model == "<synthetic>":
        return
    tools = tuple(str(b.get("name")) for b in message.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_use")
    if message.get("id"):
        key = f"{message['id']}:{entry.get('requestId') or ''}"
    elif entry.get("uuid"):
        key = f"uuid:{entry['uuid']}"
    else:
        key = f"line:{thread.path}:{number}"
    existing = turns.get(key)
    if existing:
        existing.usage = usage_from(raw)
        existing.tools = existing.tools + tools
        return
    sidechain = thread.subagent or bool(entry.get("isSidechain"))
    agent = thread.agent if thread.subagent else ("subagent" if sidechain else "main")
    session = clean_text(entry["sessionId"]) if isinstance(entry.get("sessionId"), str) else ""
    turns[key] = Turn(key, clean_text(str(model or "unknown")) or "unknown", parse_timestamp(entry.get("timestamp")), session, agent, sidechain, usage_from(raw), len(turns), tools)


def scan(root: str, since: Optional[datetime] = None) -> Iterator[Thread]:
    seen: Set[str] = set()
    cutoff = since.timestamp() if since else None
    for path in find_transcripts(root):
        if cutoff is not None:
            try:
                if os.path.getmtime(path) < cutoff:
                    continue
            except OSError:
                continue
        thread = read_thread(path, root)
        fresh = []
        for turn in thread.turns:
            if turn.key in seen:
                continue
            seen.add(turn.key)
            turn.session = turn.session or thread.session
            fresh.append(turn)
        thread.turns = fresh
        yield thread
