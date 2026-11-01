#!/usr/bin/env python3
"""Save the ISS position for the GitHub Pages ISS page (sky/iss/).

Usage: python3 tools/fetch_iss.py [out_path]     (default data/iss.json)
Run on the Mac by tools/iss-update.sh (launchd). Open Notify only serves plain HTTP,
which a Pages (HTTPS) page can't call, so the Mac fetches it and the page reads this file.
Exits non-zero and leaves the old file alone if the position can't be read.
"""
import datetime as dt, json, os, sys, urllib.request

API = "http://api.open-notify.org/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO = "%Y-%m-%dT%H:%M:%SZ"


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Baskers1-dashboards (Mac launchd)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def build(fetch=get, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    pos = fetch("iss-now.json")
    if pos.get("message") != "success":
        raise ValueError("iss-now.json did not say success")
    lat, lon = float(pos["iss_position"]["latitude"]), float(pos["iss_position"]["longitude"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("position out of range: %s,%s" % (lat, lon))
    snap = {"fetchedAt": now.strftime(ISO), "lat": lat, "lon": lon,
            "positionAt": dt.datetime.fromtimestamp(int(pos["timestamp"]), dt.timezone.utc).strftime(ISO)}
    try:  # crew list is a bonus: its failure must not lose the position
        snap["crew"] = [p["name"] for p in fetch("astros.json")["people"] if p.get("craft") == "ISS"]
    except Exception:
        pass
    return snap


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "data", "iss.json")
    try:
        snap = build()
    except Exception as e:
        raise SystemExit("ISS fetch failed, keeping the previous file: %s" % str(e)[:300])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, out)  # never leave a half-written file for the page to read
    print("saved", out, snap["lat"], snap["lon"], "crew:", len(snap.get("crew", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
