#!/bin/zsh
set -eu

APP_DIR="/Users/lizhu/Automations/money-radar"
REPO_DIR="$APP_DIR/repo"
DB_PATH="$APP_DIR/data/money_radar.sqlite3"
LOG_DIR="/private/tmp/com.lizhu.money-radar"
VAULT_DIR="/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work副本/Reddit Money Radar"
REPO_URL="https://github.com/sourit2001/money-radar.git"
LOCK_DIR="$APP_DIR/run.lock"
REPORT_DATE="$(TZ=Asia/Shanghai date '+%Y-%m-%d')"
REPORT_FILENAME="Money Radar ${REPORT_DATE}.md"

mkdir -p "$APP_DIR" "$APP_DIR/data" "$LOG_DIR" "$VAULT_DIR"

PERMISSION_PROBE="$VAULT_DIR/.money-radar-write-test"
if ! : > "$PERMISSION_PROBE"; then
  echo "===== $(date -u '+%Y-%m-%d %H:%M:%S UTC') cannot write to iCloud destination: $VAULT_DIR =====" >> "$LOG_DIR/run.log"
  exit 1
fi
rm -f "$PERMISSION_PROBE"

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

  PYTHON="$APP_DIR/.venv/bin/python3"
  if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
  fi

  "$PYTHON" -m money_radar.cli --db "$DB_PATH" fetch
  "$PYTHON" -m money_radar.cli --db "$DB_PATH" refilter --prune
  "$PYTHON" -m money_radar.cli --db "$DB_PATH" export-obsidian "$VAULT_DIR" --min-score 4 --limit 50 --filename "$REPORT_FILENAME" --bilingual

  echo "===== completed ====="
} >> "$LOG_DIR/run.log" 2>&1
