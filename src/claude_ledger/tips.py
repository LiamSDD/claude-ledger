from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set

from .pricing import MTOK, PriceTable, Rate, cost
from .render import money, short_model, tokens
from .transcripts import LARGE_OUTPUT_CHARS, Thread, Turn

if TYPE_CHECKING:
    from .report import Ledger

READ_ONLY_TOOLS = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead", "TodoWrite", "TodoRead", "BashOutput", "ListMcpResourcesTool", "ReadMcpResourceTool"}
EXPLORATION_AGENTS = {"explore", "plan"}
TARGET_HIT_RATE = 0.85
LOW_HIT_RATE = 0.6
MIN_CONTEXT_FOR_CACHE_TIP = 50_000
LONG_CONTEXT = 150_000
HEALTHY_CONTEXT = 100_000
CHARS_PER_TOKEN = 4
MIN_SAVING = 0.01


@dataclass
class Tip:
    key: str
    title: str
    detail: str
    fix: str
    saving: float


@dataclass
class ThreadFacts:
    session: str
    agent: str
    subagent: bool
    compacted: bool
    peak_context: int = 0
    excess_cost: float = 0.0
    tools: Set[str] = field(default_factory=set)
    premium_models: Set[str] = field(default_factory=set)
    premium_cost: float = 0.0
    repriced_cost: float = 0.0
    large_outputs: int = 0
    largest_output: int = 0
    output_cost: float = 0.0


def collect_facts(thread: Thread, turns: List[Turn], prices: PriceTable, time_ok: Callable[[Optional[datetime]], bool]) -> ThreadFacts:
    facts = ThreadFacts(thread.session, thread.agent, thread.subagent, thread.compacted)
    reference = prices.family_rate("sonnet")
    context_turns = [t for t in turns if thread.subagent or not t.sidechain]
    for turn in turns:
        facts.tools.update(turn.tools)
        rate = prices.lookup(turn.model)
        if thread.subagent and rate and reference and rate.output > reference.output:
            facts.premium_models.add(turn.model)
            facts.premium_cost += cost(turn.usage, rate)
            facts.repriced_cost += cost(turn.usage, reference)
    for turn in context_turns:
        rate = prices.lookup(turn.model)
        context = turn.usage.context
        facts.peak_context = max(facts.peak_context, context)
        if rate and context > HEALTHY_CONTEXT:
            facts.excess_cost += (context - HEALTHY_CONTEXT) * rate.cache_read / MTOK
    ordinals = [t.ordinal for t in context_turns]
    for output in thread.outputs:
        if output.chars < LARGE_OUTPUT_CHARS or not time_ok(output.timestamp):
            continue
        split = bisect.bisect_left(ordinals, output.ordinal)
        later = len(ordinals) - split
        nearest = context_turns[split - 1] if split else (context_turns[split] if later else None)
        rate = _rate_for(nearest, prices)
        if rate is None:
            continue
        facts.large_outputs += 1
        facts.largest_output = max(facts.largest_output, output.chars)
        facts.output_cost += output.chars / CHARS_PER_TOKEN * (rate.cache_write_5m + later * rate.cache_read) / MTOK
    return facts


def _rate_for(turn: Optional[Turn], prices: PriceTable) -> Optional[Rate]:
    return prices.lookup(turn.model) if turn else None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _cache_tip(ledger: "Ledger") -> Optional[Tip]:
    usage = ledger.total.usage
    if usage.context < MIN_CONTEXT_FOR_CACHE_TIP or usage.cache_hit_rate >= LOW_HIT_RATE:
        return None
    saving = 0.0
    for model, bucket in ledger.groups["model"].items():
        rate = ledger.prices.lookup(model)
        if not rate:
            continue
        u = bucket.usage
        moved = min(u.input + u.cache_write, max(0.0, TARGET_HIT_RATE * u.context - u.cache_read))
        saving += moved * max(0.0, rate.input - rate.cache_read) / MTOK
    return Tip(
        "cache-hit-rate",
        "Low prompt-cache hit rate",
        f"Only {usage.cache_hit_rate:.0%} of context tokens were served from cache ({tokens(usage.cache_read)} of {tokens(usage.context)}). "
        f"Well-cached Claude Code sessions reach 85-95%; at {TARGET_HIT_RATE:.0%} the same work would cost about {money(saving)} less.",
        "Keep CLAUDE.md, settings and MCP servers stable during a session, avoid switching models mid-task, and continue long tasks with --continue instead of starting fresh sessions.",
        saving,
    )


def _exploration_tip(ledger: "Ledger") -> Optional[Tip]:
    hits = [f for f in ledger.facts if f.subagent and f.premium_cost > 0 and (f.agent.lower() in EXPLORATION_AGENTS or (f.tools and f.tools <= READ_ONLY_TOOLS))]
    if not hits:
        return None
    premium = sum(f.premium_cost for f in hits)
    repriced = sum(f.repriced_cost for f in hits)
    saving = premium - repriced
    agents = ", ".join(sorted({f.agent for f in hits}))
    models = ", ".join(sorted({short_model(m) for f in hits for m in f.premium_models}))
    reference = ledger.prices.families.get("sonnet", "sonnet")
    return Tip(
        "premium-exploration",
        "Read-only subagents run on a premium model",
        f"{_plural(len(hits), 'read-only subagent run')} ({agents}) cost {money(premium)} on {models}. "
        f"The same tokens on {short_model(reference)} would cost {money(repriced)}.",
        "Add `model: sonnet` (or `model: haiku`) to the frontmatter of exploration and research agents in .claude/agents/, or set CLAUDE_CODE_SUBAGENT_MODEL.",
        saving,
    )


def _long_session_tip(ledger: "Ledger") -> Optional[Tip]:
    hits = [f for f in ledger.facts if not f.subagent and not f.compacted and f.peak_context >= LONG_CONTEXT]
    if not hits:
        return None
    saving = sum(f.excess_cost for f in hits)
    peak = max(f.peak_context for f in hits)
    return Tip(
        "long-sessions",
        "Long sessions without compaction",
        f"{_plural(len(hits), 'session')} grew past {LONG_CONTEXT // 1000}k tokens of context without compacting (peak {tokens(peak)}). "
        f"Every request re-reads the whole context; the part above {HEALTHY_CONTEXT // 1000}k cost {money(saving)} in cache reads alone.",
        "Run /compact at natural breakpoints, /clear between unrelated tasks, and compact earlier with CLAUDE_AUTOCOMPACT_PCT_OVERRIDE.",
        saving,
    )


def _large_output_tip(ledger: "Ledger") -> Optional[Tip]:
    count = sum(f.large_outputs for f in ledger.facts)
    if not count:
        return None
    saving = sum(f.output_cost for f in ledger.facts)
    largest = max(f.largest_output for f in ledger.facts)
    return Tip(
        "large-outputs",
        "Large tool outputs in context",
        f"{_plural(count, 'tool result')} over {LARGE_OUTPUT_CHARS // 1000}k characters (largest {tokens(largest)} chars) entered the context. "
        f"Caching that content and re-reading it on later requests cost about {money(saving)}.",
        "Search before reading (Grep, then Read with offset/limit), pipe noisy commands through head or tail, and lower BASH_MAX_OUTPUT_LENGTH.",
        saving,
    )


def build_tips(ledger: "Ledger") -> List[Tip]:
    if not ledger.total.usage.requests:
        return []
    builders = (_cache_tip, _exploration_tip, _long_session_tip, _large_output_tip)
    tips = [tip for tip in (build(ledger) for build in builders) if tip and tip.saving >= MIN_SAVING]
    return sorted(tips, key=lambda t: -t.saving)


def tips_json(tips: List[Tip]) -> List[Dict[str, object]]:
    return [{"key": t.key, "title": t.title, "detail": t.detail, "fix": t.fix, "saving_usd": round(t.saving, 6)} for t in tips]
