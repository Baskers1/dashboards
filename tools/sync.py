#!/usr/bin/env python3
"""Copy downloaded Claude artifact files into the GitHub Pages folders and rebuild the hub page.

Usage: python3 tools/sync.py <download_dir> [<id> ...]
  <download_dir>/<artifact id>/index.html (+ any other published files) must already exist,
  saved by the Artifact tool. Files are copied byte for byte; the only change made is that
  links to other dashboards' claude.ai artifact pages are pointed at their GitHub Pages copies.
  With ids given, only those dashboards are synced; the hub is always rebuilt.
  Entries whose id starts with "local:" are published by their own task (e.g. sky pages) and are only listed on the hub.
Exits non-zero (and changes nothing for that dashboard) if a downloaded page looks wrong.
"""
import html, json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "https://baskers1.github.io/dashboards/"
M = json.load(open(os.path.join(ROOT, "tools", "dashboards.json"), encoding="utf-8"))
BY_ID = {d["id"]: d for d in M["dashboards"]}
LINK = re.compile(r"https://claude\.ai/(?:code/)?artifact/([A-Za-z0-9]{22})")


def folder(d):
    return os.path.join(ROOT, d["area"], d["slug"])


def rewrite_links(text):
    return LINK.sub(lambda m: BASE_URL + BY_ID[m.group(1)]["area"] + "/" + BY_ID[m.group(1)]["slug"] + "/"
                    if m.group(1) in BY_ID else m.group(0), text)


def check(page):
    with open(page, "rb") as f:
        raw = f.read()
    if len(raw) < 10_000:
        return f"too small ({len(raw)} bytes)"
    if b"<title>" not in raw:
        return "no <title>"
    return None


def sync_one(src_root, d):
    src = os.path.join(src_root, d["id"])
    page = os.path.join(src, "index.html")
    if not os.path.exists(page):
        return f"{d['id']}: missing {page}"
    bad = check(page)
    if bad:
        return f"{d['id']}: {bad}"
    dst = folder(d)
    if os.path.isdir(dst):
        shutil.rmtree(dst)  # exact mirror: drop files the artifact no longer has
    shutil.copytree(src, dst)
    for dirpath, _, names in os.walk(dst):
        for n in names:
            if n.endswith(".html"):
                p = os.path.join(dirpath, n)
                t = open(p, encoding="utf-8").read()
                t2 = rewrite_links(t)
                if t2 != t:
                    open(p, "w", encoding="utf-8").write(t2)
    return None


def build_hub():
    rows = []
    for key, label in M["areas"].items():
        items = [d for d in M["dashboards"] if d["area"] == key and os.path.exists(os.path.join(folder(d), "index.html"))]
        if not items:
            continue
        links = "".join(f'<li><a href="{key}/{d["slug"]}/">{html.escape(d["name"])}</a></li>' for d in items)
        rows.append(f'<section><h2>{html.escape(label)}</h2><ul>{links}</ul></section>')
    page = f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Baskers Dashboards</title>
<style>
:root{{--bg:#fffdf7;--fg:#1a1a1a;--muted:#555;--card:#fff;--line:#ddd6c8;--accent:#0b5394}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#f1f1f1;--muted:#b5b5b5;--card:#20242a;--line:#343a42;--accent:#8ab8ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:19px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:46rem;margin:0 auto;padding:32px 16px 64px}}h1{{font-size:30px;margin:0 0 4px}}
p.lede{{color:var(--muted);margin:0 0 24px}}h2{{font-size:21px;margin:28px 0 10px}}
ul{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(14rem,1fr));gap:10px}}
a{{display:block;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--card);
color:var(--accent);font-weight:600;text-decoration:none}}a:hover,a:focus{{border-color:var(--accent)}}
</style></head><body><main><h1>Baskers Dashboards</h1>
<p class="lede">Weather, what's on, menus, local consultations and NHS waits for the places we care about. Each page updates itself on a schedule.</p>
{''.join(rows)}</main></body></html>
"""
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(page)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src_root, ids = argv[1], argv[2:] or [i for i in BY_ID if not i.startswith("local:")]
    errors = [e for e in (sync_one(src_root, BY_ID[i]) for i in ids if i in BY_ID) if e]
    unknown = [i for i in ids if i not in BY_ID]
    build_hub()
    for e in errors + [f"{i}: not in tools/dashboards.json" for i in unknown]:
        print("SKIPPED", e)
    print(f"synced {len(ids) - len(errors) - len(unknown)} of {len(ids)}")
    return 1 if errors or unknown else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
