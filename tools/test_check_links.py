"""Self-check for check_links.py (no network): python3 tools/test_check_links.py"""
import importlib.util, os

d = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("check_links", os.path.join(d, "check_links.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

# --- extraction: brackets survive, a stray ")" from prose does not (v1 cut Wikipedia URLs short)
wiki = "https://en.wikipedia.org/wiki/Watford_(UK_Parliament_constituency)"
assert c.tidy(c.URL_RE.findall(wiki)[0]) == wiki
assert c.tidy(c.URL_RE.findall("(see https://foo.org/a)")[0]) == "https://foo.org/a"
assert c.tidy("https://x.org/a.") == "https://x.org/a"
assert c.tidy("https://x.org/?a=1&amp;b=2") == "https://x.org/?a=1&b=2"

# --- page code is not data: template literals and social links are skipped
assert not c.wanted("https://www.tripadvisor.co.uk/${a.a?")
assert not c.wanted("https://www.facebook.com/somevenue")
assert c.wanted("https://www.lemonrock.com/gig/123")

S = lambda **k: c.classify("https://site.org/events/1", **k)["state"]
R = lambda **k: c.classify("https://site.org/events/1", **k)["reason"]

# --- dead
assert S(status=404, final="https://site.org/events/1") == "dead"
assert R(status=410, final="https://site.org/events/1") == "http_410"
assert S(error="DNSError: Could not resolve host", nx_both=True) == "dead"
assert S(status=200, final="https://site.org/events/1", body="<title>Page not found | Site</title>") == "dead"
assert R(status=200, final="https://site.org/", body="<title>Home</title>") == "redirected_to_homepage"
assert c.classify("https://x.org/?u=undefined")["state"] == "dead"

# --- cant_check: never dead on these (LINKS.md section 1)
assert S(error="DNSError: Could not resolve host", nx_both=False) == "cant_check"
assert S(status=403, final="https://site.org/events/1") == "cant_check"
assert S(status=429, final="https://site.org/events/1") == "cant_check"
assert S(status=503, final="https://site.org/events/1") == "cant_check"
assert S(error="Timeout: operation timed out") == "cant_check"
assert R(status=403, final="https://site.org/events/1", body="<title>Just a moment...</title>") == "blocked"
assert S(error="SSLError: certificate verify failed", curl_code=None) == "cant_check"

# --- TLS: macOS curl decides (incomplete chain works in browsers; expired cert does not)
assert S(error="SSLError: unable to get local issuer certificate", curl_code=200) == "works"
assert S(error="SSLError: certificate has expired", curl_code=404) == "dead"

# --- works: a page that merely mentions 404 in its body is fine; only title/h1 count
assert S(status=200, final="https://site.org/events/1", body="<title>Gig</title><p>Room 404</p>") == "works"
assert S(status=200, final="https://site.org/events/1-renamed", body="<title>Gig</title>") == "works"
# a query-string URL landing on "/" is a site's search page, not a lost page
assert c.classify("https://site.org/?event=5", status=200, final="https://site.org/")["state"] == "works"

# --- ledger: only non-works kept; dead_runs counts consecutive dead runs; revival drops the entry
r1 = {"https://a.org/x": {"state": "dead", "reason": "http_404", "status": 404, "pages": ["tayside/whats-on"]},
      "https://b.org/": {"state": "cant_check", "reason": "blocked", "status": 403, "pages": ["tayside/menu-watch"]},
      "https://c.org/": {"state": "works", "reason": None, "status": 200, "pages": ["tayside/menu-watch"]}}
L1 = c.update_ledger({}, r1, "2026-11-17")
assert set(L1["urls"]) == {"https://a.org/x", "https://b.org/"}
assert L1["urls"]["https://a.org/x"]["dead_runs"] == 1
assert c.newly_dead(L1) == ["https://a.org/x"]
assert L1["counts"] == {"checked": 3, "dead": 1, "cant_check": 1, "works": 1}

L2 = c.update_ledger(L1, r1, "2026-11-18")
e = L2["urls"]["https://a.org/x"]
assert e["dead_runs"] == 2 and e["first_dead"] == "2026-11-17" and e["first_seen"] == "2026-11-17"
assert L2["urls"]["https://b.org/"]["cant_check_runs"] == 2
assert c.newly_dead(L2) == [], "a link already reported must not be reported again"

r3 = dict(r1); r3["https://a.org/x"] = {"state": "works", "reason": None, "status": 200, "pages": []}
L3 = c.update_ledger(L2, r3, "2026-11-25")
assert "https://a.org/x" not in L3["urls"], "a revived link leaves the ledger"

r4 = dict(r1); r4["https://a.org/x"] = {"state": "cant_check", "reason": "timeout", "status": None, "pages": []}
L4 = c.update_ledger(L2, r4, "2026-11-25")
assert "dead_runs" not in L4["urls"]["https://a.org/x"], "a cant_check run breaks the dead streak"
assert L4["urls"]["https://a.org/x"]["pages"] == ["tayside/whats-on"], "pages kept when a run has none"

print("check_links: all tests passed")
