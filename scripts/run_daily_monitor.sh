#!/usr/bin/env bash
# Daily monitor runner — invoked by cron / systemd.
# Scrapes smartvisaguide.com + immi.homeaffairs.gov.au, updates
# public/*.json, then deploys to Firebase Hosting.

set -euo pipefail

REPO_DIR="/home/moataz/work/migration-app/repo"
LOG_DIR="$REPO_DIR/.monitor-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date -u +%Y-%m-%d).log"

cd "$REPO_DIR"

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) Daily monitor run ==="
  python3 scripts/daily_monitor.py
  echo "--- Deploying to Firebase ---"
  firebase deploy --only hosting --project swift-shore-238707 --non-interactive
  echo "=== Done ==="
} >> "$LOG_FILE" 2>&1
