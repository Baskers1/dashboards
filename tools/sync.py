#!/usr/bin/env python3
"""Copy downloaded Claude artifact files into the GitHub Pages folders and rebuild the hub page.

Usage: python3 tools/sync.py <download_dir> [<id> ...]
       python3 tools/sync.py --harden-only      (re-apply harden.py to the pages already here)
  <download_dir>/<artifact id>/index.html (+ any other published files) must already exist,
  saved by the Artifact tool. Files are copied as they are, except that links to other
  dashboards' claude.ai artifact pages are pointed at their GitHub Pages copies and every
  HTML page goes through harden.py (Content-Security-Policy, link guard, lang, unwrapping).
  Only browser files are published (see PUBLIC_EXT): working data, research, playbooks and
  scripts stay out of the public site. Exact-text replacements in redact.json remove personal
  details. Links use both claude.ai forms: short ids and code/artifact/<uuid> ("aliases").
  With ids given, only those dashboards are synced; the hub is always rebuilt.
  Entries whose id starts with "local:" are published by their own task (e.g. sky pages) and are only listed on the hub.
Exits non-zero (and leaves that dashboard's live folder untouched) if a downloaded page looks wrong.
"""
import html, json, os, re, shutil, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harden import harden  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "https://baskers1.github.io/dashboards/"
M = json.load(open(os.path.join(ROOT, "tools", "dashboards.json"), encoding="utf-8"))
BY_ID = {d["id"]: d for d in M["dashboards"]}
LOOKUP = {**BY_ID, **{a: d for d in M["dashboards"] for a in d.get("aliases", [])}}
LINK = re.compile(r"https://claude\.ai/(?:code/)?artifact/"
                  r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9]{22})")
_R = json.load(open(os.path.join(ROOT, "tools", "redact.json"), encoding="utf-8"))
REDACT = _R["replacements"]
PATTERNS = [(re.compile(r["regex"]), r["replace"]) for r in _R.get("patterns", [])]
KEEP = set(_R.get("keep", []))
BASE64 = re.compile(r"data:[a-z0-9.+/-]+;base64,[A-Za-z0-9+/=]+", re.I)
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PUBLIC_EXT = {".html", ".htm", ".css", ".js", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
              ".svg", ".ico", ".woff", ".woff2"}


def folder(d):
    for part in (d["area"], d["slug"]):
        if not SAFE_NAME.match(part):  # these names get rmtree'd; never let them escape ROOT
            raise ValueError(f"unsafe folder name in dashboards.json: {part!r}")
    return os.path.join(ROOT, d["area"], d["slug"])


def rewrite_links(text):
    def sub(m):
        d = LOOKUP.get(m.group(1))
        return f"{BASE_URL}{d['area']}/{d['slug']}/" if d else m.group(0)
    return LINK.sub(sub, text)


def redact(text):
    for r in REDACT:
        text = text.replace(r["find"], r["replace"])
    if not PATTERNS:
        return text
    def scrub(part):
        for rx, rep in PATTERNS:
            part = rx.sub(lambda m: m.group(0) if m.group(0) in KEEP else rep, part)
        return part
    # never touch embedded images: a digit run inside base64 could look like a phone number
    out, last = [], 0
    for m in BASE64.finditer(text):
        out += [scrub(text[last:m.start()]), m.group(0)]
        last = m.end()
    return "".join(out) + scrub(text[last:])


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
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    # Build the new copy beside the old one, then swap, so a failure never leaves a missing page.
    tmp = tempfile.mkdtemp(prefix=".sync-", dir=os.path.dirname(dst))
    try:
        staged = os.path.join(tmp, "new")
        shutil.copytree(src, staged)
        fix_pages(staged)
        if os.path.isdir(dst):
            os.rename(dst, os.path.join(tmp, "old"))  # exact mirror: drop files the artifact no longer has
        os.rename(staged, dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


def fix_pages(dst):
    """Drop non-browser files, then fix links, redact and harden every HTML page under dst.
    Returns the paths removed, relative to dst."""
    removed = []
    for dirpath, _, names in os.walk(dst, topdown=False):
        for n in names:
            p = os.path.join(dirpath, n)
            ext = os.path.splitext(n)[1].lower()
            if ext not in PUBLIC_EXT:
                os.remove(p)
                removed.append(os.path.relpath(p, dst))
            elif ext in (".html", ".htm"):
                with open(p, encoding="utf-8", newline="") as f:
                    t = f.read()
                t2 = harden(redact(rewrite_links(t)))
                if t2 != t:
                    with open(p, "w", encoding="utf-8", newline="") as f:
                        f.write(t2)
        if dirpath != dst and not os.listdir(dirpath):
            os.rmdir(dirpath)
    return removed


def build_hub():
    rows = []
    for key, label in M["areas"].items():
        listed = [d for d in M["dashboards"] if d["area"] == key]
        items = [d for d in listed if os.path.exists(os.path.join(folder(d), "index.html"))]
        for d in listed:
            if d not in items:
                print(f"WARNING not on the hub (no page published yet): {key}/{d['slug']}")
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
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(harden(page))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--harden-only":
        done = [d for d in M["dashboards"] if os.path.isdir(folder(d))]
        for d in done:
            for r in fix_pages(folder(d)):
                print("removed", os.path.join(d["area"], d["slug"], r))
        build_hub()
        print(f"hardened {len(done)} dashboards and the hub")
        return 0
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
