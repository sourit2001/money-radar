"""Optional cached offline translation using Argos Translate."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from typing import Callable

from .storage import get_translation, save_translation


_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")


def argos_english_to_chinese(text: str) -> str:
    """Translate English text with an installed Argos en->zh package."""
    import argostranslate.translate

    return argostranslate.translate.translate(text, "en", "zh")


def translate_cached(
    conn: sqlite3.Connection,
    text: object,
    *,
    translator: Callable[[str], str] = argos_english_to_chinese,
) -> str:
    source = " ".join(str(text or "").split()).strip()
    if not source or _CJK_PATTERN.search(source):
        return source

    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    cached = get_translation(conn, source_hash, "zh")
    if cached is not None:
        return cached

    translated = " ".join(translator(source).split()).strip()
    if translated:
        save_translation(
            conn,
            source_hash,
            "zh",
            source,
            translated,
            datetime.now(timezone.utc).isoformat(),
        )
    return translated


def add_chinese_translations(
    conn: sqlite3.Connection,
    posts: list[dict],
    *,
    translator: Callable[[str], str] = argos_english_to_chinese,
) -> bool:
    """Attach Chinese render fields; gracefully fall back if Argos is unavailable."""
    try:
        for post in posts:
            post["title_zh"] = translate_cached(conn, post.get("title"), translator=translator)
            post["pain_summary_zh"] = translate_cached(
                conn, post.get("pain_summary"), translator=translator
            )
            post["selftext_zh"] = translate_cached(
                conn, post.get("selftext"), translator=translator
            )
    except (ImportError, RuntimeError, ValueError):
        return False
    return True
