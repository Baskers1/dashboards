"""Self-check for fetch_donki.py (no network): python3 tools/test_fetch_donki.py"""
import datetime as dt, importlib.util, os

spec = importlib.util.spec_from_file_location("f", os.path.join(os.path.dirname(__file__), "fetch_donki.py"))
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
NOW = dt.datetime(2026, 10, 13, 20, 0, tzinfo=dt.timezone.utc)

def fake(bad=()):
    def fetch(url):
        kind = url.split("/get/")[1].split("?")[0]
        if kind in bad: raise OSError("boom " + kind)
        return "" if kind == "MPC" else ('{"not":"a list"}' if kind == "SEP" else '[{"x":1}]')
    return fetch

s = f.build(fake(), NOW)
assert s["window"] == {"start": "2026-09-13", "start11": "2026-10-02", "end": "2026-10-13"}, s["window"]
assert s["fetchedAt"] == "2026-10-13T20:00:00Z"
assert len(s["payload"]["results"]) == 8 and [e["url"] for e in s["payload"]["errors"]] == [f.urls(s["window"])[1]], "SEP must fail as not-a-list; empty MPC is fine"
assert f.urls(s["window"])[2].endswith("IPS?startDate=2026-09-13&endDate=2026-10-13&location=ALL&catalog=ALL")
assert f.build(fake({"CME"}), NOW)["payload"]["errors"][-1]["url"].startswith(f.API + "CME"), "one feed down still saves"
try:
    f.build(fake({"FLR", "CME"}), NOW); raise AssertionError("should refuse when FLR and CME both fail")
except SystemExit:
    pass
print("fetch_donki ok")
