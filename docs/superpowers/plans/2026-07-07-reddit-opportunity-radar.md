# Reddit Opportunity Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dependency-light local Reddit opportunity radar that fetches recent popular English Reddit posts, stores them in SQLite, annotates demand signals, and serves a local web UI.

**Architecture:** Use a Python standard-library package with separate modules for config, filtering, annotation, Reddit API access, SQLite storage, and HTTP serving. Serve static HTML/CSS/JS plus JSON API endpoints from the same local process. Keep annotation deterministic in the MVP so the app works before LLM credentials are added.

**Tech Stack:** Python 3 standard library, SQLite, unittest, static HTML/CSS/JavaScript.

---

## File Structure

- `README.md`: local setup, Reddit credential instructions, run commands, daily scheduling note.
- `money_radar/__init__.py`: package marker and version.
- `money_radar/config.py`: channel, subreddit, keyword, and default path configuration.
- `money_radar/filters.py`: demand-signal detection and engagement filtering.
- `money_radar/annotator.py`: deterministic opportunity annotation.
- `money_radar/storage.py`: SQLite schema, upsert, and query functions.
- `money_radar/reddit.py`: Reddit OAuth token and weekly top-post fetcher.
- `money_radar/server.py`: local HTTP server and JSON API.
- `money_radar/cli.py`: command-line entry point for init, fetch, serve, and sample data.
- `public/index.html`: radar UI shell.
- `public/styles.css`: app layout and visual styling.
- `public/app.js`: fetches local API data and implements filters/search.
- `tests/test_filters.py`: demand and engagement filter coverage.
- `tests/test_annotator.py`: annotation coverage.
- `tests/test_storage.py`: SQLite schema and upsert coverage.
- `tests/test_server.py`: local API shape coverage.

## Tasks

### Task 1: Create Package Skeleton and Configuration

**Files:**
- Create: `money_radar/__init__.py`
- Create: `money_radar/config.py`
- Create: `README.md`

- [ ] Create the package directory and version file.
- [ ] Define channels, subreddits, demand keywords, and default database/static paths.
- [ ] Write README instructions for credentials and local commands.

### Task 2: Implement Filtering and Annotation With Tests

**Files:**
- Create: `money_radar/filters.py`
- Create: `money_radar/annotator.py`
- Create: `tests/test_filters.py`
- Create: `tests/test_annotator.py`

- [ ] Write tests for demand-signal matching, engagement filtering, and annotation score bounds.
- [ ] Implement keyword-based signal detection.
- [ ] Implement deterministic annotation returning pain summary, opportunity type, and value score.
- [ ] Run `python3 -m unittest tests.test_filters tests.test_annotator`.

### Task 3: Implement SQLite Storage With Tests

**Files:**
- Create: `money_radar/storage.py`
- Create: `tests/test_storage.py`

- [ ] Write tests for schema initialization, post upsert, and sorted querying.
- [ ] Implement SQLite schema creation.
- [ ] Implement upsert and list query helpers.
- [ ] Run `python3 -m unittest tests.test_storage`.

### Task 4: Implement Reddit Fetcher and CLI

**Files:**
- Create: `money_radar/reddit.py`
- Create: `money_radar/cli.py`

- [ ] Implement Reddit app-only OAuth token retrieval from environment variables.
- [ ] Implement weekly top-post fetching for configured subreddits.
- [ ] Implement CLI commands: `init`, `fetch`, `sample`, and `serve`.
- [ ] Ensure missing Reddit credentials produce a clear error.

### Task 5: Implement Local Server and UI

**Files:**
- Create: `money_radar/server.py`
- Create: `public/index.html`
- Create: `public/styles.css`
- Create: `public/app.js`
- Create: `tests/test_server.py`

- [ ] Write tests for `/api/posts` response shape using a temporary SQLite database.
- [ ] Implement static file serving and `/api/posts`.
- [ ] Implement a dense radar UI with channel, subreddit, score, and search filters.
- [ ] Run `python3 -m unittest tests.test_server`.

### Task 6: Verify End to End

**Files:**
- Modify: `README.md`

- [ ] Run the full test suite with `python3 -m unittest`.
- [ ] Run `python3 -m money_radar.cli init`.
- [ ] Run `python3 -m money_radar.cli sample`.
- [ ] Start the server with `python3 -m money_radar.cli serve --port 8765`.
- [ ] Fetch `http://127.0.0.1:8765/api/posts` and confirm JSON contains sample posts.
- [ ] Update README with any command corrections found during verification.

