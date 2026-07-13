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
from .reddit import RedditFetchError, clean_html_text, fetch_candidate_posts
from .server import serve
from .storage import connect, init_db, upsert_posts


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
        posts, failures = fetch_candidate_posts(subreddits=subs)
    except RedditFetchError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    count = upsert_posts(conn, posts)
    print(f"\n✅ Stored {count} candidate posts.")
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
