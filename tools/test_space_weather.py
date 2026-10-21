#!/usr/bin/env python3
"""Browser checks for sky/space-weather/index.html (the mirrored DONKI dashboard).

Usage: python3 tools/test_space_weather.py      (needs playwright + chromium; not run in CI)
- snapshot mode: the page as GitHub Pages serves it, under its real CSP, reading data/donki.json
- live mode: window.claude mocked to answer TinyFish fetch_content with the same payload,
  plus a hostile payload (script injection, malformed flare, out-of-window CME) and each error code
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
            arr.append(dict(flrID="2026-10-01T00:00:00-FLR-009", beginTime="2026-10-01T00:00Z", peakTime="2026-10-01T00:10Z",
                            endTime=None, classType="X1.1", sourceLocation="</script><img src=x onerror=alert(1)>", activeRegionNum=1))
            arr.append(dict(flrID="bad", beginTime="nope", peakTime="nope", classType="<b>", sourceLocation="", activeRegionNum=1))
        if "/CME?" in r["url"]:
            arr.append(dict(activityID="2020-01-01T00:00:00-CME-001", startTime="2020-01-01T00:00Z", cmeAnalyses=[]))
        r["text"] = json.dumps(arr)
    return p


def mock(mode, payload):
    return """window.claude={use:async n=>{ if(n!=='mcp'||%(m)s==='null') return null;
      const P=%(p)s, ev=(h,e)=>setTimeout(()=>h(e),10);
      return Object.freeze({
        watchTool:(s,t,i,h)=>{ ev(h, %(m)s==='ok' ? {type:'data',result:{payload:P}}
          : {type:'error',error:{code:%(m)s,message:'test',retryable:%(m)s==='server_unavailable'}}); return ()=>{} },
        callTool:async()=>({payload:P})})}};""" % dict(m=json.dumps(mode), p=json.dumps(payload))


def check(browser, url, label, init=None, expect_tabs=True):
    ctx = browser.new_context(viewport={"width": 390, "height": 900}, bypass_csp=init is not None)
    pg = ctx.new_page()
    errs, dialogs, csp = [], [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.on("console", lambda m: "Content Security Policy" in m.text and csp.append(m.text))
    if init:
        pg.add_init_script(init)
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
            check(b, url, "live ok", mock("ok", SNAP["payload"]))
            check(b, url, "live hostile", mock("ok", hostile(SNAP["payload"])))
            for code in ("null", "server_not_connected", "approval_required", "server_unavailable"):
                check(b, url, "live " + code, mock(code, None), expect_tabs=False)
            b.close()
    finally:
        srv.shutdown()
    print("space-weather ok")


if __name__ == "__main__":
    sys.exit(main())
