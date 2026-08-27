"""Command-line interface for the local Reddit radar."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .annotator import annotate_post
from .config import DEFAULT_DB_PATH, SUBREDDIT_TO_CHANNEL
from .filters import assess_opportunity, is_candidate_post
from .market import (
    fetch_product_hunt_feed, fetch_toolify_most_used, fetch_toolify_new,
    render_market_preview,
)
from .obsidian import export_obsidian_markdown
from .reddit import RedditFetchError, clean_html_text, fetch_candidate_posts
from .server import serve
from .storage import connect, init_db, save_scan_run, upsert_posts
from .translation import argos_english_to_chinese
from .semantic_analysis import add_market_product_analyses


SAMPLE_POSTS = [
    {
        "reddit_id": "sample_ai_reports",
        "subreddit": "Automation",
        "channel": "ai_saas_automation",
        "title": "Is there a way to automate weekly client reports?",
        "selftext": "I spend every Friday copying metrics into slides. It is manual and takes too long.",
        "permalink": "https://www.reddit.com/r/Automation/comments/sample_ai_reports/example/",
        "url": "https://www.reddit.com/r/Automation/comments/sample_ai_reports/example/",
        "author": "sample_user",
        "score": 146,
        "num_comments": 37,
        "created_utc": 1783382400,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "raw_json": {},
    },
    {
        "reddit_id": "sample_budget_tool",
        "subreddit": "personalfinance",
        "channel": "finance",
        "title": "Looking for an app for irregular income budgeting",
        "selftext": "Most budget apps assume steady paychecks. Freelance income makes planning frustrating.",
        "permalink": "https://www.reddit.com/r/personalfinance/comments/sample_budget_tool/example/",
        "url": "https://www.reddit.com/r/personalfinance/comments/sample_budget_tool/example/",
        "author": "sample_user",
        "score": 88,
        "num_comments": 19,
        "created_utc": 1783296000,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "raw_json": {},
    },
    {
        "reddit_id": "sample_excel",
        "subreddit": "excel",
        "channel": "productivity",
        "title": "Need help cleaning messy supplier spreadsheets every month",
        "selftext": "The format changes constantly and the manual cleanup is annoying.",
        "permalink": "https://www.reddit.com/r/excel/comments/sample_excel/example/",
        "url": "https://www.reddit.com/r/excel/comments/sample_excel/example/",
        "author": "sample_user",
        "score": 51,
        "num_comments": 12,
        "created_utc": 1783209600,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "raw_json": {},
    },
]


def db_path_from_args(args: argparse.Namespace) -> Path:
    return Path(args.db).expanduser().resolve()


def command_init(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args))
    init_db(conn)
    print(f"Initialized database at {db_path_from_args(args)}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args))
    init_db(conn)
    posts = []
    for post in SAMPLE_POSTS:
        enriched = dict(post)
        enriched.update(annotate_post(enriched))
        posts.append(enriched)
    count = upsert_posts(conn, posts)
    print(f"Inserted {count} sample posts into {db_path_from_args(args)}")
    return 0


def command_fetch(args: argparse.Namespace) -> int:
    from .config import FETCH_DELAY, SEARCH_QUERIES
    from .reddit import configured_subreddits

    conn = connect(db_path_from_args(args))
    init_db(conn)

    subs = [] if args.search_only else configured_subreddits()
    queries = SEARCH_QUERIES
    subreddit_feeds = (len(subs) + 5) // 6
    search_feeds = len(queries)
    total_sources = subreddit_feeds + search_feeds
    est_minutes = (total_sources * FETCH_DELAY) // 60
    print(
        f"Fetching {len(subs)} subreddits in {subreddit_feeds} grouped feeds "
        f"+ {search_feeds} high-intent searches "
        f"(~{est_minutes} min with {FETCH_DELAY}s delay) ..."
    )

    try:
        posts, failures, scan_stats = fetch_candidate_posts(subreddits=subs)
    except RedditFetchError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    count = upsert_posts(conn, posts)
    save_scan_run(conn, scan_stats)
    print(
        f"\n✅ Scanned {scan_stats['raw_items']} feed items "
        f"({scan_stats['unique_items']} unique) across "
        f"{scan_stats['sources_succeeded']}/{scan_stats['sources_attempted']} sources; "
        f"stored {count} candidate posts."
    )
    if failures:
        print(f"⚠️  {len(failures)} source(s) failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
    return 0 if not failures else 1


def command_serve(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args))
    init_db(conn)
    serve(db_path_from_args(args), host=args.host, port=args.port)
    return 0


def command_refilter(args: argparse.Namespace) -> int:
    """Re-run current precision rules against already saved raw posts."""
    conn = connect(db_path_from_args(args))
    init_db(conn)
    rows = conn.execute(
        "SELECT * FROM posts ORDER BY created_utc DESC, value_score DESC"
    ).fetchall()
    kept = 0
    rejected_ids: list[tuple[str]] = []
    seen_titles: set[str] = set()
    seen_bodies: set[str] = set()
    for row in rows:
        post = dict(row)
        try:
            raw = json.loads(post.get("raw_json") or "{}")
        except (ValueError, TypeError):
            raw = {}
        candidate = {**raw, **post}
        candidate["selftext"] = clean_html_text(candidate.get("selftext") or "")
        title_key = re.sub(r"\W+", " ", candidate.get("title", "").lower()).strip()
        body_key = re.sub(r"\W+", " ", candidate["selftext"].lower()).strip()[:500]
        duplicate = title_key in seen_titles or (body_key and body_key in seen_bodies)
        in_scope = candidate.get("subreddit", "").lower() in SUBREDDIT_TO_CHANNEL
        assessment = assess_opportunity(candidate)
        allowed_tier = not (
            candidate.get("channel") == "discovery" and assessment.tier == "latent"
        )
        # Existing configured communities stay in scope; cross-community
        # discovery rows are also valid when they are direct demand.
        allowed_scope = in_scope or candidate.get("channel") == "discovery"
        if allowed_scope and allowed_tier and not duplicate and is_candidate_post(candidate):
            annotation = annotate_post(candidate)
            conn.execute(
                """UPDATE posts SET selftext=?, signal=?, signal_phrase=?, pain_summary=?,
                   opportunity_type=?, value_score=? WHERE reddit_id=?""",
                (
                    candidate["selftext"], annotation["signal"], annotation["signal_phrase"],
                    annotation["pain_summary"], annotation["opportunity_type"],
                    annotation["value_score"], post["reddit_id"],
                ),
            )
            kept += 1
            seen_titles.add(title_key)
            if body_key:
                seen_bodies.add(body_key)
        else:
            rejected_ids.append((post["reddit_id"],))
    if args.prune and rejected_ids:
        conn.executemany("DELETE FROM posts WHERE reddit_id=?", rejected_ids)
    conn.commit()
    action = "removed" if args.prune else "would remove"
    print(f"Precision refilter: kept {kept}, {action} {len(rejected_ids)} noisy posts.")
    return 0


def command_export_obsidian(args: argparse.Namespace) -> int:
    try:
        market_products = fetch_product_hunt_feed()
    except RuntimeError as exc:
        print(f"⚠️ Product Hunt public feed unavailable: {exc}", file=sys.stderr)
        market_products = []
    try:
        toolify_tools = fetch_toolify_most_used()
    except RuntimeError as exc:
        print(f"⚠️ Toolify Most Used unavailable: {exc}", file=sys.stderr)
        toolify_tools = None
    try:
        toolify_new = fetch_toolify_new()
    except RuntimeError as exc:
        print(f"⚠️ Toolify New unavailable: {exc}", file=sys.stderr)
        toolify_new = None
    priority_names = ("salesforce", "hubspot", "jotform", "capcut", "elevenlabs", "turboscribe", "demi")
    priority_toolify = [
        tool for tool in (toolify_tools or [])
        if any(term in tool.get("name", "").lower() for term in priority_names)
    ][:7]
    market_terms = ("crm", "sales", "follow", "video", "subtitle", "brand", "prompt", "commission")
    related_product_hunt = [
        product for product in market_products
        if any(term in f"{product.get('title', '')} {product.get('description', '')}".lower() for term in market_terms)
    ][:5]
    products_to_analyze = []
    seen_product_ids = set()
    for product in market_products[:3] + related_product_hunt + (toolify_new or [])[:3] + priority_toolify:
        product_id = (product.get("source"), product.get("id"))
        if product_id in seen_product_ids:
            continue
        seen_product_ids.add(product_id)
        products_to_analyze.append(product)
    add_market_product_analyses(products_to_analyze)
    output_path = export_obsidian_markdown(
        db_path_from_args(args),
        args.target_dir,
        min_score=args.min_score,
        limit=args.limit,
        filename=args.filename,
        bilingual=args.bilingual,
        market_products=market_products,
        toolify_tools=toolify_tools,
        toolify_new=toolify_new,
        opportunity_limit=args.opportunity_limit,
    )
    print(f"Exported Obsidian report to {output_path}")
    return 0


def command_market_preview(args: argparse.Namespace) -> int:
    """Write a source-faithful Product Hunt and AI-market preview."""
    try:
        products = fetch_product_hunt_feed()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        toolify_tools = fetch_toolify_most_used()
    except RuntimeError as exc:
        print(f"⚠️ Toolify Most Used unavailable: {exc}", file=sys.stderr)
        toolify_tools = None
    target = Path(args.target_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    output_path = target / args.filename
    output_path.write_text(
        render_market_preview(
            products, toolify_tools=toolify_tools, translator=argos_english_to_chinese
        ),
        encoding="utf-8",
    )
    print(f"Exported market preview to {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Reddit opportunity radar")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize the SQLite database")
    init_parser.set_defaults(func=command_init)

    sample_parser = subparsers.add_parser("sample", help="Insert sample posts for UI testing")
    sample_parser.set_defaults(func=command_sample)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch recent popular Reddit opportunity posts")
    fetch_parser.add_argument(
        "--search-only", action="store_true",
        help="Run high-intent Reddit searches without scanning hot feeds",
    )
    fetch_parser.set_defaults(func=command_fetch)

    refilter_parser = subparsers.add_parser(
        "refilter", help="Re-score saved posts with the current precision rules"
    )
    refilter_parser.add_argument(
        "--prune", action="store_true", help="Delete posts rejected by the current rules"
    )
    refilter_parser.set_defaults(func=command_refilter)

    export_parser = subparsers.add_parser(
        "export-obsidian", help="Export saved posts to an Obsidian-friendly Markdown report"
    )
    export_parser.add_argument("target_dir", help="Directory where the Markdown report should be written")
    export_parser.add_argument("--min-score", type=int, default=4)
    export_parser.add_argument("--limit", type=int, default=50)
    export_parser.add_argument(
        "--opportunity-limit", type=int, default=3,
        help="Number of daily opportunities to show (1–5, default: 3)",
    )
    export_parser.add_argument("--filename", default="Money Radar Latest.md")
    export_parser.add_argument(
        "--bilingual", action="store_true", dest="bilingual", default=True,
        help="Add offline Chinese translations with Argos (default)"
    )
    export_parser.add_argument(
        "--no-bilingual", action="store_false", dest="bilingual",
        help="Skip Chinese translations for this export"
    )
    export_parser.set_defaults(func=command_export_obsidian)

    market_parser = subparsers.add_parser(
        "market-preview", help="Export Product Hunt and AI market validation preview"
    )
    market_parser.add_argument("target_dir", help="Directory where the Markdown preview is written")
    market_parser.add_argument("--filename", default="Money Radar 市场验证预览.md")
    market_parser.set_defaults(func=command_market_preview)

    serve_parser = subparsers.add_parser("serve", help="Run the local web server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.set_defaults(func=command_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
