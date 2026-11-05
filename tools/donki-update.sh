#!/usr/bin/env bash
# Run by launchd (com.dashboards.donki) every 3 hours: save the NASA DONKI snapshot and push it.
# Like sync-dashboards.sh it carries no credential: git uses the macOS keychain.
# Replaces the TinyFish connector and the GitHub Actions job (1 Nov 2026).
set -euo pipefail

cd "$HOME/dashboards"
PY_BIN=/Users/baskersimac/.pyenv/versions/3.13.15/bin/python3  # launchd has a bare PATH

git pull -q --rebase --autostash origin main
"$PY_BIN" -I tools/fetch_donki.py
git add data/donki.json
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "DONKI snapshot $(date -u '+%Y-%m-%d %H:%M')" -- data/donki.json
git push -q origin main || { git pull -q --rebase --autostash origin main && git push -q origin main; }
echo "$(date '+%F %T') pushed $(git rev-parse --short HEAD)"
