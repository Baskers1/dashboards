"""Self-check for sync.py: python3 tools/test_sync.py"""
import importlib.util, os

spec = importlib.util.spec_from_file_location("sync", os.path.join(os.path.dirname(__file__), "sync.py"))
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

known = s.M["dashboards"][0]
out = s.rewrite_links(f'<a href="https://claude.ai/artifact/{known["id"]}">x</a> https://claude.ai/artifact/ZZZZZZZZZZZZZZZZZZZZZZ')
assert s.BASE_URL + known["area"] + "/" + known["slug"] + "/" in out, out
assert "https://claude.ai/artifact/ZZZZZZZZZZZZZZZZZZZZZZ" in out, "unknown links must be left alone"
assert len({(d["area"], d["slug"]) for d in s.M["dashboards"]}) == len(s.M["dashboards"]), "duplicate folder"
assert len({d["id"] for d in s.M["dashboards"]}) == len(s.M["dashboards"]), "duplicate id"

# harden.py
import base64, hashlib, re
from harden import harden, unwrap, GUARD_ID

def sha(t):
    return "'sha256-" + base64.b64encode(hashlib.sha256(t.encode()).digest()).decode() + "'"

wrapper = '<!doctype html><html><head><meta charset=utf8><style>x{}</style></head><body>\n'
page = wrapper + '<title>T</title><script>var A=1;</script><p>hi</p></body></html>'
out = harden(page)
policy = re.search(r'Content-Security-Policy" content="([^"]+)"', out).group(1)
assert sha("var A=1;") in policy, "page's own script must be allowed by hash"
assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0], "no unsafe-inline for scripts"
assert sha("this.remove()") in policy and "'unsafe-hashes'" in policy, "Menu Watch thumbnail handler allowed"
assert "object-src 'none'" in policy and "base-uri 'none'" in policy
assert out.index("Content-Security-Policy") < out.index("<script"), "CSP must come before every script"
assert out.index("<meta charset") < out.index("Content-Security-Policy"), "charset stays first"
assert '<html lang="en-GB">' in out, out[:200]
assert f'<script id="{GUARD_ID}">' in out
assert harden(out) == out, "harden must be idempotent"
assert '<html lang="cy">' in harden(wrapper.replace("<html>", '<html lang="cy">') + "</body></html>"), "keep an existing lang"

# A link smuggled in by scraped data is not trusted: its handler isn't hashed into the policy.
evil = page.replace("<p>hi</p>", '<a href="x" onmouseover="steal()">x</a>')
assert sha("steal()") not in harden(evil)

# Double-wrapped page: one doctype, head content moved into head, body attributes kept.
double = (wrapper + '<!doctype html>\n<html lang="en">\n<head><style>y{}</style>'
          '<script>var B=2;</script></head>\n<body class="big">\n<p>inner</p>\n</body></html>\n\n</body></html>')
u = unwrap(double)
assert len(re.findall(r"(?i)<!doctype", u)) == 1 and len(re.findall(r"(?i)<html", u)) == 1, u
assert len(re.findall(r"(?i)<body", u)) == 1 and len(re.findall(r"(?i)</body>", u)) == 1, u
assert u.index("y{}") < u.index("</head>") and u.index("var B=2;") < u.index("</head>")
assert '<body class="big">' in u and '<html lang="en">' in u and "<p>inner</p>" in u
assert sha("var B=2;") in harden(double)
assert unwrap(page) == page, "single documents are left alone"

# --- publishing rules (aliases, folder names, redaction, file filter, safe swap) ---
import shutil, tempfile
ids = [d["id"] for d in s.M["dashboards"]] + [a for d in s.M["dashboards"] for a in d.get("aliases", [])]
assert len(set(ids)) == len(ids), "duplicate id or alias"
for d in s.M["dashboards"]:
    s.folder(d)  # raises on unsafe names
for bad in ("../x", "a/b", "", "X"):
    try:
        s.folder({"area": bad, "slug": "weather"}); raise AssertionError(f"accepted {bad!r}")
    except ValueError:
        pass

aliased = next(d for d in s.M["dashboards"] if d.get("aliases"))
out = s.rewrite_links(f'href="https://claude.ai/code/artifact/{aliased["aliases"][0]}"')
assert out == f'href="{s.BASE_URL}{aliased["area"]}/{aliased["slug"]}/"', out
unknown_uuid = "https://claude.ai/code/artifact/00000000-0000-0000-0000-000000000000"
assert s.rewrite_links(unknown_uuid) == unknown_uuid

r = s.REDACT[0]
assert r["find"] not in s.redact("x " + r["find"] + " y") and r["replace"] in s.redact(r["find"])

tmp = tempfile.mkdtemp()
try:
    for rel, body in {"index.html": "<html><head><title>t</title></head><body>" + r["find"] + "</body></html>",
                      "thumbs/a.jpg": "x", "hero.JPG": "x", "data/data.json": "{}",
                      "data/build.py.txt": "x", "data/notes.md": "x", "design/shell.txt": "x"}.items():
        os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
        open(os.path.join(tmp, rel), "w").write(body)
    removed = s.fix_pages(tmp)
    assert sorted(removed) == sorted(["data/data.json", "data/build.py.txt", "data/notes.md", "design/shell.txt"]), removed
    assert not os.path.exists(os.path.join(tmp, "data")) and not os.path.exists(os.path.join(tmp, "design"))
    assert os.path.exists(os.path.join(tmp, "thumbs/a.jpg")) and os.path.exists(os.path.join(tmp, "hero.JPG"))
    page_out = open(os.path.join(tmp, "index.html")).read()
    assert "Content-Security-Policy" in page_out and r["find"] not in page_out
finally:
    shutil.rmtree(tmp)

# sync_one: a rejected download leaves the live folder alone
src = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(src, known["id"]))
    open(os.path.join(src, known["id"], "index.html"), "w").write("<title>tiny</title>")
    dst = s.folder(known)
    before = sorted(os.listdir(dst)) if os.path.isdir(dst) else None
    assert "too small" in s.sync_one(src, known)
    assert (sorted(os.listdir(dst)) if os.path.isdir(dst) else None) == before
finally:
    shutil.rmtree(src)

# sync_one success: new copy replaces old (stale files dropped), rules applied, no temp left
root, src = tempfile.mkdtemp(), tempfile.mkdtemp()
real_root, s.ROOT = s.ROOT, root
try:
    dst = s.folder(known); os.makedirs(dst)
    open(os.path.join(dst, "stale.html"), "w").write("old")
    os.makedirs(os.path.join(src, known["id"], "data"))
    open(os.path.join(src, known["id"], "index.html"), "w").write("<html><head><title>t</title></head><body>" + "x" * 10_000 + "</body></html>")
    open(os.path.join(src, known["id"], "data", "d.json"), "w").write("{}")
    assert s.sync_one(src, known) is None
    assert os.listdir(dst) == ["index.html"], os.listdir(dst)
    assert "Content-Security-Policy" in open(os.path.join(dst, "index.html")).read()
    assert [n for n in os.listdir(os.path.dirname(dst)) if n.startswith(".sync-")] == [], "temp dir left behind"
finally:
    s.ROOT = real_root; shutil.rmtree(root); shutil.rmtree(src)
print("ok")
