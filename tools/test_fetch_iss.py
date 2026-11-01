"""Self-check for fetch_iss.py (no network): python3 tools/test_fetch_iss.py"""
import datetime as dt, importlib.util, json, os, tempfile

spec = importlib.util.spec_from_file_location("f", os.path.join(os.path.dirname(__file__), "fetch_iss.py"))
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
NOW = dt.datetime(2026, 11, 1, 23, 0, tzinfo=dt.timezone.utc)


def fake(pos=None, astros=None):
    pos = pos or {"message": "success", "timestamp": 1793574000,
                  "iss_position": {"latitude": "-12.5", "longitude": "151.25"}}
    def fetch(path):
        if path == "iss-now.json": return pos
        if astros == "boom": raise OSError("astros down")
        return astros or {"people": [{"name": "A", "craft": "ISS"}, {"name": "B", "craft": "Tiangong"}]}
    return fetch


s = f.build(fake(), NOW)
assert (s["lat"], s["lon"], s["crew"]) == (-12.5, 151.25, ["A"]), s  # numbers, ISS crew only
assert s["fetchedAt"] == "2026-11-01T23:00:00Z" and s["positionAt"] == "2026-11-01T23:00:00Z", s
assert "crew" not in f.build(fake(astros="boom"), NOW), "crew failing must not lose the position"
for bad in ({"message": "failure"}, {"message": "success", "timestamp": 1, "iss_position": {"latitude": "91", "longitude": "0"}}):
    try:
        f.build(fake(bad), NOW); raise AssertionError("should reject %s" % bad)
    except ValueError:
        pass

d = tempfile.mkdtemp(); out = os.path.join(d, "iss.json")
real = f.build; f.build = lambda: s
try:
    assert f.main(["x", out]) == 0 and json.load(open(out)) == s and not os.path.exists(out + ".tmp")
    before = open(out).read()
    f.build = lambda: (_ for _ in ()).throw(OSError("down"))
    try:
        f.main(["x", out]); raise AssertionError("should exit non-zero")
    except SystemExit as e:
        assert e.code != 0 and open(out).read() == before, "failed run must keep the old file"
finally:
    f.build = real
print("fetch_iss ok")
