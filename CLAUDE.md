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

## Why sky pages sometimes lose their hardening

Every published page must carry the `Content-Security-Policy` meta and the
`dash-guard` inline script that `tools/harden.py` injects. The builder in
`dashboards-source` does **not** emit them: `sky/work/<town>/dashboard.html` is
unhardened, and `tools/sync.py --harden-only`, run in the publishing repo after
the copy, is what adds them. Copy a built page in and skip that step and the
page is published without its CSP or its DOM sanitiser.

The two scheduled tasks do this correctly. `Sky dashboards morning refresh
(Mac)` (`trig_01NTcr39czUs5KcrChm42w6V`, 07:52) and `Sky dashboards evening
refresh (Mac)` (`trig_01575SzYtwaVj7PWhwE2t5bM`, 16:52) both run
`--harden-only` after the six `cp` commands, both require it to exit 0, both
require `git diff --quiet` afterwards so hardening touched only the staged
pages, and both make a missing `dash-guard` or CSP a per-town FAILED in their
step 4 verification. Their prompts say why: "without it CI on main goes red
(this happened 21 October 2026)." Do not "fix" these two tasks; they are the
pattern to copy.

The 2026-11-01 drift came from outside the schedule. `d524b4c` (22:26) stripped
the hardening from four pages, and the evidence says no scheduled run made it:

- the morning task's `last_fired_at` was 07:52:29Z, the evening task's
  16:53:03Z; neither fired near 22:26
- it touched four pages (ammanford, carnoustie, dundee, ramsgate), not the six
  both tasks publish — exactly the four that existed before plymouth and
  rickmansworth were added that morning at 11:24 and 11:28
- it was a net deletion (49 insertions, 101 deletions), i.e. it replaced
  hardened pages with unhardened builds rather than failing to add anything
- both task prompts were edited at 22:45, nineteen minutes *after* it

So it was an ad-hoc publish that ran part of the task's step 3 by hand, copying
four stale `work/<town>/dashboard.html` files left over from the morning build
and omitting the `--harden-only` line.

That was possible because the harden step existed only inside those two task
prompts. Nothing in the repository enforced it, so any ad-hoc publish bypassed it
silently, and `sync-rules` only caught the result once it was already on `main` —
where a red run on a push nobody reads is invisible.

## The pre-commit guard

`tools/githooks/pre-commit` now refuses any commit that stages a published page
`tools/sync.py` would still change. It is tracked, so it travels with the repo,
but git never enables a hook automatically — **install it once per clone**:

    git config core.hooksPath tools/githooks

It checks the *staged* text, not the working tree, since that is what a commit
publishes. `tools/check_hardened.py` does the work by applying
`sync.page_text()` — the same `harden(redact(rewrite_links(t)))` pipeline
`fix_pages` writes with — and refusing anything it would alter. That shared
function is deliberate: a hook that grepped for `dash-guard` would drift from
what `sync.py` actually requires, and would wave through a page that is hardened
but still carries an unrewritten link or an unredacted contact detail.

Two properties worth preserving if it is ever edited:

- It looks for python only once HTML is actually staged, so the launchd jobs that
  commit data files alone (`data/iss.json`, `data/donki.json`) never reach that
  code and cannot be broken by it.
- It fails closed. No python, or a `git diff` that errors, refuses the commit
  rather than passing; `git commit --no-verify` is the deliberate bypass.

`python3 tools/test_check_hardened.py` covers it and runs in CI.

`tools/githooks/pre-push` lives beside it and guards `main` against force-pushes
and deletions (installed 2026-10-21, originally in `.git/hooks`). Both hooks are
served from the one directory because **`core.hooksPath` replaces `.git/hooks`
wholesale rather than adding to it**: setting it silently disabled this pre-push
hook until it was moved here, since `tools/githooks/` held only `pre-commit`.
Verified, not assumed — with `core.hooksPath` set, a `.git/hooks/pre-push` that
exits 1 does not run and the push succeeds. So any hook this repo relies on must
live in `tools/githooks/`, and before telling anyone to set `core.hooksPath`,
check `ls .git/hooks/ | grep -v '\.sample$'` for hooks that would be switched
off. Fast-forward pushes, including the ISS job's, are unaffected;
`git push --no-verify` is the deliberate bypass.

## A page absent from dashboards.json is never hardened

`sync.py --harden-only` iterates `tools/dashboards.json`, so a page published
without an entry there is outside the harden regime *and* invisible to
`sync-rules`, which only compares what that command would write. `sky/iss/`
was added in `cbfde37` and served live with an inline script, no CSP and no
dash-guard for exactly that reason — the same class of bug as the drift above,
with no red CI to betray it.

It now has a `local:sky-iss` entry, mirroring `space-weather` (a sky dashboard
with no town, refreshed by its own job), which brings it under both the harden
command and CI, and lists it on the hub. When adding a published page, add its
`dashboards.json` entry in the same commit, or nothing will ever check it.

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
