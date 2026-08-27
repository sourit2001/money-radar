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

CREATE TABLE IF NOT EXISTS exported_posts (
    reddit_id TEXT PRIMARY KEY,
    report_filename TEXT NOT NULL,
    exported_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exported_posts_report
ON exported_posts(report_filename);

CREATE TABLE IF NOT EXISTS translations (
    source_hash TEXT NOT NULL,
    target_language TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_hash, target_language)
);

CREATE TABLE IF NOT EXISTS semantic_analyses (
    source_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_hash, model, prompt_version)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    run_at TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    sources_attempted INTEGER NOT NULL,
    sources_succeeded INTEGER NOT NULL,
    raw_items INTEGER NOT NULL,
    unique_items INTEGER NOT NULL,
    candidate_items INTEGER NOT NULL,
    failures_json TEXT NOT NULL DEFAULT '[]',
    details_json TEXT NOT NULL DEFAULT '[]'
);
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


def list_posts_for_report(
    conn: sqlite3.Connection,
    report_filename: str,
    *,
    min_value_score: int = 1,
    limit: int = 300,
) -> list[dict]:
    """Return new posts plus posts already assigned to this exact report.

    Posts exported by an older report are excluded, while rerunning the same
    dated report remains idempotent and preserves its existing contents.
    """
    rows = conn.execute(
        """
        SELECT posts.*
        FROM posts
        LEFT JOIN exported_posts ON exported_posts.reddit_id = posts.reddit_id
        WHERE posts.value_score >= ?
          AND (exported_posts.reddit_id IS NULL OR exported_posts.report_filename = ?)
        ORDER BY posts.value_score DESC, posts.num_comments DESC,
                 posts.score DESC, posts.created_utc DESC
        LIMIT ?
        """,
        (min_value_score, report_filename, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def record_exported_posts(
    conn: sqlite3.Connection,
    reddit_ids: Iterable[str],
    report_filename: str,
    exported_at: str,
) -> None:
    conn.executemany(
        """
        INSERT INTO exported_posts (reddit_id, report_filename, exported_at)
        VALUES (?, ?, ?)
        ON CONFLICT(reddit_id) DO NOTHING
        """,
        ((reddit_id, report_filename, exported_at) for reddit_id in reddit_ids),
    )
    conn.commit()


def get_translation(
    conn: sqlite3.Connection, source_hash: str, target_language: str
) -> str | None:
    row = conn.execute(
        "SELECT translated_text FROM translations WHERE source_hash=? AND target_language=?",
        (source_hash, target_language),
    ).fetchone()
    return row["translated_text"] if row else None


def save_translation(
    conn: sqlite3.Connection,
    source_hash: str,
    target_language: str,
    source_text: str,
    translated_text: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO translations
            (source_hash, target_language, source_text, translated_text, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_hash, target_language) DO UPDATE SET
            translated_text=excluded.translated_text,
            created_at=excluded.created_at
        """,
        (source_hash, target_language, source_text, translated_text, created_at),
    )
    conn.commit()


def get_semantic_analysis(
    conn: sqlite3.Connection, source_hash: str, model: str, prompt_version: str
) -> str | None:
    row = conn.execute(
        """SELECT analysis_json FROM semantic_analyses
           WHERE source_hash=? AND model=? AND prompt_version=?""",
        (source_hash, model, prompt_version),
    ).fetchone()
    return row["analysis_json"] if row else None


def save_semantic_analysis(
    conn: sqlite3.Connection, source_hash: str, model: str, prompt_version: str,
    analysis_json: str, created_at: str,
) -> None:
    conn.execute(
        """INSERT INTO semantic_analyses
           (source_hash, model, prompt_version, analysis_json, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(source_hash, model, prompt_version) DO UPDATE SET
             analysis_json=excluded.analysis_json, created_at=excluded.created_at""",
        (source_hash, model, prompt_version, analysis_json, created_at),
    )
    conn.commit()


def save_scan_run(conn: sqlite3.Connection, stats: dict) -> None:
    conn.execute(
        """INSERT INTO scan_runs
           (run_at, source, sources_attempted, sources_succeeded, raw_items,
            unique_items, candidate_items, failures_json, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(run_at) DO UPDATE SET
             sources_succeeded=excluded.sources_succeeded,
             raw_items=excluded.raw_items, unique_items=excluded.unique_items,
             candidate_items=excluded.candidate_items,
             failures_json=excluded.failures_json, details_json=excluded.details_json""",
        (
            stats["run_at"], stats.get("source", "reddit"),
            int(stats.get("sources_attempted") or 0),
            int(stats.get("sources_succeeded") or 0),
            int(stats.get("raw_items") or 0), int(stats.get("unique_items") or 0),
            int(stats.get("candidate_items") or 0),
            json.dumps(stats.get("failures") or [], ensure_ascii=False),
            json.dumps(stats.get("details") or [], ensure_ascii=False),
        ),
    )
    conn.commit()


def latest_scan_run(conn: sqlite3.Connection, source: str = "reddit") -> dict | None:
    row = conn.execute(
        "SELECT * FROM scan_runs WHERE source=? ORDER BY run_at DESC LIMIT 1", (source,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["failures"] = json.loads(result.pop("failures_json") or "[]")
    result["details"] = json.loads(result.pop("details_json") or "[]")
    return result


def metadata(conn: sqlite3.Connection) -> dict:
    channels = conn.execute("SELECT DISTINCT channel FROM posts ORDER BY channel").fetchall()
    subreddits = conn.execute("SELECT DISTINCT subreddit FROM posts ORDER BY lower(subreddit)").fetchall()
    total = conn.execute("SELECT COUNT(*) AS count FROM posts").fetchone()["count"]
    return {
        "total": total,
        "channels": [row["channel"] for row in channels],
        "subreddits": [row["subreddit"] for row in subreddits],
        "latest_reddit_scan": latest_scan_run(conn),
    }
