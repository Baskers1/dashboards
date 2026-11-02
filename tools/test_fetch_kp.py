"""Self-check for fetch_kp.py (no network): python3 tools/test_fetch_kp.py"""
import datetime as dt, importlib.util, json, os, tempfile

spec = importlib.util.spec_from_file_location("f", os.path.join(os.path.dirname(__file__), "fetch_kp.py"))
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
NOW = dt.datetime(2026, 11, 2, 21, 30, tzinfo=dt.timezone.utc)

# real lines from NOAA's file, including the glued "1-1" columns and -1 for blocks not measured yet
DAILY = """:Product: Daily Geomagnetic Data          DGD.txt
#  Date        A     K-indices        A     K-indices        A     K-indices
2026 10 10    40  4 5 6 6 5 4 3 3    90  5 6 7 7 6 5 4 3    76   4.67  5.33  6.67  7.00  5.67  4.33  3.33  3.00
2026 11 02    -1  1 2 3 2 2 1 1-1    -1  0 2 5 5 2 0 0-1     7   1.00  2.00  3.00  2.33  1.67  1.67  1.00 -1.00
"""
FORECAST = json.dumps([
    {"time_tag": "2026-10-26T00:00:00", "kp": 0.33, "observed": "observed", "noaa_scale": None},  # older than a day: dropped
    {"time_tag": "2026-11-02T21:00:00", "kp": 2.0, "observed": "estimated", "noaa_scale": None},
    {"time_tag": "2026-11-03T00:00:00", "kp": 5.67, "observed": "predicted", "noaa_scale": "G1"}])
AW = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<current_status api_version="0.2.5"><updated><datetime>2026-11-02T22:15:31+0000</datetime></updated><site_status project_id="project:AWN" site_id="site:AWN:SUM" status_id="amber"/></current_status>"""

def fake(bad=()):
    def fetch(url):
        if url in bad: raise OSError("boom")
        return {f.DAILY: DAILY, f.FORECAST: FORECAST, f.AW: AW}[url]
    return fetch

s = f.build(fake(), NOW)
assert s["daily"][0] == {"date": "2026-10-10", "kp": [4.67, 5.33, 6.67, 7.0, 5.67, 4.33, 3.33, 3.0]}, s["daily"][0]
assert s["daily"][1]["kp"][-1] is None, "-1 means not measured yet"
assert [r["t"] for r in s["forecast"]] == ["2026-11-02T21:00Z", "2026-11-03T00:00Z"] and s["forecast"][1]["kind"] == "predicted"
assert s["aurorawatch"] == {"status": "amber"} and s["errors"] == []

# one source down keeps the previous copy of that part, with its own age
later = NOW + dt.timedelta(hours=1)
s2 = f.build(fake({f.AW}), later, s)
assert s2["aurorawatch"] == s["aurorawatch"] and s2["aurorawatchAt"] == s["fetchedAt"] and s2["dailyAt"] == s2["fetchedAt"]
assert [e["source"] for e in s2["errors"]] == ["aurorawatch"]
for bad in ('<x><site_status status_id="purple"/></x>', "not xml"):
    try: f.parse_aw(bad); raise AssertionError("bad status must be refused")
    except (ValueError, Exception) as e: assert not isinstance(e, AssertionError)
try:
    f.build(fake({f.DAILY, f.FORECAST, f.AW}), NOW); raise AssertionError("all failed with nothing saved: refuse")
except SystemExit:
    pass

# polite: no network while the saved file is under half an hour old
d = tempfile.mkdtemp(); out = os.path.join(d, "kp.json")
json.dump(s, open(out, "w"))
calls = []
def spy(url): calls.append(url); return fake()(url)
assert f.main(["x", out], NOW + dt.timedelta(minutes=10), spy) == 0 and calls == []
assert f.main(["x", out], NOW + dt.timedelta(minutes=31), spy) == 0 and len(calls) == 3
assert json.load(open(out))["fetchedAt"] == "2026-11-02T22:01:00Z"
print("fetch_kp ok")
