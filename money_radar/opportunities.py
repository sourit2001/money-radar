"""Deterministic market-opportunity clustering for saved Reddit posts.

This is intentionally explainable: every opportunity is made from source
posts, visible evidence counts, and a small set of domain patterns.  It is a
first step beyond ranking individual posts; it does not pretend that one loud
thread proves a market.
"""

from __future__ import annotations

import re
from collections import Counter

from .filters import assess_opportunity


CLUSTER_PATTERNS = (
    ("video postproduction", (("video",), ("subtitle", "subtitles", "caption", "captions", "dubbing", "transcription", "transcribe"))),
    ("regional personal-finance data access", (("bank", "banks", "banking", "credit card", "credit cards"), ("personal finance", "budget", "budgeting", "expense", "expenses", "net worth"))),
    ("ai brand visibility tracking", (("brand", "brand tracking", "brand visibility"), ("chatgpt", "ai visibility", "prompt", "prompts", "llm"))),
    ("client reporting", (("client report", "client reports", "client reporting", "customer report", "agency report"), ("metrics", "dashboard", "dashboards", "slides", "spreadsheet", "spreadsheets", "export"))),
    ("invoice reconciliation", (("invoice reconciliation", "reconcile invoices", "stripe reconciliation", "quickbooks reconciliation"), ("accounting", "bookkeeping", "spreadsheet", "manual", "software"))),
    ("irregular-income budgeting", (("irregular income", "variable income", "freelance income", "income budgeting"), ("budget", "budgeting", "paycheck", "cash flow"))),
    ("supplier spreadsheet cleanup", (("supplier spreadsheet", "vendor spreadsheet", "inventory spreadsheet", "inventory management"), ("excel", "csv", "import", "cleanup", "mobile"))),
    ("lead and CRM workflow", (("crm", "sales pipeline", "lead management", "deal follow-up", "deal follow up"), ("lead", "prospect", "deal", "follow-up", "follow up"))),
)

STOPWORDS = {
    "about", "after", "also", "any", "app", "better", "can", "does", "for", "from",
    "have", "help", "how", "i", "is", "it", "looking", "need", "of", "on", "or",
    "please", "recommend", "software", "some", "that", "the", "this", "to", "tool",
    "use", "using", "what", "with", "would", "you", "your",
}


def _text(post: dict) -> str:
    body = (post.get("selftext") or "")[:600]
    return " ".join((post.get("title") or "", body)).lower()


def _term_present(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text) is not None


def _cluster_key(post: dict) -> str:
    text = _text(post)
    for key, groups in CLUSTER_PATTERNS:
        if all(any(_term_present(text, term) for term in group) for group in groups):
            return key
    # Unknown concepts remain individual signals until a stronger repeated
    # pattern is known. This is safer than grouping unrelated posts around
    # generic words such as "tool", "best", or "software".
    return f"signal:{post.get('reddit_id') or post.get('permalink') or id(post)}"


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _sentences(post: dict) -> list[str]:
    """Keep source-faithful, readable evidence excerpts from a post."""
    text = " ".join(str(post.get("selftext") or "").split())
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(sentence.strip()) >= 24
    ]


def _first_evidence_sentence(post: dict, patterns: tuple[str, ...]) -> str | None:
    for sentence in _sentences(post):
        lowered = sentence.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            return sentence
    return None


def _source_evidence(posts: list[dict]) -> dict[str, list[dict]]:
    """Extract quotes, never inferred claims, for the daily report."""
    pattern_sets = {
        "pain": (r"\bmanual(?:ly)?\b", r"takes? (?:a )?long", r"drown", r"difficult", r"messy", r"annoying", r"frustrat"),
        "alternative": (r"\bi (?:am|['’]m) (?:currently )?using\b", r"\bi (?:have )?tried\b", r"\btools? (?:like|such as)\b", r"\busing\b"),
        "failure": (r"\bbut\b", r"\bnone (?:of|work)\b", r"\bdoesn['’]t work\b", r"\bno longer\b", r"\blocked\b", r"\bmanual(?:ly)?\b", r"\btoo expensive\b"),
        "payment_willingness": (r"\bhappy to pay\b", r"\bwilling to pay\b", r"\bi(?: would|['’]d) pay\b", r"\bi want to pay\b", r"\bi(?: would|['’]d) subscribe\b"),
        "price_ceiling": (r"\bno (?:huge )?.{0,35}\$\d+", r"\bnot .{0,35}\$\d+", r"\btoo expensive\b", r"\bcan['’]t afford\b", r"\bdon['’]t want to pay\b"),
    }
    evidence = {kind: [] for kind in pattern_sets}
    seen: set[tuple[str, str]] = set()
    for post in posts:
        for kind, patterns in pattern_sets.items():
            quote = _first_evidence_sentence(post, patterns)
            if not quote:
                continue
            fingerprint = (kind, quote.lower())
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            evidence[kind].append({
                "quote": quote,
                "permalink": post.get("permalink") or post.get("url") or "",
                "title": post.get("title") or "Reddit 原帖",
            })
    return {kind: values[:3] for kind, values in evidence.items()}


def _workaround(post: dict) -> str | None:
    text = _text(post)
    if _has_any(text, ("spreadsheet", "excel", "google sheet")):
        return "spreadsheet or manual spreadsheet work"
    if _has_any(text, ("copy and paste", "copying", "data entry", "manually")):
        return "manual copy/paste or data entry"
    if _has_any(text, ("tried several", "tried multiple", "nothing works", "doesn't work", "none of them")):
        return "several existing tools, with no satisfactory result"
    return None


def _analysis_for(key: str, posts: list[dict]) -> dict:
    briefs = [post.get("semantic_brief") or {} for post in posts]

    def collect(*keys: str, limit: int = 2) -> str:
        values = []
        for brief in briefs:
            for key_name in keys:
                value = " ".join(str(brief.get(key_name) or "").split())
                if value and value not in values:
                    values.append(value)
                    break
        return "；".join(values[:limit])

    return {
        "use_case": collect("scenario"),
        "pain": collect("pain", "friction"),
        "alternatives": collect("current_workflow", "friction"),
        "build": collect("mvp"),
        "research_reason": "原帖提供了可复核的具体需求；规模、增长和付费意愿仍不能由这些帖子单独推出。",
        "verification_label": "需求线索，待验证",
    }


def _title(key: str, posts: list[dict]) -> str:
    if key in {name for name, _ in CLUSTER_PATTERNS}:
        return f"{key.title()} Tools"
    return "Early market signal"


def build_opportunities(posts: list[dict], limit: int = 50) -> list[dict]:
    posts = [
        post for post in posts
        if assess_opportunity(post).eligible
    ]
    groups: dict[str, list[dict]] = {}
    for post in posts:
        groups.setdefault(_cluster_key(post), []).append(post)

    opportunities: list[dict] = []
    for key, cluster in groups.items():
        texts = [_text(post) for post in cluster]
        subreddits = sorted({post.get("subreddit") for post in cluster if post.get("subreddit")})
        channels = sorted({post.get("channel") for post in cluster if post.get("channel")})
        workaround_counts = Counter(
            workaround for post in cluster if (workaround := _workaround(post))
        )
        source_evidence = _source_evidence(cluster)
        paid_count = len(source_evidence["payment_willingness"])
        price_ceiling_count = len(source_evidence["price_ceiling"])
        failed_count = sum(
            1 for text in texts if _has_any(text, ("tried", "nothing works", "doesn't work", "still doing", "manual"))
        )
        pain_count = sum(
            1 for post in cluster if post.get("signal") in {"pain", "opportunity"}
        )
        frequency = min(5, len(cluster))
        breadth = min(3, len(subreddits))
        evidence_score = frequency + breadth + min(2, paid_count) + min(2, failed_count)
        market_score = min(10, evidence_score + (1 if pain_count else 0))
        evidence_level = "strong" if len(cluster) >= 3 else "emerging" if len(cluster) >= 2 else "signal"
        gap = (
            f"Users commonly fall back to {workaround_counts.most_common(1)[0][0]}."
            if workaround_counts
            else "The posts contain a demand signal, but the current workaround is not yet clear."
        )
        sorted_posts = sorted(
            cluster,
            key=lambda post: (
                int(post.get("value_score") or 0),
                int(post.get("num_comments") or 0),
                int(post.get("score") or 0),
            ),
            reverse=True,
        )
        representative = sorted_posts[:5]
        opportunity_title = _title(key, cluster)
        if key.startswith("signal:"):
            opportunity_title = f"Early signal: {cluster[0].get('title') or 'unclassified demand'}"
        opportunities.append({
            "key": key,
            "title": opportunity_title,
            "post_count": len(cluster),
            "subreddits": subreddits,
            "channels": channels,
            "market_score": market_score,
            "evidence_level": evidence_level,
            "paid_signal_count": paid_count,
            "price_ceiling_count": price_ceiling_count,
            "failed_solution_count": failed_count,
            "pain_signal_count": pain_count,
            "direct_signal_count": sum(
                1 for post in cluster if assess_opportunity(post).tier == "direct"
            ),
            "current_workaround": gap,
            "why_now": f"Found in {len(cluster)} saved post{'s' if len(cluster) != 1 else ''} across {len(subreddits)} communit{'ies' if len(subreddits) != 1 else 'y'}.",
            "next_action": "Read the representative threads and test whether the same job appears in at least 3 independent conversations.",
            "analysis": _analysis_for(key, cluster),
            "source_evidence": source_evidence,
            "posts": sorted_posts,
            "representative_posts": representative,
        })

    return sorted(
        opportunities,
        key=lambda item: (item["market_score"], item["post_count"], item["paid_signal_count"]),
        reverse=True,
    )[:limit]
