"""DeepSeek-backed, source-grounded annotations for the daily report."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
from typing import Callable
from urllib import error, request

from .config import PROJECT_ROOT
from .storage import get_semantic_analysis, save_semantic_analysis
from .translation import split_source_sentences


DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
PROMPT_VERSION = "source-grounded-brief-v4"


class SemanticAnalysisError(RuntimeError):
    """Raised when DeepSeek cannot return a safe structured annotation."""


def _api_key_from_project_file() -> str | None:
    """Read the ignored project-root key file without exposing it in logs."""
    path = PROJECT_ROOT / "deepseek.env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                value = line.split("=", 1)[1].strip()
                return value or None
    except OSError:
        return None
    return None


def _prompt(title: str, sentences: list[str]) -> str:
    numbered = "\n".join(f"{index + 1}. {sentence}" for index, sentence in enumerate(sentences))
    return f"""You analyze a real user post for a Chinese product-opportunity brief.

Title: {title}

Sentences:
{numbered}

Return JSON only, with this exact shape:
{{"annotations":[{{"sentence_id":1}}],"brief":{{"scenario":"...","current_workflow":"...","pain":"...","friction":"...","user_wants":"...","mvp":"...","evidence_boundary":"..."}}}}

Select only 1 to 3 sentences that materially affect a product decision. Each
annotation must contain exactly one sentence_id and nothing else. Use the title and
the complete post body, not generic knowledge. Extract concrete details such as named
tools, country, workflow steps, failed alternatives, constraints, requested outcome,
and explicit payment language when present. The brief must be concise Chinese and
contain only facts supported by the source. Omit unsupported details rather than
filling them with generic wording. Each field is one short sentence. A price complaint
is only a price constraint; never call it willingness to pay unless the post explicitly
says the user will pay. Do not invent user counts, competitor facts, payment intent,
market size, or conclusions from the subreddit name."""


def _parse(content: str, sentences: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SemanticAnalysisError("DeepSeek did not return valid JSON.") from exc
    annotations: dict[str, str] = {}
    for entry in payload.get("annotations", []):
        sentence_id = entry.get("sentence_id")
        if isinstance(sentence_id, int) and 1 <= sentence_id <= len(sentences):
            annotations[sentences[sentence_id - 1]] = "selected"
    field_defaults = {
        "scenario": "",
        "current_workflow": "",
        "pain": "",
        "friction": "",
        "user_wants": "",
        "mvp": "",
        "evidence_boundary": "",
    }
    brief = {}
    for key, default in field_defaults.items():
        value = " ".join(str((payload.get("brief") or {}).get(key) or default).split())[:360]
        if value:
            brief[key] = value
    return annotations, brief


def _call_deepseek(api_key: str, model: str, prompt: str) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise product researcher. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "max_tokens": 2200,
        "thinking": {"type": "disabled"},
    }).encode("utf-8")
    req = request.Request(
        DEEPSEEK_URL, data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        raise SemanticAnalysisError(f"DeepSeek request failed: {exc}") from exc
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SemanticAnalysisError("DeepSeek response did not contain analysis content.") from exc


def add_deepseek_analyses(
    conn: sqlite3.Connection, posts: list[dict], *,
    api_key: str | None = None, model: str | None = None,
    caller: Callable[[str, str, str], str] = _call_deepseek,
) -> bool:
    """Attach cached inline analyses. Missing credentials leave reports usable."""
    if api_key is None:
        if os.environ.get("MONEY_RADAR_DISABLE_SEMANTIC_ANALYSIS") == "1":
            return False
        api_key = os.environ.get("DEEPSEEK_API_KEY") or _api_key_from_project_file()
    model = model or os.environ.get("MONEY_RADAR_DEEPSEEK_MODEL", DEFAULT_MODEL)
    if not api_key:
        return False
    for post in posts:
        sentences = split_source_sentences(post.get("selftext"))
        if not sentences:
            post["semantic_annotations"] = {}
            continue
        source = f"{post.get('title', '')}\n{post.get('selftext', '')}"
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        cached = get_semantic_analysis(conn, source_hash, model, PROMPT_VERSION)
        if cached is None:
            content = caller(api_key, model, _prompt(str(post.get("title") or ""), sentences))
            annotations, brief = _parse(content, sentences)
            cached = json.dumps(
                {"annotations": annotations, "brief": brief}, ensure_ascii=False, sort_keys=True
            )
            save_semantic_analysis(
                conn, source_hash, model, PROMPT_VERSION, cached,
                datetime.now(timezone.utc).isoformat(),
            )
        try:
            parsed = json.loads(cached)
            post["semantic_annotations"] = parsed.get("annotations", {})
            post["semantic_brief"] = parsed.get("brief", {})
        except json.JSONDecodeError:
            post["semantic_annotations"] = {}
            post["semantic_brief"] = {}
    return True


def add_deepseek_comment_summaries(
    posts: list[dict], *, api_key: str | None = None, model: str | None = None,
    caller: Callable[[str, str, str], str] = _call_deepseek,
) -> bool:
    """Summarize only fetched Reddit comments; absent comments stay explicit."""
    if api_key is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or _api_key_from_project_file()
    model = model or os.environ.get("MONEY_RADAR_DEEPSEEK_MODEL", DEFAULT_MODEL)
    if not api_key:
        return False
    for post in posts:
        comments = post.get("comments") or []
        if not comments:
            post["comment_summary"] = ""
            continue
        quoted = "\n".join(f"{index + 1}. {comment['body']}" for index, comment in enumerate(comments))
        prompt = f"""Summarize these Reddit comments about the source post below in concise Chinese.
Source title: {post.get('title', '')}
Comments:\n{quoted}

Return JSON only: {{"summary":"..."}}. Write at most two concise Chinese sentences.
Name concrete tools, workarounds, failures, requested features, or disagreement when
the comments provide them. If comments add no useful evidence, say so briefly. State
only what these comments support. Do not infer market size, and do not call a comment
payment intent unless it explicitly says so."""
        try:
            payload = json.loads(caller(api_key, model, prompt).strip().removeprefix("```json").removesuffix("```").strip())
            post["comment_summary"] = " ".join(str(payload.get("summary") or "").split())
        except (SemanticAnalysisError, json.JSONDecodeError):
            post["comment_summary"] = ""
    return True


def add_market_product_analyses(
    products: list[dict], *, api_key: str | None = None, model: str | None = None,
    caller: Callable[[str, str, str], str] = _call_deepseek,
) -> bool:
    """Explain what concrete products cover, using only their public descriptions."""
    if api_key is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or _api_key_from_project_file()
    model = model or os.environ.get("MONEY_RADAR_DEEPSEEK_MODEL", DEFAULT_MODEL)
    products = [product for product in products if str(product.get("description") or "").strip()]
    if not api_key or not products:
        return False
    compact = [
        {
            "id": str(product.get("id") or product.get("url") or index),
            "source": product.get("source") or "unknown",
            "name": product.get("name") or product.get("title") or "",
            "description": str(product.get("description") or "")[:700],
            "rank": product.get("rank"),
            "list_type": product.get("list_type"),
        }
        for index, product in enumerate(products)
    ]
    prompt = f"""Analyze these public product-directory entries for a Chinese opportunity brief.
Entries: {json.dumps(compact, ensure_ascii=False)}

Return JSON only:
{{"analyses":[{{"id":"...","problem":"...","target_user":"...","coverage":"...","solo_gap":"...","evidence_limit":"..."}}]}}

For each entry explain: the concrete problem it claims to solve; its likely target user
only when supported by the description; what capability already exists; a narrow angle
an individual developer might investigate without cloning the whole product; and what
cannot be concluded from a directory/launch description. Do not invent usage numbers,
growth, complaints, pricing, reviews, or unmet demand. If a field is unsupported, say
'公开简介未说明'. Use concise Chinese."""
    try:
        content = caller(api_key, model, prompt).strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else ""
            content = content.rstrip().removesuffix("```").strip()
        payload = json.loads(content)
    except (SemanticAnalysisError, json.JSONDecodeError):
        return False
    by_id = {
        str(item.get("id")): {
            key: " ".join(str(item.get(key) or "公开简介未说明").split())[:360]
            for key in ("problem", "target_user", "coverage", "solo_gap", "evidence_limit")
        }
        for item in payload.get("analyses", []) if item.get("id") is not None
    }
    for index, product in enumerate(products):
        product_id = str(product.get("id") or product.get("url") or index)
        product["analysis"] = by_id.get(product_id, {})
    return bool(by_id)
