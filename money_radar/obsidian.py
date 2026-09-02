"""Markdown export helpers for Obsidian."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .storage import (
    connect,
    init_db,
    list_posts,
    metadata,
    record_exported_posts,
)
from .reddit import RedditFetchError, fetch_post_comments
from .market import market_validation_for
from .opportunities import build_opportunities
from .semantic_analysis import add_deepseek_analyses, add_deepseek_comment_summaries


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
        permalink = post.get("permalink") or post.get("url") or ""
        lines.extend(
            [
                f"## {index}. 需求来源 {index}",
                "",
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
        if pain:
            lines.extend(["", f"**Pain / 痛点摘要**：{pain}"])
        lines.append("")

    return "\n".join(lines)


def _brief_line(brief: dict[str, str], key: str, fallback: str) -> str:
    return " ".join(str(brief.get(key) or fallback).split())


def _render_market_product(product: dict, *, heading_level: int = 4) -> list[str]:
    name = _escape_markdown(product.get("name") or product.get("title") or "未命名产品")
    url = product.get("url") or ""
    analysis = product.get("analysis") or {}
    source = "Product Hunt 新品" if product.get("source") == "product_hunt" else (
        "Toolify 新收录" if product.get("list_type") == "new" else "Toolify Most Used"
    )
    rank = f" · 榜单 #{product['rank']}" if product.get("rank") else ""
    description = _compact_text(product.get("description"), limit=500) or "公开简介未说明。"
    lines = [
        f"{'#' * heading_level} [{name}]({url})",
        "",
        f"- **来源**：{source}{rank}",
        f"- **公开简介**：{description}",
        f"- **解决什么问题**：{analysis.get('problem') or '等待模型依据公开简介分析。'}",
        f"- **面向谁**：{analysis.get('target_user') or '公开简介未说明。'}",
        f"- **已经覆盖的能力**：{analysis.get('coverage') or '公开简介未说明。'}",
        f"- **个人开发者可研究的缺口**：{analysis.get('solo_gap') or '仅凭简介无法判断。'}",
        f"- **证据限制**：{analysis.get('evidence_limit') or '这里只有榜单/发布简介，没有用户评论，不能判断满意度。'}",
    ]
    if product.get("monthly_visitors"):
        lines.append(f"- **Toolify 月访问量**：{product['monthly_visitors']}")
    if product.get("added_on"):
        lines.append(f"- **Toolify 收录时间**：{product['added_on']}")
    if product.get("review_count") is not None and product.get("source") == "toolify":
        lines.append(f"- **Toolify 评论数**：{product.get('review_count', 0)}；评论正文未公开抓取，不能代替用户反馈。")
    lines.append("")
    return lines


def _report_opportunities(
    posts: list[dict], *, require_market_validation: bool = False, limit: int = 3,
    require_semantic: bool = True,
) -> list[dict]:
    """Choose only the few candidates that belong in a concise daily brief."""
    all_opportunities = build_opportunities(posts, limit=50)
    # A rule-based cluster is not enough for a delivered conclusion. Every
    # source in it needs a real source-grounded brief; otherwise keep it in the
    # observation pool instead of rendering fabricated "未说明" fields.
    if require_semantic:
        all_opportunities = [
            item for item in all_opportunities
            if all(
                any(str((post.get("semantic_brief") or {}).get(key) or "").strip()
                    for key in ("scenario", "pain", "user_wants"))
                for post in item["posts"]
            )
        ]
    repeated = [item for item in all_opportunities if item["post_count"] >= 2]
    direct_signals = [
        item for item in all_opportunities
        if item["post_count"] == 1
        and item["direct_signal_count"]
        and (item["failed_solution_count"] or item["paid_signal_count"])
    ]
    # The free phase only promotes themes that have a matching AI-market
    # validation category.  Everything else stays in the observation pool
    # until Product Hunt/App-review evidence is available.
    candidates = repeated + direct_signals
    if require_market_validation:
        # A repeated theme can become an "already validated direction" when
        # it matches a market category.  A singleton can still be shown as a
        # clearly labelled research lead only when it maps to a named job and
        # carries direct demand plus a failed alternative or price signal.
        candidates = [
            item for item in candidates
            if not item["key"].startswith("signal:")
            and (
                item["post_count"] >= 2
                or (item["direct_signal_count"] and (item["failed_solution_count"] or item["paid_signal_count"]))
            )
        ]
        candidates.sort(
            key=lambda item: (
                item["post_count"] >= 2,
                bool(market_validation_for(item["posts"], [])["watch"]),
                item["market_score"],
            ),
            reverse=True,
        )
    return candidates[:max(1, min(limit, 5))]


def render_opportunity_report(
    posts: list[dict], *, total_saved: int, min_score: int,
    market_products: list[dict] | None = None, opportunity_limit: int = 3,
    toolify_tools: list[dict] | None = None,
    toolify_new: list[dict] | None = None,
    scan_stats: dict | None = None,
) -> str:
    """Render a market-opportunity-first report without raw source text."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    opportunities = _report_opportunities(
        posts, require_market_validation=market_products is not None,
        limit=opportunity_limit,
    )
    lines = [
        "# Money Radar 市场机会日报",
        "",
        f"> {generated_at} · 只显示需求明确、且个人开发者值得进一步验证的 1–3 条。",
        "",
    ]
    if scan_stats:
        lines.extend([
            "## 本次扫描审计",
            "",
            f"- **Reddit 来源**：成功 {scan_stats.get('sources_succeeded', 0)}/{scan_stats.get('sources_attempted', 0)}",
            f"- **读到的帖子**：{scan_stats.get('raw_items', 0)} 条；去重后 {scan_stats.get('unique_items', 0)} 条",
            f"- **进入候选池**：{scan_stats.get('candidate_items', 0)} 条",
            f"- **Product Hunt 新品**：{len(market_products or [])} 个",
            f"- **Toolify Most Used**：{len(toolify_tools or [])} 个；**Toolify New**：{len(toolify_new or [])} 个",
            "",
        ])
    if not opportunities:
        lines.extend([
            "今天没有满足“明确需求 + 失败替代方案/付费意愿”的候选。",
            "",
            "不为凑内容推荐项目；原始帖子继续留在观察池。",
            "",
        ])
        return "\n".join(lines)

    for index, item in enumerate(opportunities, start=1):
        analysis = item["analysis"]
        market = market_validation_for(
            item["posts"], market_products or [], toolify_tools=toolify_tools
        )
        watch = market["watch"]
        lines.extend([
            f"## {index}. {_escape_markdown(item['title'])}",
            "",
            f"**结论**：{analysis['verification_label']}",
            "",
        ])
        for label, key in (("使用场景", "use_case"), ("用户痛点", "pain"),
                           ("现有做法 / 替代", "alternatives"), ("用户明确想要", "build")):
            if analysis.get(key):
                lines.append(f"- **{label}**：{analysis[key]}")
        lines.extend([
            f"- **需求复现**：{item['post_count']} 条 Reddit 原帖，来自 {len(item['subreddits'])} 个社区；失败替代方案 {item['failed_solution_count']} 条。",
            f"- **付费证据**：直接愿意付费 {item['paid_signal_count']} 条；价格上限/拒绝 {item['price_ceiling_count']} 条。两者不混算。",
            f"- **为什么值得研究**：{analysis['research_reason']}",
        ])
        if watch:
            lines.append(f"- **榜单市场验证**：{watch['market_evidence']}（{'、'.join(f'[{source["name"]}]({source["url"]})' for source in market['sources'][1:])}）")
            if market["toolify_tools"]:
                links = "、".join(f"[{tool['name']}]({tool['url']})" for tool in market["toolify_tools"])
                lines.append(f"- **Toolify 同类上榜**：{links}。这只证明同类工具有网站流量，不能证明该痛点已被解决。")
            elif market["toolify_checked"]:
                lines.append("- **Toolify 核验**：已读取 Most Used 榜单，但未找到与此工作流直接匹配的工具；不把无关上榜当证据。")
            else:
                lines.append("- **Toolify 核验**：本次未能读取 Most Used 榜单，因此不使用它作为本次证据。")
        else:
            lines.append("- **榜单市场验证**：当前没有与该工作流精确匹配的免费榜单证据，保持观察。")
        if market["products"]:
            lines.append("- **Product Hunt 验证**：找到与该工作流相邻的近期发布，具体覆盖如下。")
        else:
            lines.append("- **Product Hunt 验证**：当前公开 feed 没有同一工作流的匹配产品；不能用无关产品凑证据。")
        concrete_products = [*market.get("toolify_tools", []), *market.get("products", [])]
        if concrete_products:
            lines.extend(["", "### 已有具体方案", ""])
            for product in concrete_products:
                lines.extend(_render_market_product(product, heading_level=4))
        lines.extend(["### 证据来源", ""])
        for index, post in enumerate(item["posts"], start=1):
            permalink = post.get("permalink") or post.get("url") or ""
            brief = post.get("semantic_brief") or {}
            lines.extend([
                f"- **来源 {index}**：[查看 Reddit 帖子]({permalink})" if permalink else f"- **来源 {index}**：链接不可用",
                "",
            ])
            for label, key in (("场景", "scenario"), ("当前做法 / 工具", "current_workflow"),
                               ("痛点", "pain"), ("槽点 / 缺口", "friction"),
                               ("用户想要什么", "user_wants"), ("可验证首版", "mvp"),
                               ("证据边界", "evidence_boundary")):
                value = _brief_line(brief, key, "")
                if value:
                    lines.append(f"- **{label}**：{value}")
            lines.append("")
            comments = post.get("comments") or []
            if comments and post.get("comment_summary"):
                lines.extend([f"- **评论补充**：{post['comment_summary']}"])
            for comment in comments:
                lines.append(f"  - [查看评论]({comment['permalink']})")
            lines.append("")
        lines.append("")

    observed = [*(market_products or [])[:3], *(toolify_new or [])[:3]]
    if observed:
        lines.extend([
            "## 今日外部产品观察",
            "",
            "这些产品不一定对应上面的 Reddit 需求，但它们代表今天新增或正在被关注的具体方案。",
            "",
        ])
        for product in observed:
            lines.extend(_render_market_product(product, heading_level=3))

    return "\n".join(lines)


def export_obsidian_markdown(
    db_path: str | Path,
    target_dir: str | Path,
    *,
    min_score: int = 4,
    limit: int = 50,
    filename: str = "Money Radar Latest.md",
    bilingual: bool = True,
    market_products: list[dict] | None = None,
    opportunity_limit: int = 3,
    toolify_tools: list[dict] | None = None,
    toolify_new: list[dict] | None = None,
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

    # A source post is evidence, not a delivered recommendation.  Older raw
    # reports recorded source IDs in exported_posts; using that history here
    # would make a newer, better opportunity model blind to the whole corpus.
    # Opportunity-level de-duplication belongs to opportunity keys, not this
    # source-post delivery history.
    posts = list_posts(
        conn,
        min_value_score=min_score,
        limit=max(limit * 20, 300),
    )
    if bilingual:
        # Kept for CLI/backward compatibility. The daily report intentionally
        # does not expose raw source text or translations.
        selected_posts = [
            post for item in _report_opportunities(
                posts, require_market_validation=market_products is not None,
                limit=opportunity_limit, require_semantic=False,
            ) for post in item["posts"]
        ]
        # Fetch the evidence first. The post analysis must not be a gate that
        # silently prevents comment evidence from reaching the model.
        for post in selected_posts:
            try:
                post["comments"] = fetch_post_comments(post.get("permalink") or "", limit=8)
            except RedditFetchError:
                post["comments"] = []
        has_semantic_analysis = add_deepseek_analyses(conn, selected_posts)
        if has_semantic_analysis:
            add_deepseek_comment_summaries(selected_posts)
    meta = metadata(conn)

    output_path = target / filename
    output_path.write_text(
        render_opportunity_report(
            posts, total_saved=meta["total"], min_score=min_score,
            market_products=market_products, opportunity_limit=opportunity_limit,
            toolify_tools=toolify_tools,
            toolify_new=toolify_new,
            scan_stats=meta.get("latest_reddit_scan"),
        ),
        encoding="utf-8",
    )
    # Do not record source posts as "delivered" for opportunity reports.
    # The same Reddit/App/Product Hunt evidence may legitimately support a
    # later opportunity as market validation improves.
    conn.close()
    return output_path
