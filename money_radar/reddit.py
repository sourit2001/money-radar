"""Reddit RSS fetcher — no API credentials required.

Uses Reddit's public RSS feeds via subprocess curl to avoid Python TLS
fingerprint blocking.  Falls back gracefully when requests are rate-limited.
"""

from __future__ import annotations

import hashlib
from html import unescape
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote_plus, urlparse

from .annotator import annotate_post
from .config import (
    CHANNELS,
    COOLDOWN_429,
    FETCH_DELAY,
    SEARCH_QUERIES,
    SUBREDDIT_TO_CHANNEL,
    USER_AGENT,
)
from .filters import assess_opportunity, is_candidate_post

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_cooldown_until: float = 0.0  # epoch timestamp; skip optional requests until then


class RedditFetchError(RuntimeError):
    """Raised when a Reddit fetch fails."""


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _curl_fetch(url: str, timeout: int = 20) -> tuple[str, int]:
    """Fetch *url* via subprocess curl.

    Returns ``(body, http_status_code)``.  Using curl avoids the HTTP 403
    errors that Python's ``urllib`` triggers due to TLS fingerprinting.
    """
    try:
        result = subprocess.run(
            [
                "curl",
                "-sL",
                "--compressed",
                "--max-time",
                str(timeout),
                "-H",
                f"User-Agent: {USER_AGENT}",
                "-H",
                "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-H",
                "Accept-Language: en-US,en;q=0.9",
                "-w",
                "\n__HTTP_CODE__:%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except FileNotFoundError:
        raise RedditFetchError(
            "curl is not installed.  Install curl to use Reddit RSS fetching."
        )
    except subprocess.TimeoutExpired:
        raise RedditFetchError(f"Timeout fetching {url}")

    raw = result.stdout
    # Extract HTTP status code from the trailer we appended via -w
    status = 0
    if "__HTTP_CODE__:" in raw:
        parts = raw.rsplit("__HTTP_CODE__:", 1)
        raw = parts[0]
        try:
            status = int(parts[1].strip())
        except ValueError:
            pass
    return raw, status


def _rate_limited_fetch(url: str, *, optional: bool = False) -> str | None:
    """Fetch with global 429 cooldown awareness.

    If *optional* is True and we are inside a cooldown window the request is
    silently skipped (returns ``None``).
    """
    global _cooldown_until

    now = time.time()
    if optional and now < _cooldown_until:
        remaining = int(_cooldown_until - now)
        print(f"  ⏳ Skipping optional request (429 cooldown, {remaining}s left)")
        return None

    body, status = _curl_fetch(url)

    if status == 429:
        _cooldown_until = time.time() + COOLDOWN_429
        msg = f"Rate-limited (429) fetching {url}. Cooling down for {COOLDOWN_429}s."
        if optional:
            print(f"  ⚠️  {msg}")
            return None
        raise RedditFetchError(msg)

    if status == 403:
        if optional:
            print(f"  ⚠️  403 Forbidden for {url} (skipped)")
            return None
        raise RedditFetchError(f"403 Forbidden: {url}")

    if status != 200:
        if optional:
            print(f"  ⚠️  HTTP {status} for {url} (skipped)")
            return None
        raise RedditFetchError(f"HTTP {status} fetching {url}")

    return body


# ---------------------------------------------------------------------------
# RSS parsing
# ---------------------------------------------------------------------------

# Atom namespace used by Reddit RSS feeds
_ATOM_NS = "http://www.w3.org/2005/Atom"


def _extract_reddit_id_from_link(link: str) -> str:
    """Pull a stable Reddit post id from a permalink."""
    parts = [p for p in urlparse(link).path.strip("/").split("/") if p]
    if "comments" in parts:
        idx = parts.index("comments")
        if len(parts) > idx + 1:
            return parts[idx + 1]
    # Fallback: hash the URL
    return hashlib.md5(link.encode()).hexdigest()[:12]


def _extract_subreddit_from_link(link: str) -> str:
    match = re.search(r"/r/(\w+)", link)
    return match.group(1) if match else ""


def clean_html_text(raw: str) -> str:
    """Strip RSS HTML, decode entities, and remove Reddit feed boilerplate."""
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+submitted by\s+.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", text).strip()


def parse_rss_entries(xml_text: str) -> list[dict]:
    """Parse a Reddit Atom/RSS feed into a list of post dicts.

    Each dict has: ``reddit_id``, ``title``, ``selftext``, ``permalink``,
    ``subreddit``, ``author``, ``score`` (0), ``num_comments`` (0).
    """
    posts: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return posts

    # Reddit RSS uses Atom format: <feed><entry>…</entry></feed>
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{_ATOM_NS}}}title")
        link_el = entry.find(f"{{{_ATOM_NS}}}link")
        content_el = entry.find(f"{{{_ATOM_NS}}}content")
        author_el = entry.find(f"{{{_ATOM_NS}}}author/{{{_ATOM_NS}}}name")
        published_el = entry.find(f"{{{_ATOM_NS}}}published")
        updated_el = entry.find(f"{{{_ATOM_NS}}}updated")

        link = (link_el.get("href") if link_el is not None else "") or ""
        if not link:
            continue

        title = (title_el.text if title_el is not None else "") or ""
        selftext = clean_html_text((content_el.text if content_el is not None else "") or "")
        author = (author_el.text if author_el is not None else "") or ""
        # Strip the /u/ prefix Reddit sometimes includes
        if author.startswith("/u/"):
            author = author[3:]

        subreddit = _extract_subreddit_from_link(link)
        reddit_id = _extract_reddit_id_from_link(link)
        date_text = (
            (published_el.text if published_el is not None else "")
            or (updated_el.text if updated_el is not None else "")
            or ""
        )
        try:
            created_utc = datetime.fromisoformat(
                date_text.replace("Z", "+00:00")
            ).timestamp()
        except ValueError:
            created_utc = 0

        posts.append(
            {
                "id": reddit_id,
                "title": title,
                "selftext": selftext,
                "permalink": link,
                "url": link,
                "subreddit": subreddit,
                "author": author,
                # RSS does not include engagement numbers
                "score": 0,
                "num_comments": 0,
                "created_utc": created_utc,
                "stickied": False,
                "over_18": False,
            }
        )

    return posts


# ---------------------------------------------------------------------------
# High-level fetch functions
# ---------------------------------------------------------------------------


def configured_subreddits() -> list[str]:
    return [subreddit for details in CHANNELS.values() for subreddit in details["subreddits"]]


def fetch_subreddit_rss(subreddit: str, sort: str = "hot") -> list[dict]:
    """Fetch posts from a single subreddit RSS feed."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}/.rss"
    body = _rate_limited_fetch(url)
    if body is None:
        return []
    return parse_rss_entries(body)


def fetch_subreddit_group_rss(subreddits: Iterable[str], sort: str = "hot") -> list[dict]:
    """Fetch one combined feed to avoid one rate-limited call per subreddit."""
    joined = "+".join(subreddits)
    url = f"https://www.reddit.com/r/{joined}/{sort}/.rss"
    body = _rate_limited_fetch(url)
    if body is None:
        return []
    return parse_rss_entries(body)


def fetch_search_rss(query: str) -> list[dict]:
    """Search Reddit via the search RSS endpoint."""
    encoded = quote_plus(query)
    url = f"https://www.reddit.com/search.rss?q={encoded}&sort=new&t=month&limit=100"
    body = _rate_limited_fetch(url, optional=True)
    if body is None:
        return []
    return parse_rss_entries(body)


def fetch_post_stats(permalink: str) -> dict:
    """Try to fetch structured stats (upvotes, comments) for a single post.

    Uses the post's ``.json`` endpoint.  This is optional — if it fails the
    caller just gets an empty dict and the post is stored without stats.
    """
    clean_url = permalink.split("?")[0].rstrip("/")
    json_url = f"{clean_url}.json"

    body = _rate_limited_fetch(json_url, optional=True)
    if body is None:
        return {}

    try:
        payload = json.loads(body)
        post_data = payload[0]["data"]["children"][0]["data"]
        return {
            "score": int(post_data.get("ups") or post_data.get("score") or 0),
            "num_comments": int(post_data.get("num_comments") or 0),
        }
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return {}


def fetch_post_comments(permalink: str, limit: int = 3) -> list[dict]:
    """Fetch a few substantive public comments for a selected report source."""
    clean_url = permalink.split("?")[0].rstrip("/")
    body = _rate_limited_fetch(f"{clean_url}.json?limit={max(1, min(limit, 5))}", optional=True)
    if not body:
        return []
    try:
        children = json.loads(body)[1]["data"]["children"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return []
    comments = []
    for child in children:
        data = child.get("data") or {}
        text = clean_html_text(data.get("body") or "")
        if child.get("kind") != "t1" or len(text) < 40 or text in {"[deleted]", "[removed]"}:
            continue
        comments.append({
            "body": text,
            "permalink": f"https://www.reddit.com{data.get('permalink', '')}",
            "score": int(data.get("score") or 0),
        })
    return sorted(comments, key=lambda item: item["score"], reverse=True)[:limit]


def normalize_reddit_post(post: dict, fetched_at: str) -> dict:
    subreddit = post.get("subreddit") or ""
    permalink = post.get("permalink") or ""
    full_permalink = permalink if permalink.startswith("http") else f"https://www.reddit.com{permalink}"
    normalized = {
        "reddit_id": post.get("id") or "",
        "subreddit": subreddit,
        "channel": SUBREDDIT_TO_CHANNEL.get(subreddit.lower(), "discovery"),
        "title": post.get("title") or "",
        "selftext": post.get("selftext") or "",
        "permalink": full_permalink,
        "url": post.get("url") or full_permalink,
        "author": post.get("author") or "",
        "score": int(post.get("score") or 0),
        "num_comments": int(post.get("num_comments") or 0),
        "created_utc": float(post.get("created_utc") or 0),
        "fetched_at": fetched_at,
        "raw_json": post,
    }
    normalized.update(annotate_post(normalized))
    return normalized


def fetch_candidate_posts(
    subreddits: Iterable[str] | None = None,
) -> tuple[list[dict], list[str], dict]:
    """Fetch and filter candidate posts from Reddit RSS feeds.

    No API credentials needed.  Uses Reddit's public RSS endpoints via curl.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    posts: list[dict] = []
    failures: list[str] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    raw_ids: set[str] = set()
    details: list[dict] = []
    raw_items = 0
    sources_succeeded = 0

    subs = list(configured_subreddits() if subreddits is None else subreddits)
    groups = [subs[index:index + 6] for index in range(0, len(subs), 6)]
    queries = list(SEARCH_QUERIES)
    query_groups = queries

    def collect(raw_posts: list[dict], *, search_result: bool) -> int:
        count = 0
        for raw_post in raw_posts:
            pid = raw_post.get("id", "")
            if pid:
                raw_ids.add(pid)
            normalized_title = re.sub(r"\W+", " ", raw_post.get("title", "").lower()).strip()
            if pid in seen_ids or normalized_title in seen_titles:
                continue
            assessment = assess_opportunity(raw_post)
            if search_result and assessment.tier == "latent":
                continue
            if is_candidate_post(raw_post):
                posts.append(normalize_reddit_post(raw_post, fetched_at))
                seen_ids.add(pid)
                seen_titles.add(normalized_title)
                count += 1
        return count

    # Search comes first: these feeds have much higher demand density than hot
    # pages, so rate limiting cannot starve the most valuable source.
    if query_groups:
        print(f"  Searching {len(queries)} demand phrases in {len(query_groups)} groups ...")
    for index, combined_query in enumerate(query_groups, 1):
        print(
            f"  [search {index}/{len(query_groups)}] demand query group ...",
            end=" ", flush=True,
        )
        try:
            raw_posts = fetch_search_rss(combined_query)
        except RedditFetchError as exc:
            failures.append(str(exc))
            print("FAILED")
        else:
            raw_items += len(raw_posts)
            sources_succeeded += 1
            count = collect(raw_posts, search_result=True)
            details.append({"kind": "search", "label": combined_query, "raw": len(raw_posts), "candidates": count})
            print(f"{len(raw_posts)} posts, {count} new candidates")
        if index < len(query_groups) or groups:
            time.sleep(FETCH_DELAY)

    # Hot feeds are a lower-density supplement for latent pain that does not
    # use one of the explicit search phrases.
    if groups:
        print(f"\n  Scanning {len(groups)} grouped hot feeds ...")
    for index, group in enumerate(groups, 1):
        label = "+".join(group)
        print(f"  [feed {index}/{len(groups)}] r/{label} ...", end=" ", flush=True)
        try:
            raw_posts = fetch_subreddit_group_rss(group)
        except RedditFetchError as exc:
            failures.append(str(exc))
            print("FAILED")
        else:
            raw_items += len(raw_posts)
            sources_succeeded += 1
            count = collect(raw_posts, search_result=False)
            details.append({"kind": "feed", "label": label, "raw": len(raw_posts), "candidates": count})
            print(f"{len(raw_posts)} posts, {count} candidates")
        if index < len(groups):
            time.sleep(FETCH_DELAY)

    stats = {
        "run_at": fetched_at,
        "source": "reddit",
        "sources_attempted": len(query_groups) + len(groups),
        "sources_succeeded": sources_succeeded,
        "raw_items": raw_items,
        "unique_items": len(raw_ids),
        "candidate_items": len(posts),
        "failures": failures,
        "details": details,
    }
    return posts, failures, stats
