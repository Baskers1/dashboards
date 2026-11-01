# dashboards

Static dashboards published via GitHub Pages. Data files under `data/` are
refreshed by scheduled jobs on the owner's iMac, committed, and pushed; the
Pages build then republishes the site.

## Debugging rule: no fix without an observed failure

Before proposing a remedy, name the failure you are explaining and quote the
output that shows it. If there is no such output, say "this has not failed
yet" and stop.

This rule exists because of a real detour on 2026-11-01. `bash
tools/iss-update.sh` failed with `No such file or directory`. The cause was a
stale checkout: the file was committed at `cbfde37` on `origin/main`, and the
Mac was still on `d524b4c`, so `git pull` was the whole fix. Instead the
session volunteered that launchd could not reach a locked macOS keychain,
walked the user through nine steps of SSH key setup, illustrated the theory
with an invented `Device not configured` error it had never observed, and then
asserted the keychain was "the actual bug". `~/bin/sync-dashboards.sh`
disproved it: that job pushes over HTTPS with `credential.helper=osxkeychain`
under launchd every hour and had five clean runs that same day.

Three habits to keep:

- Distinguish "this could fail because X" from "this failed because X". Never
  let the first borrow the second's grammar.
- Never write a sample error message in a way that reads as observed. If it is
  constructed, label it as constructed, or omit it.
- `No such file or directory` on a tracked file means check the checkout
  (`git log --oneline -1 HEAD` vs `origin/main`) before anything else. A fetch
  updates remote refs only; it never touches the working tree.

## Scheduled jobs on the iMac (`baskersimac@iMac`)

Both are launchd agents in `~/Library/LaunchAgents`, run only while the user is
logged in, and hardcode
`/Users/baskersimac/.pyenv/versions/3.13.15/bin/python3` because launchd
supplies a bare `PATH`. A pyenv upgrade silently breaks both.

| Job | Script | Interval | Repo | Logs |
|---|---|---|---|---|
| `com.dashboards.iss` | `tools/iss-update.sh` (in this repo) | 600s | `~/dashboards`, SSH remote | `/tmp/dashboards-iss.{log,err}` |
| hourly sync | `~/bin/sync-dashboards.sh` (not in this repo) | hourly at :10 | `~/dashboards-source`, HTTPS + keychain | `~/dashboards-source/.last-sync-status.txt` |

Credentials: the keychain works fine under launchd — do not "fix" it. This
repo's remote was switched to SSH on 2026-11-01, which is one less moving part
but was not a repair.

`~/dashboards-source` is a separate repository from this one. Something other
than `sync-dashboards.sh` also commits to it (commits titled `Hourly sync
<timestamp>`, whereas the script writes `sync: <timestamp>`) — most likely a
GitHub Action. Unverified.

## Known weak spot in `~/bin/sync-dashboards.sh`

`✓ sync complete` is appended to `.last-sync-status.txt` *before* the
commit/push block, and the push is `git push -q origin main 2>/dev/null` whose
failure path only echoes a warning and exits 0. So a clean heartbeat does not
prove the push landed. To check whether commits are stranded locally:

    cd ~/dashboards-source && git fetch -q origin main && git log --oneline origin/main..HEAD

Empty output means everything is pushed.

## Generated data files

`data/iss.json` is written at runtime by `tools/fetch_iss.py` and is not
committed on every branch. Its absence in a fresh clone is normal, not
breakage. `tools/fetch_iss.py` fails soft, keeping the previous file, so in a
sandbox with no DNS route it prints a warning and writes nothing — which then
makes the `git add data/iss.json` in `tools/iss-update.sh` fail under `set -e`.
