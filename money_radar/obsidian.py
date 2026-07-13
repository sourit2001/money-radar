"""Markdown export helpers for Obsidian."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .storage import connect, init_db, list_posts, metadata


def _escape_markdown(value: object) -> str:
    text = str(value or "").strip()
    return text.replace("|", "\\|")


def _format_post_date(seconds: object) -> str:
    try:
        timestamp = float(seconds or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if not timestamp:
        return "unknown date"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _compact_text(value: object, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def render_obsidian_markdown(posts: list[dict], *, total_saved: int, min_score: int) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Money Radar Latest",
        "",
        f"- Generated: {generated_at}",
        f"- Showing: {len(posts)} posts with score >= {min_score}",
        f"- Database total: {total_saved} saved posts",
        "",
    ]

    if not posts:
        lines.extend(
            [
                "No matching Reddit opportunities yet.",
                "",
                "Try running the fetch command again or lowering the minimum score.",
                "",
            ]
        )
        return "\n".join(lines)

    for index, post in enumerate(posts, start=1):
        title = _escape_markdown(post.get("title"))
        permalink = post.get("permalink") or post.get("url") or ""
        lines.extend(
            [
                f"## {index}. {title}",
                "",
                f"- Score: {post.get('value_score', 1)}/5",
                f"- Source: r/{_escape_markdown(post.get('subreddit'))} / {_escape_markdown(post.get('channel'))}",
                f"- Posted: {_format_post_date(post.get('created_utc'))}",
                f"- Signal: {_escape_markdown(post.get('signal'))}",
                f"- Opportunity: {_escape_markdown(post.get('opportunity_type'))}",
            ]
        )
        if permalink:
            lines.append(f"- Reddit: {permalink}")
        phrase = _compact_text(post.get("signal_phrase"), limit=220)
        if phrase:
            lines.append(f"- Phrase: {phrase}")
        pain = _compact_text(post.get("pain_summary"), limit=360)
        if pain:
            lines.extend(["", f"**Pain**: {pain}"])
        body = _compact_text(post.get("selftext"), limit=900)
        if body and body != pain:
            lines.extend(["", body])
        lines.append("")

    return "\n".join(lines)


def export_obsidian_markdown(
    db_path: str | Path,
    target_dir: str | Path,
    *,
    min_score: int = 4,
    limit: int = 50,
    filename: str = "Money Radar Latest.md",
) -> Path:
    conn = connect(db_path)
    init_db(conn)
    posts = list_posts(conn, min_value_score=min_score, limit=limit)
    meta = metadata(conn)
    conn.close()

    target = Path(target_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    output_path = target / filename
    output_path.write_text(
        render_obsidian_markdown(posts, total_saved=meta["total"], min_score=min_score),
        encoding="utf-8",
    )
    return output_path
