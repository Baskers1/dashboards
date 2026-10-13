#!/usr/bin/env python3
"""Fetch the NASA DONKI feeds for the Space Weather dashboard and save a snapshot.

Usage: python3 tools/fetch_donki.py [out_path]     (default data/donki.json)
Run by .github/workflows/donki.yml. The live page in Claude fetches the same feeds through
TinyFish; the GitHub Pages copy reads this snapshot instead. The file uses the same
{results:[{url,text}], errors:[{url,error}]} shape as TinyFish's fetch_content, so the page
parses and validates both the same way. No API key is needed.
Exits non-zero and leaves the old snapshot alone when neither flares nor CMEs came back.
"""
import datetime as dt, json, os, sys, urllib.request

API = "https://ccmc.gsfc.nasa.gov/DONKI-API/get/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def window(today):
    d = lambda n: (today - dt.timedelta(days=n)).isoformat()
    return {"start": d(30), "start11": d(11), "end": d(0)}


def urls(w):
    # must match feedUrls() in the page exactly: the page looks results up by URL
    u = lambda k, s, x="": f"{API}{k}?startDate={s}&endDate={w['end']}{x}"
    return [u("FLR", w["start"]), u("SEP", w["start"]), u("IPS", w["start"], "&location=ALL&catalog=ALL"),
            u("HSS", w["start"]), u("RBE", w["start"]), u("GST", w["start"]), u("MPC", w["start"]),
            u("notifications", w["start11"], "&type=all"), u("CME", w["start"])]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Baskers1-dashboards (GitHub Actions)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8")


def build(fetch=get, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    w = window(now.date())
    results, errors = [], []
    for url in urls(w):
        try:
            text = fetch(url)
            if text.strip() and not isinstance(json.loads(text), list):
                raise ValueError("response is not a JSON list")
            results.append({"url": url, "text": text})
        except Exception as e:  # one feed failing must not sink the others
            errors.append({"url": url, "error": str(e)[:300]})
    ok = {r["url"].split("/get/")[1].split("?")[0] for r in results}
    if not ({"FLR", "CME"} & ok):
        raise SystemExit("neither FLR nor CME fetched; keeping the previous snapshot. " + json.dumps(errors))
    return {"fetchedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window": w,
            "payload": {"results": results, "errors": errors}}


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "data", "donki.json")
    snap = build()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, out)  # never leave a half-written snapshot for the page to read
    print("saved", out, "| ok:", len(snap["payload"]["results"]), "| failed:", [e["url"] for e in snap["payload"]["errors"]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
