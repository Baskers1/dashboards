#!/usr/bin/env python3
"""Fail if any tracked file holds a personal contact detail that sync.py would redact.

Usage: python3 tools/check_contacts.py            (scans every file in `git ls-files`)
       python3 tools/check_contacts.py FILE ...   (scans just those files)

Uses the same patterns, `keep` list and base64 rule as sync.redact(), so pages, tests,
tools and data are held to one rule. Fictional values are allowed: Ofcom's drama range
07700 900000-900999 and any address whose local part starts with "example".
Prints file:line for each hit and exits 1 if there are any.
"""
import os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync import BASE64, KEEP, PATTERNS, ROOT  # noqa: E402

FICTIONAL = re.compile(r"^07700 ?900 ?\d{3}$|^example[^@]*@", re.I)


def hits(text):
    """Yield (line_no, value) for each contact detail outside base64 spans."""
    blanked = BASE64.sub(lambda m: " " * len(m.group(0)), text)
    for rx, _ in PATTERNS:
        for m in rx.finditer(blanked):
            v = m.group(0)
            if v not in KEEP and not FICTIONAL.match(v):
                yield blanked.count("\n", 0, m.start()) + 1, v


def main(argv):
    files = argv[1:] or subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                                       check=True, text=True).stdout.split("\0")
    found = 0
    for f in filter(None, files):
        try:
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue  # binary or gone: nothing to read as text
        for line, v in hits(text):
            found += 1
            # masked so the CI log doesn't republish the value
            print(f"{f}:{line}: contact detail {v[:3]}…{v[-2:]} (add it to keep in tools/redact.json if it is public)")
    print(f"{found} contact detail(s) found" if found else "no contact details found")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
