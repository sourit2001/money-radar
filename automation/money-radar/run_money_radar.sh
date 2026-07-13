#!/bin/zsh
set -eu

APP_DIR="/Users/lizhu/Automations/money-radar"
REPO_DIR="$APP_DIR/repo"
DB_PATH="$APP_DIR/data/money_radar.sqlite3"
LOG_DIR="/private/tmp/com.lizhu.money-radar"
VAULT_DIR="/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work副本/Reddit Money Radar"
REPO_URL="https://github.com/sourit2001/money-radar.git"

mkdir -p "$APP_DIR" "$APP_DIR/data" "$LOG_DIR" "$VAULT_DIR"

{
  echo "===== $(date -u '+%Y-%m-%d %H:%M:%S UTC') money-radar run ====="

  if [ ! -d "$REPO_DIR/.git" ]; then
    rm -rf "$REPO_DIR"
    git clone --depth=1 "$REPO_URL" "$REPO_DIR"
  else
    git -C "$REPO_DIR" fetch --depth=1 origin main
    git -C "$REPO_DIR" checkout -B main FETCH_HEAD
  fi

  cd "$REPO_DIR"

  python3 -m money_radar.cli --db "$DB_PATH" fetch
  python3 -m money_radar.cli --db "$DB_PATH" refilter --prune
  python3 -m money_radar.cli --db "$DB_PATH" export-obsidian "$VAULT_DIR" --min-score 4 --limit 50

  echo "===== completed ====="
} >> "$LOG_DIR/run.log" 2>&1
