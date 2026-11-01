"""Refuse to commit a published page that tools/sync.py would still change.

The sky builders in dashboards-source emit unhardened pages on purpose; running
`tools/sync.py --harden-only` in this repo afterwards is what adds the
Content-Security-Policy and the dash-guard script. That step lived only inside the two
sky refresh tasks, so an ad-hoc publish could stage a page without it and nothing
noticed until CI went red on main -- where a failed run on a push nobody reads is
invisible. This checks the STAGED text, which is what the commit would actually publish,
not the working tree.

  python3 tools/check_hardened.py <path>...   paths relative to the repo root
  python3 tools/check_hardened.py            paths as NUL-separated stdin (git -z)

Exits 1 and names every page that is not already in its published form.
"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync import page_text  # noqa: E402


def staged(path):
    """The text this commit would publish, or None if the staged blob is not UTF-8."""
    r = subprocess.run(["git", "show", f":{path}"], capture_output=True)
    if r.returncode != 0:
        return None
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def reasons(text):
    """Why this page is not publishable as staged; empty when it is already correct."""
    if page_text(text) == text:
        return []
    why = []
    if "Content-Security-Policy" not in text:
        why.append("no Content-Security-Policy")
    if 'id="dash-guard"' not in text:
        why.append("no dash-guard script")
    # Hardening is not the only thing fix_pages does, so say so rather than mislead.
    return why or ["sync.py would still rewrite it (links, redaction or hardening)"]


def main(paths):
    bad = []
    for p in paths:
        t = staged(p)
        why = ["could not read the staged blob as UTF-8 text"] if t is None else reasons(t)
        if why:
            bad.append((p, why))
    for p, why in bad:
        print(f"{p}: {', '.join(why)}", file=sys.stderr)
    if bad:
        print("\nEvery published page must carry the CSP and link guard. Fix with:\n"
              f"  python3 tools/sync.py --harden-only && git add {' '.join(p for p, _ in bad)}\n"
              "A page outside tools/dashboards.json is never hardened by that command: add it "
              "there first, or this will not clear.", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        argv = [p for p in sys.stdin.buffer.read().decode("utf-8").split("\0") if p]
    sys.exit(main(argv))
