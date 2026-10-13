"""Put a freshly built dashboard's data into a fixed page design.

Usage: python3 retemplate.py <shell.html> <built.html> [out.html]

The `const DATA={...}` line in <shell.html> is replaced with the one from
<built.html>; everything else in the shell (layout, photos, styling) is kept.
Without out.html, <built.html> is overwritten.
"""
import re
import sys

DATA_LINE = re.compile(r"^const DATA=\{.*\};?[ \t]*$", re.M)


def data_line(html, name):
    m = DATA_LINE.search(html)
    if not m:
        sys.exit(f"no `const DATA=` line in {name}")
    return m.group(0)


def main(shell, built, out=None):
    s = open(shell, encoding="utf-8").read()
    data = data_line(open(built, encoding="utf-8").read(), built)
    data_line(s, shell)
    s = DATA_LINE.sub(lambda _: data, s, count=1)
    open(out or built, "w", encoding="utf-8").write(s)
    print("retemplated", out or built, len(s))


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    main(*sys.argv[1:])
