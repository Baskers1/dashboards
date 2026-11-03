"""Self-check for fetch_orbit.py (no network; needs sgp4): python3 tools/test_fetch_orbit.py"""
import datetime as dt, importlib.util, json, os, re

spec = importlib.util.spec_from_file_location("f", os.path.join(os.path.dirname(__file__), "fetch_orbit.py"))
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TLE = """ISS (ZARYA)
1 25544U 98067A   26306.43427755  .00005374  00000+0  10508-3 0  9999
2 25544  51.6332 335.9757 0007139 339.3739  20.6961 15.49150046593183"""
CREW = json.dumps({"iss_expedition": 75, "people": [
    {"name": "Ann <script>Lee</script>", "agency": "NASA", "position": "Commander", "flag_code": "us", "iss": True},
    {"name": "Bo Chen", "agency": "CMSA", "flag_code": "cn", "iss": False},
    {"name": "Cy Ito", "agency": "JAXA", "flag_code": "x\"y", "iss": True}]})
NOW = dt.datetime(2026, 11, 2, 23, 0, tzinfo=dt.timezone.utc)
calls = []
def fake(url):
    calls.append(url)
    return TLE if "celestrak" in url else CREW

s = f.build(fake, NOW, {})
# position: matches wheretheiss.at for the same moment (14.18 N, 107.00 E at 2026-11-02 23:30:14 UTC)
x = f.states(s["tle"], dt.datetime.fromtimestamp(1793662214, dt.timezone.utc), 0, 60)[0][1]
lat, lon = f.subpoint(x)
assert abs(lat - 14.18) < 0.5 and abs(lon - 107.00) < 0.5, (lat, lon)
assert len(s["track"]) == 146 and s["track"][45][0] == "2026-11-02T23:00:00Z" and s["periodMin"] == 93.0
assert all(-52 < p[1] < 52 for p in s["track"]), "the ISS never goes past 51.6 degrees"
# passes: none visible in the next week from Thanet (all midnight, in shadow), then the 12 Nov evening one
th = s["passes"]["thanet"]
assert th and th[0]["start"].startswith("2026-11-12T18:2") and th[0]["from"] == "S", th[:1]
assert all(10 <= p["peakEl"] <= 90 and p["mag"] < 3 and len(p["path"]) == 3 and p["path"][1][1] == p["peakEl"] for v in s["passes"].values() for p in v)
# crew: only those on the ISS, plain text only, bad flag codes dropped
c = s["people"]
assert [p["name"] for p in c["crew"]] == ["Ann scriptLee/script", "Cy Ito"] and c["crew"][1]["flag"] == "" and c["elsewhere"] == 1 and c["expedition"] == 75

# caching: fresh copies are reused without a fetch; a failed fetch keeps the old copy
calls.clear()
s2 = f.build(fake, NOW + dt.timedelta(hours=1), s)
assert calls == [] and s2["tle"] == s["tle"] and s2["tleAt"] == s["tleAt"]
def down(url): raise OSError("boom")
s3 = f.build(down, NOW + dt.timedelta(hours=13), s)
assert s3["people"] == s["people"] and {e["source"] for e in s3["errors"]} == {"tle", "people"}
try:
    f.build(down, NOW, {}); raise AssertionError("no orbit data at all must refuse")
except SystemExit:
    pass

# the page and this script must agree on the places and where they are
page = open(os.path.join(ROOT, "sky", "space-weather", "index.html"), encoding="utf-8").read()
for k, (la, lo) in f.load_places().items():
    m = re.search(r"'?%s'?:\{name:[^}]*?lat:([-\d.]+),lon:([-\d.]+)" % re.escape(k), page)
    assert m and (float(m[1]), float(m[2])) == (la, lo), f"{k}: page and tools/places.json disagree"
print("fetch_orbit ok")
