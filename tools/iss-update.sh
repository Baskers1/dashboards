#!/usr/bin/env bash
# Run by launchd (com.dashboards.iss) every 10 minutes: save the ISS position (and, every half hour, Kp and
# AuroraWatch for the Space Weather page) and push it.
# Like sync-dashboards.sh it carries no credential: git uses the macOS keychain.
# 10 minutes, not 5: GitHub Pages soft-limits builds to about 10 an hour.
set -euo pipefail

cd "$HOME/dashboards"
PY_BIN=/Users/baskersimac/.pyenv/versions/3.13.15/bin/python3  # launchd has a bare PATH

git pull -q --rebase --autostash origin main
"$PY_BIN" -I tools/fetch_iss.py
# Kp and AuroraWatch for the Space Weather page; fetches at most every 30 minutes, and a failure must not stop the ISS push
"$PY_BIN" -I tools/fetch_kp.py || echo "fetch_kp failed; keeping the previous data/kp.json" >&2
git add data/iss.json data/kp.json
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "ISS position $(date -u '+%Y-%m-%d %H:%M')"
git push -q origin main || { git pull -q --rebase --autostash origin main && git push -q origin main; }
echo "$(date '+%F %T') pushed $(git rev-parse --short HEAD)"
