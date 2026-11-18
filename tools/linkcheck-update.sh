#!/usr/bin/env bash
# Run by launchd (com.dashboards.linkcheck) once a week: check every listing link on the What's On,
# Menu Watch, Community Watch and Consultation Watch pages, update data/link-ledger.json, re-apply
# tools/sync.py so a link dead on two runs is published without its href, and push.
# Rules: LINKS.md in dashboards-source. Report: ~/.cache/linkcheck/report-<date>.md.
# Like iss-update.sh it carries no credential: git uses the macOS keychain.
# Takes about 20 minutes (10 for our checker, 8 for the lychee second opinion).
set -euo pipefail

cd "$HOME/dashboards"
PY_BIN=/Users/baskersimac/.pyenv/versions/3.13.15/bin/python3  # launchd has a bare PATH
export PATH="/opt/homebrew/bin:/usr/bin:/bin:$PATH"            # lychee, dig, curl

git pull -q --rebase --autostash origin main

# Refuse to sweep someone else's half-finished page edit into this commit.
if [ -n "$(git diff --name-only -- '*.html')" ]; then
  echo "tracked pages already have uncommitted edits; not running" >&2
  git diff --name-only -- '*.html' >&2
  exit 1
fi

"$PY_BIN" -I tools/check_links.py
"$PY_BIN" -I tools/sync.py --harden-only >/dev/null

changed=$(git diff --name-only -- '*.html')
git add data/link-ledger.json
[ -n "$changed" ] && echo "$changed" | xargs git add --
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "Link check $(date -u '+%Y-%m-%d')"
git push -q origin main || { git pull -q --rebase --autostash origin main && git push -q origin main; }
echo "$(date '+%F %T') pushed $(git rev-parse --short HEAD); pages changed: $(echo "$changed" | grep -c . || true)"
