#!/usr/bin/env bash
# Run by launchd (com.dashboards.nptsocial) once a day: refresh the Neath Port Talbot food-and-drink
# social pull and push it.
# Unlike iss-update.sh and donki-update.sh this one DOES need a credential, because ScrapeCreators is
# a paid API. The key is read from a file outside the repo, never from this script and never from the
# plist, so it cannot be committed by accident:
#
#     mkdir -p ~/.config/npt-social
#     printf 'export SCRAPECREATORS_API_KEY=%s\n' 'YOUR-KEY' > ~/.config/npt-social/env
#     chmod 600 ~/.config/npt-social/env
#
# git itself carries no credential here: it uses the macOS keychain, as the other jobs do.
# A cold run costs about 700 API credits. fetch_npt_social.py throttles itself to 20 hours, so a
# missed day costs nothing and a double-fire does nothing.
set -euo pipefail

cd "$HOME/dashboards"
PY_BIN=/Users/baskersimac/.pyenv/versions/3.13.15/bin/python3  # launchd has a bare PATH

ENV_FILE="$HOME/.config/npt-social/env"
if [ ! -r "$ENV_FILE" ]; then
  echo "$ENV_FILE is missing or unreadable; see the header of this script" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$ENV_FILE"
: "${SCRAPECREATORS_API_KEY:?SCRAPECREATORS_API_KEY is not set in $ENV_FILE}"

git pull -q --rebase --autostash origin main
# The cache holds the raw corpus and stays outside the repo. Do not point this inside ~/dashboards.
export NPT_SOCIAL_CACHE="${NPT_SOCIAL_CACHE:-$HOME/.cache/npt-social}"
"$PY_BIN" -I tools/fetch_npt_social.py
git add data/npt-food-social.json
if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
git commit -q -m "NPT food & drink social pull $(date -u '+%Y-%m-%d %H:%M')"
git push -q origin main || { git pull -q --rebase --autostash origin main && git push -q origin main; }
echo "$(date '+%F %T') pushed $(git rev-parse --short HEAD)"
