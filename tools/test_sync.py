"""Self-check for sync.py: python3 tools/test_sync.py"""
import importlib.util, os, shutil, tempfile

spec = importlib.util.spec_from_file_location("sync", os.path.join(os.path.dirname(__file__), "sync.py"))
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

# manifest sanity
known = s.M["dashboards"][0]
assert len({(d["area"], d["slug"]) for d in s.M["dashboards"]}) == len(s.M["dashboards"]), "duplicate folder"
ids = [d["id"] for d in s.M["dashboards"]] + [a for d in s.M["dashboards"] for a in d.get("aliases", [])]
assert len(set(ids)) == len(ids), "duplicate id or alias"
for d in s.M["dashboards"]:
    s.folder(d)  # raises on unsafe names

# links: short ids, uuid aliases, unknown links untouched
out = s.rewrite_links(f'<a href="https://claude.ai/artifact/{known["id"]}">x</a> https://claude.ai/artifact/ZZZZZZZZZZZZZZZZZZZZZZ')
assert s.BASE_URL + known["area"] + "/" + known["slug"] + "/" in out, out
assert "https://claude.ai/artifact/ZZZZZZZZZZZZZZZZZZZZZZ" in out, "unknown links must be left alone"
aliased = next(d for d in s.M["dashboards"] if d.get("aliases"))
out = s.rewrite_links(f'href="https://claude.ai/code/artifact/{aliased["aliases"][0]}"')
assert out == f'href="{s.BASE_URL}{aliased["area"]}/{aliased["slug"]}/"', out
unknown_uuid = "https://claude.ai/code/artifact/00000000-0000-0000-0000-000000000000"
assert s.rewrite_links(unknown_uuid) == unknown_uuid

# folder names
for bad in ("../x", "a/b", "", "X"):
    try:
        s.folder({"area": bad, "slug": "weather"}); raise AssertionError(f"accepted {bad!r}")
    except ValueError:
        pass

# redaction
r = s.REDACT[0]
assert r["find"] not in s.redact("x " + r["find"] + " y") and r["replace"] in s.redact(r["find"])

# CSP: added once, right after <head>, idempotent
page = '<!doctype html><html><head><meta charset="utf-8"><title>t</title></head><body></body></html>'
p1 = s.add_csp(page)
assert p1.count("Content-Security-Policy") == 1 and p1.index("Content-Security-Policy") < p1.index("<title>")
assert s.add_csp(p1) == p1
assert s.add_csp('<HEAD lang="en">x').startswith('<HEAD lang="en">\n<meta http-equiv')

# publish_tree drops working files, keeps page assets, processes HTML, removes empty dirs
tmp = tempfile.mkdtemp()
try:
    for rel, body in {"index.html": "<head></head>" + r["find"], "thumbs/a.jpg": "x", "hero.JPG": "x",
                      "data/data.json": "{}", "data/build.py.txt": "x", "data/notes.md": "x",
                      "design/shell.txt": "x"}.items():
        os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
        open(os.path.join(tmp, rel), "w").write(body)
    removed = s.publish_tree(tmp)
    assert sorted(removed) == sorted(["data/data.json", "data/build.py.txt", "data/notes.md", "design/shell.txt"]), removed
    assert not os.path.exists(os.path.join(tmp, "data")) and not os.path.exists(os.path.join(tmp, "design"))
    assert os.path.exists(os.path.join(tmp, "thumbs/a.jpg")) and os.path.exists(os.path.join(tmp, "hero.JPG"))
    html = open(os.path.join(tmp, "index.html")).read()
    assert "Content-Security-Policy" in html and r["find"] not in html
finally:
    shutil.rmtree(tmp)

# sync_one: a rejected download leaves the existing folder alone
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

# sync_one success: new copy replaces old one (stale files dropped), rules applied
root, src = tempfile.mkdtemp(), tempfile.mkdtemp()
real_root, s.ROOT = s.ROOT, root
try:
    dst = s.folder(known); os.makedirs(dst)
    open(os.path.join(dst, "stale.html"), "w").write("old")
    os.makedirs(os.path.join(src, known["id"], "data"))
    open(os.path.join(src, known["id"], "index.html"), "w").write("<head><title>t</title></head>" + "x" * 10_000)
    open(os.path.join(src, known["id"], "data", "d.json"), "w").write("{}")
    assert s.sync_one(src, known) is None
    assert os.listdir(dst) == ["index.html"], os.listdir(dst)
    assert "Content-Security-Policy" in open(os.path.join(dst, "index.html")).read()
    assert [n for n in os.listdir(os.path.dirname(dst)) if n.startswith(".sync-")] == [], "temp dir left behind"
finally:
    s.ROOT = real_root; shutil.rmtree(root); shutil.rmtree(src)

print("ok")
