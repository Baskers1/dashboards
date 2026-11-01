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


def check(browser, url, label, data=None, expect_tabs=True):
    ctx = browser.new_context(viewport={"width": 390, "height": 900})
    pg = ctx.new_page()
    errs, dialogs, csp = [], [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.on("console", lambda m: "Content Security Policy" in m.text and csp.append(m.text))
    if data is not None:  # serve a substitute snapshot in place of data/donki.json
        pg.route("**/data/donki.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(data)))
    pg.goto(url)
    pg.wait_for_timeout(1500)
    tabs = pg.locator("#tabs button").count()
    wide = pg.evaluate("document.documentElement.scrollWidth > innerWidth")
    status = pg.inner_text("#status")[:120].replace("\n", " ")
    imgs = pg.locator("img").count()
    ctx.close()
    assert not errs, f"{label}: page errors {errs}"
    assert not dialogs and not imgs, f"{label}: injected markup ran"
    assert not csp, f"{label}: CSP violations {csp}"
    assert not wide, f"{label}: horizontal scroll at 390px"
    assert (tabs > 0) == expect_tabs, f"{label}: tabs={tabs}, status={status!r}"
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
            check(b, url, "snapshot")
            check(b, url, "hostile snapshot", dict(SNAP, payload=hostile(SNAP["payload"])))
            check(b, url, "missing snapshot", {}, expect_tabs=False)
            b.close()
    finally:
        srv.shutdown()
    print("space-weather ok")


if __name__ == "__main__":
    sys.exit(main())
