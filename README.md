# dashboards
Series of Dashboards for several places that give information on that area.

Published at https://baskers1.github.io/dashboards/. Each page is a mirror of a Claude artifact.

## Publishing
`python3 tools/sync.py <download_dir>` copies downloaded artifacts into their folders and rebuilds the hub.
Every page goes through the same publishing rules on the way in:

- only browser files are published (HTML, images, CSS, JS, fonts); working data, research and scripts are not
- links between dashboards point at the GitHub Pages copies, not at claude.ai
- exact-text replacements in `tools/redact.json` remove personal contact details
- each page gets a Content-Security-Policy that blocks outside scripts, network calls and forms

`python3 tools/sync.py --reprocess` re-applies the rules to what is already committed. `python3 tools/test_sync.py` runs the self-tests. CI runs both.
