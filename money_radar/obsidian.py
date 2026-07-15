"""Markdown export helpers for Obsidian."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .storage import (
    connect,
    init_db,
    list_posts_for_report,
    metadata,
    record_exported_posts,
)
from .translation import add_chinese_translations


_REDDIT_ID_PATTERN = re.compile(r"reddit\.com/(?:r/[^/]+/)?comments/([^/?#]+)", re.IGNORECASE)


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
        title_zh = _escape_markdown(post.get("title_zh"))
        permalink = post.get("permalink") or post.get("url") or ""
        lines.extend(
            [
                f"## {index}. {title}",
                "",
                *([f"**中文标题**：{title_zh}", ""] if title_zh and title_zh != title else []),
                f"- Score / 评分: {post.get('value_score', 1)}/5",
                f"- Source / 来源: r/{_escape_markdown(post.get('subreddit'))} / {_escape_markdown(post.get('channel'))}",
                f"- Posted / 发布时间: {_format_post_date(post.get('created_utc'))}",
                f"- Signal / 需求信号: {_escape_markdown(post.get('signal'))}",
                f"- Opportunity / 机会类型: {_escape_markdown(post.get('opportunity_type'))}",
            ]
        )
        if permalink:
            lines.append(f"- Reddit: {permalink}")
        phrase = _compact_text(post.get("signal_phrase"), limit=220)
        if phrase:
            lines.append(f"- Phrase: {phrase}")
        pain = _compact_text(post.get("pain_summary"), limit=360)
        pain_zh = _compact_text(post.get("pain_summary_zh"), limit=360)
        if pain:
            lines.extend(["", f"**Pain / 痛点（原文）**：{pain}"])
        if pain_zh and pain_zh != pain:
            lines.append(f"**痛点（中文）**：{pain_zh}")
        body = _compact_text(post.get("selftext"), limit=900)
        body_zh = _compact_text(post.get("selftext_zh"), limit=900)
        if body and body != pain:
            lines.extend(["", "**Post / 帖子原文**", "", body])
        if body_zh and body_zh not in {body, pain_zh}:
            lines.extend(["", "**中文翻译**", "", body_zh])
        lines.append("")

    return "\n".join(lines)


def export_obsidian_markdown(
    db_path: str | Path,
    target_dir: str | Path,
    *,
    min_score: int = 4,
    limit: int = 50,
    filename: str = "Money Radar Latest.md",
    bilingual: bool = False,
) -> Path:
    target = Path(target_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    init_db(conn)

    # Bootstrap delivery history from reports created before exported_posts was
    # introduced, preventing a one-time replay after upgrading.
    for report_path in sorted(target.glob("Money Radar *.md")):
        try:
            report_text = report_path.read_text(encoding="utf-8")
        except OSError:
            continue
        historical_ids = set(_REDDIT_ID_PATTERN.findall(report_text))
        if historical_ids:
            record_exported_posts(
                conn,
                historical_ids,
                report_path.name,
                datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            )

    posts = list_posts_for_report(
        conn,
        filename,
        min_value_score=min_score,
        limit=limit,
    )
    if bilingual:
        add_chinese_translations(conn, posts)
    meta = metadata(conn)

    output_path = target / filename
    output_path.write_text(
        render_obsidian_markdown(posts, total_saved=meta["total"], min_score=min_score),
        encoding="utf-8",
    )
    record_exported_posts(
        conn,
        (post["reddit_id"] for post in posts),
        filename,
        datetime.now(timezone.utc).isoformat(),
    )
    conn.close()
    return output_path
