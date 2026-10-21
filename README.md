# dashboards
Series of Dashboards for several places that give information on that area.

Published at https://baskers1.github.io/dashboards/. Each page is a mirror of a Claude artifact.

## Publishing
`python3 tools/sync.py <download_dir>` copies downloaded artifacts into their folders and rebuilds the hub.
Every page goes through the same publishing rules on the way in:

- only browser files are published (HTML, images, CSS, JS, fonts); working data, research and scripts are not
- links between dashboards point at the GitHub Pages copies, not at claude.ai
- `tools/redact.json` removes personal contact details: exact-text replacements, plus patterns for UK mobiles and personal email providers (values in its `keep` list stay)
- `tools/harden.py` adds a Content-Security-Policy, a link guard and `lang` to each page

`python3 tools/sync.py --harden-only` re-applies the rules to what is already committed. `python3 tools/test_sync.py` runs the self-tests. CI runs both.

`python3 tools/check_contacts.py` scans every tracked file (not just pages) with the same patterns and fails on any hit, so a real number can't slip in through a test, script or data file. Use fictional values in tests: 07700 900xxx numbers and `example…@` addresses. CI runs it too.

## Who pushes to `main`
Three writers commit to `main`, so it moves without you:

| Writer | Commits look like | When |
|---|---|---|
| "Dashboards Git Sync" scheduled task (Claude) | `Mirror <date> <time>: <dashboards>` | about :51 past each hour, roughly 08:00–20:00 UK time |
| `.github/workflows/donki.yml` | `DONKI snapshot <date> <time>` | :17 past every third hour (UTC), only when the feed changed |
| You, and Claude sessions you start | merges and fixes | any time |

Before a history rewrite (for example `git filter-repo`):

1. Pause the "Dashboards Git Sync" scheduled task and disable the DONKI workflow.
2. Record each branch's SHA before rewriting, and push with `git push --force-with-lease=<branch>:<that SHA>`. A lease taken from a fresh fetch just before pushing protects nothing.
3. Re-enable both afterwards. The scheduled task clones fresh each run, so it picks up the new history by itself.
