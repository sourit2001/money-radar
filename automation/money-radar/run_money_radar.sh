#!/bin/zsh
set -eu

APP_DIR="/Users/lizhu/Automations/money-radar"
REPO_DIR="$APP_DIR/repo"
DB_PATH="$APP_DIR/data/money_radar.sqlite3"
LOG_DIR="/private/tmp/com.lizhu.money-radar"
VAULT_DIR="$APP_DIR/obsidian"
REPO_URL="https://github.com/sourit2001/money-radar.git"
LOCK_DIR="$APP_DIR/run.lock"

mkdir -p "$APP_DIR" "$APP_DIR/data" "$LOG_DIR" "$VAULT_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "===== $(date -u '+%Y-%m-%d %H:%M:%S UTC') previous run still active; skipping =====" >> "$LOG_DIR/run.log"
  exit 0
fi

trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

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
