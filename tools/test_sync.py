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
print("ok")
