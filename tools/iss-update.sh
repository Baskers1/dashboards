#!/usr/bin/env bash
# Run by launchd (com.dashboards.iss) every 10 minutes: save the ISS position and push it.
# Like sync-dashboards.sh it carries no credential: git uses the macOS keychain.
# 10 minutes, not 5: GitHub Pages soft-limits builds to about 10 an hour.
set -euo pipefail

cd "$HOME/dashboards"
PY_BIN=/Users/baskersimac/.pyenv/versions/3.13.15/bin/python3  # launchd has a bare PATH

git pull -q --rebase origin main
"$PY_BIN" -I tools/fetch_iss.py
git add data/iss.json
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "ISS position $(date -u '+%Y-%m-%d %H:%M')"
git push -q origin main || { git pull -q --rebase origin main && git push -q origin main; }
echo "$(date '+%F %T') pushed $(git rev-parse --short HEAD)"
