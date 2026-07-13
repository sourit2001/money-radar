# Money Radar

Local Reddit Opportunity Radar for finding recent popular English Reddit posts that contain help requests, tool searches, workflow pain, and recommendation demand.

## What It Does

- Scans selected English subreddits via RSS feeds (no API key needed).
- Searches Reddit for demand-signal keywords (e.g. "looking for software", "alternative to").
- Keeps posts only when explicit tool/automation intent is supported by a
  concrete workflow, professional context, recurring need, or pain signal.
- Stores posts in local SQLite.
- Shows the original post list in a local web UI.
- Adds medium-strength opportunity notes: pain summary, opportunity type, and value score.

## Setup

This MVP uses only the Python standard library. **No Reddit API credentials are needed** — the app fetches data from Reddit's public RSS feeds via `curl`.

Requirements:
- Python 3.10+
- `curl` (pre-installed on macOS and most Linux)

## Commands

```bash
python3 -m money_radar.cli init
python3 -m money_radar.cli sample
python3 -m money_radar.cli serve --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

To fetch Reddit data:

```bash
python3 -m money_radar.cli fetch
```

To re-apply the latest precision rules to saved posts:

```bash
python3 -m money_radar.cli refilter          # preview
python3 -m money_radar.cli refilter --prune  # remove rejected noise
```

## Notes

- **Rate Limits**: Reddit RSS has strict rate limits. The fetch command waits ~10 seconds between requests to avoid being blocked. A full scan of all subreddits + search queries takes about 5 minutes.
- **No engagement data from RSS**: RSS feeds do not include upvote or comment
  counts. Missing engagement is treated as unknown; a post still has to pass
  the stricter multi-signal content assessment.
- **curl required**: HTTP requests are made via subprocess `curl` because Reddit blocks Python's `urllib` based on TLS fingerprinting.

## Daily Run

For the MVP, run `python3 -m money_radar.cli fetch` manually once per day. After the subreddit and keyword quality looks good, this can be scheduled with cron or launchd.
