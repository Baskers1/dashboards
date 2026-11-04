#!/usr/bin/env python3
"""Browser checks for sky/space-weather/index.html (the mirrored DONKI dashboard).

Usage: python3 tools/test_space_weather.py      (needs playwright + chromium; not run in CI)
- snapshot mode: the page as GitHub Pages serves it, under its real CSP, reading data/donki.json
- a hostile snapshot (script injection, malformed flare, out-of-window CME) served the same way
The server runs in-process, so nothing needs killing afterwards.
"""
import copy, functools, http.server, json, os, sys, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = json.load(open(os.path.join(ROOT, "data", "donki.json"), encoding="utf-8"))


def hostile(payload):
    p = copy.deepcopy(payload)
    for r in p["results"]:
        arr = json.loads(r["text"]) if r["text"].strip() else []
        if "/FLR?" in r["url"]:
            d = SNAP["window"]["end"]  # inside the window, so it is rendered, not dropped
            arr.append(dict(flrID=d + "T00:00:00-FLR-009", beginTime=d + "T00:00Z", peakTime=d + "T00:10Z",
                            endTime=None, classType="X1.1", sourceLocation="</script><img src=x onerror=alert(1)>", activeRegionNum=1))
            arr.append(dict(flrID="bad", beginTime="nope", peakTime="nope", classType="<b>", sourceLocation="", activeRegionNum=1))
        if "/CME?" in r["url"]:
            arr.append(dict(activityID="2020-01-01T00:00:00-CME-001", startTime="2020-01-01T00:00Z", cmeAnalyses=[]))
        r["text"] = json.dumps(arr)
    return p


def check(browser, url, label, data=None, expect_tabs=True, kp="real", expect_text=None, refuse_text=None, orbit="real"):
    ctx = browser.new_context(viewport={"width": 390, "height": 900})
    pg = ctx.new_page()
    errs, dialogs, csp = [], [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.on("console", lambda m: "Content Security Policy" in m.text and csp.append(m.text))
    if data is not None:  # serve a substitute snapshot in place of data/donki.json
        pg.route("**/data/donki.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(data)))
    if kp is None:  # no kp.json at all: the page must still work, just without tonight's answer
        pg.route("**/data/kp.json", lambda r: r.fulfill(status=404, body="not found"))
    elif kp != "real":
        pg.route("**/data/kp.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(kp)))
    if orbit is None:
        pg.route("**/data/orbit.json", lambda r: r.fulfill(status=404, body="not found"))
    elif orbit != "real":
        pg.route("**/data/orbit.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(orbit)))
    pg.goto(url)
    pg.wait_for_timeout(1500)
    tabs = pg.locator("#tabs button").count()
    wide = pg.evaluate("document.documentElement.scrollWidth > innerWidth")
    status = pg.inner_text("#status")[:120].replace("\n", " ")
    imgs = pg.locator("img").count()
    body = pg.inner_text("body")
    ctx.close()
    assert not errs, f"{label}: page errors {errs}"
    assert not dialogs and not imgs, f"{label}: injected markup ran"
    assert not csp, f"{label}: CSP violations {csp}"
    assert not wide, f"{label}: horizontal scroll at 390px"
    assert (tabs > 0) == expect_tabs, f"{label}: tabs={tabs}, status={status!r}"
    assert expect_text is None or expect_text in body, f"{label}: missing {expect_text!r}"
    assert refuse_text is None or refuse_text not in body, f"{label}: should not show {refuse_text!r}"
    print("ok", label, "|", status)


def main():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = functools.partial(Quiet, directory=ROOT)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/sky/space-weather/"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            check(b, url, "snapshot", expect_text="Could I see the aurora from Thanet tonight?")
            check(b, url, "no kp.json", kp=None, refuse_text="Could I see the aurora")
            # the ISS tab: tonight's answer for the place, and safe with missing or tampered orbit data
            check(b, url + "#iss", "ISS tab", expect_text="Could I see the ISS from Thanet tonight?")
            check(b, url + "#iss", "no orbit.json", orbit=None, expect_text="No ISS data yet")
            evil = "<img src=x onerror=alert(1)>"
            check(b, url + "?place=plymouth#iss", "hostile orbit.json", orbit={"fetchedAt": evil, "periodMin": evil,
                  "track": [["2026-11-02T23:00:00Z", 10, 20, 1], ["2026-11-02T23:01:00Z", 12, 23, 1], [evil, 999, 0, 1]],
                  "passes": {"plymouth": [{"start": evil, "end": evil, "peak": evil, "peakEl": 99, "mag": evil, "from": evil, "to": "S", "path": []}], evil: []},
                  "people": {"crew": [{"name": evil, "agency": evil, "position": evil, "flag": evil}], "expedition": evil, "elsewhere": evil}},
                  expect_text="Could I see the ISS from Plymouth & Ivybridge tonight? Not in the next 10 days.")
            # one master page: ?place= changes the answer, not just the name (AuroraWatch names Scotland separately)
            yellow = dict(json.load(open(os.path.join(ROOT, "data", "kp.json"))), aurorawatch={"status": "yellow"})
            check(b, url + "?place=dundee", "Dundee on a yellow night", kp=yellow, expect_text="from Dundee & Tayside tonight? Maybe")
            check(b, url + "?place=thanet", "Thanet on a yellow night", kp=yellow, expect_text="from Thanet tonight? Not from here")
            check(b, url + "?place=neath", "Neath opens South Wales", expect_text="from Ammanford, Swansea & Neath Port Talbot tonight?")
            check(b, url + "?place=<script>", "unknown place falls back", expect_text="Could I see the aurora from")
            evil = "<img src=x onerror=alert(1)>"
            check(b, url, "hostile kp.json", kp={"fetchedAt": evil, "aurorawatch": {"status": evil}, "aurorawatchAt": evil,
                  "daily": [{"date": evil, "kp": [99]}, {"date": SNAP["window"]["end"], "kp": [evil, 99, -5, 3]}],
                  "forecast": [{"t": evil, "kp": 9, "kind": "predicted"}, {"t": "2099-01-01T00:00Z", "kp": evil, "kind": evil}]},
                  refuse_text="Kp 99")
            check(b, url, "hostile snapshot", dict(SNAP, payload=hostile(SNAP["payload"])))
            check(b, url, "missing snapshot", {}, expect_tabs=False)
            # links from before the Nov 2026 tab rename still open the matching tab
            for old, new in (("overview", "Now"), ("solar", "Sun"), ("geo", "Earth"), ("mag", "Earth"), ("models", "Forecasts")):
                pg = b.new_page()
                pg.goto(url + "#" + old)
                pg.wait_for_timeout(800)
                got = pg.locator('#tabs button[aria-selected="true"]').inner_text()
                pg.close()
                assert got == new, f"#{old} opened {got!r}, expected {new!r}"
            print("ok old tab links")
            # tapping a calendar day redraws Earth's shield for that day
            pg = b.new_page()
            pg.goto(url + "#earth")
            pg.wait_for_timeout(800)
            before = pg.inner_text("#shield")
            day = pg.locator('#shield').evaluate("() => document.querySelector('.cal button[data-d]:not([aria-pressed=\"true\"])').click()")
            pg.wait_for_timeout(200)
            after = pg.inner_text("#shield")
            pressed = pg.locator('.cal button[aria-pressed="true"]').count()
            pg.close()
            assert after and after != before and pressed == 1, (before, after, pressed)
            print("ok shield day picker")
            # tapping a forecast lane shows that forecast's story
            pg = b.new_page()
            pg.goto(url + "#forecasts")
            pg.wait_for_timeout(800)
            before = pg.inner_text("#race .fclist")
            pg.evaluate("() => document.querySelector('#race [data-fc][aria-pressed=\"false\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
            pg.wait_for_timeout(200)
            after = pg.inner_text("#race .fclist")
            pressed = pg.locator('#race [data-fc][aria-pressed="true"]').count()
            pg.close()
            assert after and after != before and pressed == 1, (before, after, pressed)
            print("ok forecast lane picker")
            # tapping a place on the chooser's map switches the page to that place
            pg = b.new_page()
            pg.goto(url + "?place=thanet#now")
            pg.wait_for_timeout(800)
            pg.evaluate("() => document.querySelector('#placemap [data-place=\"tayside\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
            pg.wait_for_timeout(300)
            chosen, title = pg.eval_on_selector("#place", "e => e.value"), pg.inner_text("#p-now .tonight h3")
            pg.close()
            assert chosen == "tayside" and "Dundee" in title, (chosen, title)
            print("ok place map")
            b.close()
    finally:
        srv.shutdown()
    print("space-weather ok")


if __name__ == "__main__":
    sys.exit(main())
