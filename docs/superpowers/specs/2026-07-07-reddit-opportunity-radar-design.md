# Reddit Opportunity Radar Design

## Goal

Build a local, self-use web app that surfaces recent popular English Reddit posts where people ask for help, request recommendations, complain about painful workflows, or look for tools. The app should keep the original post list as the main experience and add a lightweight opportunity annotation beside each item.

## Scope

The first version focuses only on English Reddit. It does not include Chinese platforms, public deployment, login, team features, or paid-product workflows. The app is meant to help validate whether Reddit contains useful demand signals before investing in a heavier product.

## Sources

The app monitors selected subreddits across four channels:

- Entrepreneurship and small business: `Entrepreneur`, `startups`, `smallbusiness`, `sideproject`, `SaaS`, `solopreneur`
- AI, SaaS, and automation: `ChatGPT`, `artificial`, `LocalLLaMA`, `Automation`, `NoCode`, `webdev`
- Personal finance, investing, and saving money: `personalfinance`, `investing`, `povertyfinance`, `financialindependence`, `sidehustle`
- Productivity, tools, and workflows: `productivity`, `Notion`, `excel`, `freelance`, `marketing`, `dataanalysis`

Fetching should use Reddit's API-compatible JSON/OAuth flow rather than brittle HTML scraping. The app stores only the post data needed for local review and always links back to the original Reddit post.

## Fetching Strategy

The MVP fetches recent popular posts once per day. For each configured subreddit, it reads the weekly top listing and keeps posts that pass basic engagement and demand-signal filters.

Default filters:

- Time window: top posts from the last week
- Engagement: at least 5 comments or at least 10 upvotes
- Demand signal: title or body includes help, recommendation, tool-search, pain, workaround, or frustration language

The user can run the fetch manually at first. Daily automation can be added with cron or launchd after the data quality looks useful.

## Annotation

Each saved post receives a medium-strength annotation:

- Pain summary: one short sentence describing what the poster appears to be struggling with
- Opportunity type: one of `SaaS`, `small tool`, `template`, `content`, `service`, `automation`, `data product`, or `unclear`
- Value score: integer from 1 to 5

The first implementation can use a deterministic local annotator so the app works without paid model credentials. The annotation module should be isolated so an LLM-backed annotator can replace it later.

## Web Experience

The first screen is the actual radar, not a marketing page.

The page shows a dense, scannable list of original Reddit posts. Each card includes:

- Post title
- Subreddit
- Channel
- Created time
- Upvotes and comment count
- Short excerpt from the original self text, when available
- Highlighted demand-signal phrase category
- Pain summary, opportunity type, and value score
- Link to open the original Reddit post

The page should support:

- Channel filter
- Subreddit filter
- Minimum value score filter
- Search across title, excerpt, subreddit, and annotation text
- Refresh button that reloads data from the local API

## Data Model

Use SQLite for local persistence. Store one row per Reddit post keyed by Reddit post ID. Repeated fetches update existing rows rather than creating duplicates.

Core fields:

- `reddit_id`
- `subreddit`
- `channel`
- `title`
- `selftext`
- `permalink`
- `url`
- `author`
- `score`
- `num_comments`
- `created_utc`
- `fetched_at`
- `signal`
- `pain_summary`
- `opportunity_type`
- `value_score`

## Architecture

Use Python standard library components for the MVP:

- A small package containing configuration, Reddit fetching, filtering, annotation, storage, and HTTP serving
- SQLite for local data storage
- Static HTML, CSS, and browser JavaScript for the UI
- A CLI entry point to initialize the database, fetch posts, and run the local web server

This avoids dependency installation and keeps the MVP easy to run on the local machine.

## Error Handling

If Reddit credentials are missing, the fetch command should print clear setup instructions and exit without modifying data. If a subreddit request fails, the fetch should continue with the remaining subreddits and report the failure at the end. If annotation fails, the post can still be stored with `unclear` annotation fields.

## Verification

The MVP should include tests for:

- Demand-signal filtering
- Annotation shape and score range
- SQLite upsert behavior
- API response shape for the local web server

Manual verification:

- Initialize the database
- Insert or fetch sample posts
- Start the local server
- Open the radar page
- Confirm filters, search, scores, and Reddit outbound links work

