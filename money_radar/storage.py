"""SQLite persistence for Reddit opportunity posts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    reddit_id TEXT PRIMARY KEY,
    subreddit TEXT NOT NULL,
    channel TEXT NOT NULL,
    title TEXT NOT NULL,
    selftext TEXT NOT NULL DEFAULT '',
    permalink TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    num_comments INTEGER NOT NULL DEFAULT 0,
    created_utc REAL NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL,
    signal TEXT NOT NULL DEFAULT 'unclear',
    signal_phrase TEXT NOT NULL DEFAULT '',
    pain_summary TEXT NOT NULL DEFAULT '',
    opportunity_type TEXT NOT NULL DEFAULT 'unclear',
    value_score INTEGER NOT NULL DEFAULT 1,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_value_score ON posts(value_score);
"""

POST_FIELDS = [
    "reddit_id",
    "subreddit",
    "channel",
    "title",
    "selftext",
    "permalink",
    "url",
    "author",
    "score",
    "num_comments",
    "created_utc",
    "fetched_at",
    "signal",
    "signal_phrase",
    "pain_summary",
    "opportunity_type",
    "value_score",
    "raw_json",
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def normalize_post(post: dict) -> dict:
    normalized = {field: post.get(field) for field in POST_FIELDS}
    normalized["selftext"] = normalized.get("selftext") or ""
    normalized["author"] = normalized.get("author") or ""
    normalized["score"] = int(normalized.get("score") or 0)
    normalized["num_comments"] = int(normalized.get("num_comments") or 0)
    normalized["created_utc"] = float(normalized.get("created_utc") or 0)
    normalized["signal"] = normalized.get("signal") or "unclear"
    normalized["signal_phrase"] = normalized.get("signal_phrase") or ""
    normalized["pain_summary"] = normalized.get("pain_summary") or ""
    normalized["opportunity_type"] = normalized.get("opportunity_type") or "unclear"
    normalized["value_score"] = int(normalized.get("value_score") or 1)
    raw_json = normalized.get("raw_json")
    if not isinstance(raw_json, str):
        raw_json = json.dumps(raw_json or {}, ensure_ascii=True, sort_keys=True)
    normalized["raw_json"] = raw_json
    return normalized


def upsert_post(conn: sqlite3.Connection, post: dict) -> None:
    normalized = normalize_post(post)
    placeholders = ", ".join("?" for _ in POST_FIELDS)
    columns = ", ".join(POST_FIELDS)
    updates = ", ".join(f"{field}=excluded.{field}" for field in POST_FIELDS if field != "reddit_id")
    conn.execute(
        f"""
        INSERT INTO posts ({columns}) VALUES ({placeholders})
        ON CONFLICT(reddit_id) DO UPDATE SET {updates}
        """,
        [normalized[field] for field in POST_FIELDS],
    )
    conn.commit()


def upsert_posts(conn: sqlite3.Connection, posts: Iterable[dict]) -> int:
    count = 0
    for post in posts:
        upsert_post(conn, post)
        count += 1
    return count


def list_posts(
    conn: sqlite3.Connection,
    channel: str | None = None,
    subreddit: str | None = None,
    min_value_score: int = 1,
    search: str | None = None,
    limit: int = 300,
) -> list[dict]:
    clauses = ["value_score >= ?"]
    params: list[object] = [min_value_score]
    if channel:
        clauses.append("channel = ?")
        params.append(channel)
    if subreddit:
        clauses.append("lower(subreddit) = lower(?)")
        params.append(subreddit)
    if search:
        needle = f"%{search.lower()}%"
        clauses.append(
            "(lower(title) LIKE ? OR lower(selftext) LIKE ? OR lower(pain_summary) LIKE ? OR lower(subreddit) LIKE ?)"
        )
        params.extend([needle, needle, needle, needle])
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT * FROM posts
        WHERE {" AND ".join(clauses)}
        ORDER BY value_score DESC, num_comments DESC, score DESC, created_utc DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def metadata(conn: sqlite3.Connection) -> dict:
    channels = conn.execute("SELECT DISTINCT channel FROM posts ORDER BY channel").fetchall()
    subreddits = conn.execute("SELECT DISTINCT subreddit FROM posts ORDER BY lower(subreddit)").fetchall()
    total = conn.execute("SELECT COUNT(*) AS count FROM posts").fetchone()["count"]
    return {
        "total": total,
        "channels": [row["channel"] for row in channels],
        "subreddits": [row["subreddit"] for row in subreddits],
    }

