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

To export the current shortlist to Obsidian:

```bash
python3 -m money_radar.cli export-obsidian \
  '/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work副本/Reddit Money Radar'
```

## Notes

- **Rate Limits**: Reddit RSS has strict rate limits. The fetch command waits between requests to avoid being blocked. A full scan of all grouped subreddit feeds + search queries can take several minutes.
- **No engagement data from RSS**: RSS feeds do not include upvote or comment
  counts. Missing engagement is treated as unknown; a post still has to pass
  the stricter multi-signal content assessment.
- **curl required**: HTTP requests are made via subprocess `curl` because Reddit blocks Python's `urllib` based on TLS fingerprinting.

## Daily Run

For a manual daily run:

```bash
python3 -m money_radar.cli fetch
python3 -m money_radar.cli refilter --prune
python3 -m money_radar.cli export-obsidian \
  '/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work副本/Reddit Money Radar'
```

For macOS automation, copy `automation/money-radar/` to
`/Users/lizhu/Automations/money-radar/`, install
`com.lizhu.money-radar.plist` into `~/Library/LaunchAgents/`, and load it with
`launchctl`. The provided LaunchAgent runs every day at 04:00 Beijing time
when the Mac is awake and writes a
dated local Markdown report:

```text
/Users/lizhu/Automations/money-radar/obsidian/Money Radar YYYY-MM-DD.md
```

On this Mac, that local export directory is linked into the iCloud Obsidian
vault at:

```text
/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work副本/Reddit Money Radar/
```

The directory link keeps LaunchAgent writes out of iCloud's FileProvider
permission path while still letting Obsidian see each dated report.
