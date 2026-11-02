#!/usr/bin/env python3
"""Fetch geomagnetic activity for the Space Weather dashboard and save data/kp.json.

Usage: python3 tools/fetch_kp.py [out_path]     (default data/kp.json)
Run by tools/iss-update.sh (launchd com.dashboards.iss, every 10 minutes), but it only goes to the
network when the saved file is at least MIN_AGE_MIN old, so the sources see one request each per half hour.

Sources (free, no key):
- NOAA SWPC daily geomagnetic indices: the last 30 days of planetary Kp, eight 3-hour values a day
- NOAA SWPC planetary Kp forecast: observed, estimated and predicted Kp in 3-hour blocks
- AuroraWatch UK current status (green, yellow, amber, red), Lancaster University
Each source fails soft: a failed one keeps its part of the previous file, so the page never loses data
to a single bad fetch. Exits non-zero without writing only when every source failed and nothing was saved before.
"""
import datetime as dt, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET

DAILY = "https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt"
FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
AW = "https://aurorawatch-api.lancs.ac.uk/0.2/status/current-status.xml"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_AGE_MIN = 30
STATUSES = {"green", "yellow", "amber", "red"}
KINDS = {"observed", "estimated", "predicted"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Baskers1-dashboards (iMac launchd)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def kp_or_none(v):
    v = float(v)
    return round(v, 2) if 0 <= v <= 9 else None  # NOAA writes -1 for a block not measured yet


def parse_daily(text):
    days = []
    for line in text.splitlines():
        m = re.match(r"(\d{4}) (\d\d) (\d\d)\s", line)
        if not m:
            continue
        kp = re.findall(r"-?\d+\.\d\d", line)[-8:]  # the planetary columns are the only ones with decimals
        if len(kp) == 8:
            days.append({"date": "-".join(m.groups()), "kp": [kp_or_none(v) for v in kp]})
    if not days:
        raise ValueError("no daily rows found (format changed?)")
    return days


def parse_forecast(text, now):
    keep = []
    for r in json.loads(text):
        t = dt.datetime.strptime(r["time_tag"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
        if r.get("observed") in KINDS and r.get("kp") is not None and t >= now - dt.timedelta(hours=24):
            k = kp_or_none(r["kp"])
            if k is not None:
                keep.append({"t": t.strftime("%Y-%m-%dT%H:%MZ"), "kp": k, "kind": r["observed"]})
    if not keep:
        raise ValueError("no forecast rows from the last day onwards")
    return keep


def parse_aw(text):
    el = ET.fromstring(text).find(".//site_status")
    s = el.get("status_id") if el is not None else None
    if s not in STATUSES:
        raise ValueError(f"unknown AuroraWatch status {s!r}")
    return {"status": s}


def build(fetch=get, now=None, old=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    old = old or {}
    snap, errors = {"fetchedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ")}, []
    for key, url, parse in (("daily", DAILY, parse_daily), ("forecast", FORECAST, lambda t: parse_forecast(t, now)),
                            ("aurorawatch", AW, parse_aw)):
        try:
            snap[key] = parse(fetch(url))
            snap[key + "At"] = snap["fetchedAt"]
        except Exception as e:  # keep the last good copy of this part
            errors.append({"source": key, "error": str(e)[:200]})
            if key in old:
                snap[key], snap[key + "At"] = old[key], old.get(key + "At", old.get("fetchedAt"))
    if len(errors) == 3 and not old:
        raise SystemExit("every source failed and nothing saved before: " + json.dumps(errors))
    snap["errors"] = errors
    return snap


def fresh(old, now, minutes=MIN_AGE_MIN):
    try:
        t = dt.datetime.strptime(old["fetchedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        return now - t < dt.timedelta(minutes=minutes)
    except (KeyError, TypeError, ValueError):
        return False


def main(argv, now=None, fetch=get):
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "data", "kp.json")
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        with open(out, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    if fresh(old, now):
        print("kp.json is under", MIN_AGE_MIN, "minutes old - not fetching")
        return 0
    snap = build(fetch, now, old)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, out)  # never leave a half-written file for the page to read
    print("saved", out, "| failed:", [e["source"] for e in snap["errors"]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
