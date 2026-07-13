"""Deterministic opportunity annotation for MVP posts."""

from __future__ import annotations

import re

from .filters import assess_opportunity, detect_signal

OPPORTUNITY_KEYWORDS = [
    ("automation", ["automate", "automation", "manual", "workflow", "takes too long"]),
    ("SaaS", ["saas", "subscription", "dashboard", "crm", "client", "team"]),
    ("small tool", ["tool", "app", "software", "extension", "script", "calculator"]),
    ("template", ["template", "notion", "spreadsheet", "excel", "sheet"]),
    ("content", ["learn", "course", "guide", "tutorial", "explain"]),
    ("service", ["freelance", "agency", "consultant", "client", "outsourc"]),
    ("data product", ["data", "tracking", "analytics", "report", "monitor"]),
]


def compact_sentence(text: str, limit: int = 170) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return "The post shows a possible demand signal, but the body is empty."
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rsplit(" ", 1)[0] + "..."


def opportunity_type(text: str) -> str:
    lowered = text.lower()
    for label, keywords in OPPORTUNITY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return label
    return "unclear"


def value_score(post: dict, signal: str | None, kind: str) -> int:
    precision_score = assess_opportunity(post).score
    if precision_score >= 9:
        score = 5
    elif precision_score >= 7:
        score = 4
    elif precision_score >= 5:
        score = 3
    elif precision_score >= 3:
        score = 2
    else:
        score = 1
    comments = int(post.get("num_comments") or 0)
    upvotes = int(post.get("score") or 0)
    if comments >= 20 or upvotes >= 75:
        score += 1
    return max(1, min(score, 5))


def annotate_post(post: dict) -> dict:
    title = post.get("title") or ""
    body = post.get("selftext") or ""
    text = f"{title}. {body}".strip()
    signal_match = detect_signal(post)
    signal = signal_match.signal if signal_match else "unclear"
    kind = opportunity_type(text)
    return {
        "signal": signal,
        "signal_phrase": signal_match.phrase if signal_match else "",
        "pain_summary": compact_sentence(text),
        "opportunity_type": kind,
        "value_score": value_score(post, signal, kind),
    }
