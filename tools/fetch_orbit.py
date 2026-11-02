#!/usr/bin/env python3
"""Work out where the ISS is, where it has been and will be, and when each place can see it; save data/orbit.json.

Usage: python3 tools/fetch_orbit.py [out_path]     (default data/orbit.json)
Run by tools/iss-update.sh (launchd com.dashboards.iss) every 10 minutes. Needs the sgp4 package
(pip install sgp4==2.27), the standard SGP4 orbit model used with NORAD orbit data.

Sources (free, no key), each fetched only when the saved copy is old, and kept when a fetch fails:
- CelesTrak: the ISS orbit data (TLE), at most every 6 hours
- corquaid's International Space Station APIs: who is in space, at most every 12 hours
Then, with no network: the ground track from 45 minutes ago to 100 minutes ahead, and the visible passes
for each place in tools/places.json over the next 10 days (times can shift by a minute or so that far out;
they sharpen as fresh orbit data arrives). A pass is visible when the ISS is at least
10 degrees up, in sunlight, and the sky at the place is dark (Sun more than 6 degrees below the horizon).
"""
import datetime as dt, json, math, os, re, sys, urllib.request

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
CREW_URL = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO = "%Y-%m-%dT%H:%M:%SZ"
TLE_HOURS, CREW_HOURS = 6, 12
DAYS = 10  # visible passes come in seasons, so look far enough ahead to always name the next one
R_EARTH = 6371.0


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Baskers1-dashboards (iMac launchd)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_tle(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    l1 = next((l for l in lines if l.startswith("1 25544")), None)
    l2 = next((l for l in lines if l.startswith("2 25544")), None)
    if not (l1 and l2 and len(l1) == 69 and len(l2) == 69):
        raise ValueError("no ISS TLE in the response")
    return [l1, l2]


def parse_crew(text):
    d = json.loads(text)
    people = d["people"]
    clean = lambda v, n=80: re.sub(r"[^\w .,'()&/-]", "", str(v or ""))[:n]  # plain words only: the page shows them
    crew = [{"name": clean(p["name"]), "agency": clean(p.get("agency"), 20), "position": clean(p.get("position"), 40),
             "flag": p["flag_code"] if re.fullmatch(r"[a-z]{2}", str(p.get("flag_code", ""))) else ""}
            for p in people if p.get("iss") is True]
    if not crew:
        raise ValueError("nobody listed on the ISS")
    exp = d.get("iss_expedition")
    return {"crew": crew, "expedition": exp if isinstance(exp, int) else None, "elsewhere": sum(1 for p in people if p.get("iss") is not True)}


def jd(t):
    return t.timestamp() / 86400 + 2440587.5


def gmst(j):  # Greenwich mean sidereal time, radians (low precision is plenty for a map and pass times)
    return math.radians((280.46061837 + 360.98564736629 * (j - 2451545.0)) % 360)


def sun_dir(j):  # unit vector to the Sun, Earth-centred inertial frame (low-precision almanac formula)
    n = j - 2451545.0
    g = math.radians(357.528 + 0.9856003 * n)
    lam = math.radians(280.460 + 0.9856474 * n + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    return (math.cos(lam), math.cos(eps) * math.sin(lam), math.sin(eps) * math.sin(lam))


def rot(v, a):  # inertial -> Earth-fixed: rotate by -GMST about the pole
    return (v[0] * math.cos(a) + v[1] * math.sin(a), -v[0] * math.sin(a) + v[1] * math.cos(a), v[2])


def observer(lat, lon):
    a, f = 6378.137, 1 / 298.257223563
    e2, p, l = f * (2 - f), math.radians(lat), math.radians(lon)
    n = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    pos = (n * math.cos(p) * math.cos(l), n * math.cos(p) * math.sin(l), n * (1 - e2) * math.sin(p))
    up = (math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p))
    east = (-math.sin(l), math.cos(l), 0.0)
    north = (-math.sin(p) * math.cos(l), -math.sin(p) * math.sin(l), math.cos(p))
    return pos, up, east, north


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def states(tle, start, minutes, step_s):
    """(time, Earth-fixed ISS position km, sunlit?, Earth-fixed Sun direction) every step_s seconds."""
    from sgp4.api import Satrec
    sat = Satrec.twoline2rv(*tle)
    out = []
    for i in range(int(minutes * 60 / step_s) + 1):
        t = start + dt.timedelta(seconds=i * step_s)
        j = jd(t)
        e, r, _ = sat.sgp4(math.floor(j - 0.5) + 0.5, j - (math.floor(j - 0.5) + 0.5))
        if e:
            raise ValueError(f"sgp4 error {e} at {t}")
        s = sun_dir(j)
        proj = dot(r, s)
        lit = proj > 0 or math.dist(r, tuple(proj * c for c in s)) > R_EARTH  # outside Earth's shadow cylinder
        g = gmst(j)
        out.append((t, rot(r, g), lit, rot(s, g)))
    return out


def subpoint(x):
    return math.degrees(math.atan2(x[2], math.hypot(x[0], x[1]))), math.degrees(math.atan2(x[1], x[0]))


COMPASS = "N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split()


def passes(sts, lat, lon, keep=6):
    pos, up, east, north = observer(lat, lon)
    found, cur = [], None
    for t, x, lit, sun in sts:
        d = tuple(x[i] - pos[i] for i in range(3))
        rng = math.sqrt(dot(d, d))
        el = math.degrees(math.asin(dot(d, up) / rng))
        az = math.degrees(math.atan2(dot(d, east), dot(d, north))) % 360
        seen = el >= 10 and lit and dot(sun, up) < math.sin(math.radians(-6))
        if seen:
            if cur is None:
                cur = {"start": t, "azStart": az, "elStart": el, "peakEl": el, "peakT": t, "peakAz": az, "minRange": rng}
            cur.update(end=t, azEnd=az, elEnd=el)
            if el > cur["peakEl"]:
                cur.update(peakEl=el, peakT=t, peakAz=az)
            cur["minRange"] = min(cur["minRange"], rng)
        elif cur is not None:
            found.append(cur)
            cur = None
    if cur is not None:
        found.append(cur)
    c = lambda a: COMPASS[int((a + 11.25) % 360 // 22.5)]
    return [{"start": p["start"].strftime(ISO), "end": p["end"].strftime(ISO), "peak": p["peakT"].strftime(ISO),
             "peakEl": round(p["peakEl"]), "from": c(p["azStart"]), "to": c(p["azEnd"]),
             # rough brightness: -1.8 at 1000 km, fainter with distance (ignores how much of it is lit)
             "mag": round(-1.8 + 5 * math.log10(p["minRange"] / 1000), 1),
             # where it appears, peaks and disappears: [azimuth, elevation] in degrees, for drawing its path across the sky
             "path": [[round(p["azStart"]), round(p["elStart"])], [round(p["peakAz"]), round(p["peakEl"])], [round(p["azEnd"]), round(p["elEnd"])]]}
            for p in found if p["end"] > p["start"]][:keep]


def age_h(snap, key, now):
    try:
        return (now - dt.datetime.strptime(snap[key], ISO).replace(tzinfo=dt.timezone.utc)).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return 1e9


def build(fetch=get, now=None, old=None, places=None):
    now = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0)
    old, errors = old or {}, []
    snap = {"fetchedAt": now.strftime(ISO)}
    for key, url, parse, hours in (("tle", TLE_URL, parse_tle, TLE_HOURS), ("people", CREW_URL, parse_crew, CREW_HOURS)):
        if key in old and age_h(old, key + "At", now) < hours:
            snap[key], snap[key + "At"] = old[key], old[key + "At"]
            continue
        try:
            snap[key], snap[key + "At"] = parse(fetch(url)), now.strftime(ISO)
        except Exception as e:  # keep the last good copy
            errors.append({"source": key, "error": str(e)[:200]})
            if key in old:
                snap[key], snap[key + "At"] = old[key], old.get(key + "At")
    if "tle" not in snap:
        raise SystemExit("no ISS orbit data, fetched or saved: " + json.dumps(errors))
    start = now - dt.timedelta(minutes=45)
    track = states(snap["tle"], start, 145, 60)
    snap["track"] = [[t.strftime(ISO)] + [round(v, 2) for v in subpoint(x)] + [int(lit)] for t, x, lit, _ in track]
    snap["periodMin"] = round(1440 / float(snap["tle"][1][52:63]), 1)
    sky = states(snap["tle"], now, DAYS * 1440, 20)
    places = places if places is not None else load_places()
    snap["passes"] = {k: passes(sky, *ll) for k, ll in places.items()}
    snap["errors"] = errors
    return snap


def load_places():
    with open(os.path.join(ROOT, "tools", "places.json"), encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def main(argv, now=None, fetch=get):
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "data", "orbit.json")
    try:
        with open(out, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    snap = build(fetch, now, old)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, out)  # never leave a half-written file for the page to read
    print("saved", out, "| passes:", {k: len(v) for k, v in snap["passes"].items()}, "| failed:", [e["source"] for e in snap["errors"]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
