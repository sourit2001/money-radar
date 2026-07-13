"""Precision-first filtering utilities for demand-signal Reddit posts."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re

from .config import (
    DEMAND_PATTERNS,
    EXPLICIT_OPPORTUNITY_PHRASES,
    FAILED_ATTEMPT_TERMS,
    MIN_COMMENTS,
    MIN_OPPORTUNITY_SCORE,
    MIN_SCORE,
    PROBLEM_CONTEXT_TERMS,
    PROMOTIONAL_TITLE_PATTERNS,
    RECURRING_TERMS,
    STRONG_INTENT_PHRASES,
    SUPPLY_POST_MARKERS,
    WORKFLOW_TERMS,
)


@dataclass(frozen=True)
class SignalMatch:
    signal: str
    phrase: str


@dataclass(frozen=True)
class OpportunityAssessment:
    eligible: bool
    score: int
    reasons: tuple[str, ...]
    signal_match: SignalMatch | None
    tier: str = "rejected"


def combined_text(post: dict) -> str:
    title = post.get("title") or ""
    selftext = post.get("selftext") or ""
    text = unescape(f"{title}\n{selftext}").lower()
    # Reddit RSS appends boilerplate that is not authored demand text.
    text = re.sub(r"\s+submitted by\s+.*$", "", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _first_phrase(text: str, phrases: list[str]) -> str | None:
    for phrase in sorted(phrases, key=len, reverse=True):
        if _contains(text, phrase):
            return phrase
    return None


def detect_signal(post: dict) -> SignalMatch | None:
    text = combined_text(post)
    # Prefer commercially useful signals over generic "help" wording.
    for signal in ("tool_search", "opportunity", "pain", "help"):
        phrase = _first_phrase(text, DEMAND_PATTERNS[signal])
        if phrase:
            return SignalMatch(signal=signal, phrase=phrase)
    return None


def assess_opportunity(post: dict) -> OpportunityAssessment:
    """Score a concrete opportunity and retain reasons for the decision."""
    title = unescape(post.get("title") or "").lower()
    text = combined_text(post)
    body = unescape(post.get("selftext") or "").lower()
    # Intent buried deep inside a long essay is commonly an example or quote,
    # not the author's request. Supporting evidence may use the full post, but
    # request intent must appear in the title or opening paragraph.
    lead_text = re.sub(r"\s+", " ", f"{title} {body[:400]}").strip()
    signal_match = detect_signal(post)

    if post.get("stickied") or post.get("over_18"):
        return OpportunityAssessment(False, 0, ("blocked post type",), signal_match)

    promo = _first_phrase(title, PROMOTIONAL_TITLE_PATTERNS)
    seo_title = any(
        re.search(pattern, title)
        for pattern in (
            r"\b\d+\s+best\b",
            r"\bbest .+ software (?:in|for) 20\d{2}\b",
            r"^what is .+ software\??$",
            r"^how .+ software (?:improves|helps|can)",
            r"^why (?:are|do) businesses .+ software",
        )
    )
    explicit_question = "?" in title or _first_phrase(
        lead_text,
        [
            "how do i", "how can i", "is there a way", "need help",
            "struggling", "stuck", "looking for a tool", "looking for an app",
            "looking for software", "looking for a platform",
            "looking for a solution", "alternative to", "does this exist",
            "does anyone know", "has anyone found", "what do you use for",
            "any recommendations", "need a better way",
        ],
    )
    strong_intent = _first_phrase(lead_text, STRONG_INTENT_PHRASES)
    opportunity = _first_phrase(lead_text, EXPLICIT_OPPORTUNITY_PHRASES)
    pain = _first_phrase(text, DEMAND_PATTERNS["pain"])
    workflow = _first_phrase(text, WORKFLOW_TERMS)
    context = _first_phrase(text, PROBLEM_CONTEXT_TERMS)
    recurring = _first_phrase(text, RECURRING_TERMS)
    failed_attempt = _first_phrase(text, FAILED_ATTEMPT_TERMS)
    supply_marker = _first_phrase(text, SUPPLY_POST_MARKERS)

    if seo_title:
        return OpportunityAssessment(False, 0, ("SEO/vendor title",), signal_match)

    if promo:
        return OpportunityAssessment(
            False, 0, (f"promotional/meta title: {promo}",), signal_match
        )

    # Product launches often contain exactly the same pain vocabulary as
    # demand posts. Keep first-person supply posts out unless the author is
    # explicitly describing a spreadsheet workaround to an unresolved pain.
    spreadsheet_workaround = opportunity == "i built a spreadsheet" and bool(pain)
    if supply_marker and not spreadsheet_workaround:
        return OpportunityAssessment(
            False, 0, (f"product/supply post: {supply_marker}",), signal_match
        )

    score = 0
    reasons: list[str] = []
    evidence = (
        (4, "explicit tool intent", strong_intent),
        (3, "automation/workaround intent", opportunity),
        (2, "pain", pain),
        (2, "workflow evidence", workflow),
        (1, "professional/financial context", context),
        (1, "recurring need", recurring),
        (2, "failed workaround", failed_attempt),
        (1, "explicit question", explicit_question and "question"),
    )
    for points, label, phrase in evidence:
        if phrase:
            score += points
            reasons.append(f"{label}: {phrase}")

    if strong_intent and _contains(title, strong_intent):
        score += 1
        reasons.append("intent appears in title")

    supporting_evidence = sum(
        bool(value) for value in (pain, workflow, context, recurring, failed_attempt)
    )
    direct_demand = (
        (bool(strong_intent) and supporting_evidence >= 1 and bool(explicit_question))
        or (bool(opportunity) and supporting_evidence >= 1 and bool(explicit_question))
        or (bool(pain) and bool(workflow) and bool(explicit_question))
    )
    latent_demand = bool(pain) and bool(workflow) and bool(context or recurring)
    eligible = score >= MIN_OPPORTUNITY_SCORE and (direct_demand or latent_demand)
    if eligible and latent_demand and not direct_demand:
        reasons.append("latent demand: concrete workflow pain")
    if not reasons:
        reasons.append("no concrete opportunity evidence")
    tier = "direct" if eligible and direct_demand else "latent" if eligible else "rejected"
    return OpportunityAssessment(eligible, score, tuple(reasons), signal_match, tier)


def passes_engagement(
    post: dict, min_comments: int = MIN_COMMENTS, min_score: int = MIN_SCORE
) -> bool:
    return int(post.get("num_comments") or 0) >= min_comments or int(
        post.get("score") or 0
    ) >= min_score


def is_candidate_post(post: dict) -> bool:
    assessment = assess_opportunity(post)
    if not assessment.eligible:
        return False
    # Missing RSS engagement is unknown, not positive. Content still has to
    # pass the stricter multi-signal assessment above.
    score = int(post.get("score") or 0)
    comments = int(post.get("num_comments") or 0)
    if score == 0 and comments == 0:
        return True
    return passes_engagement(post)
