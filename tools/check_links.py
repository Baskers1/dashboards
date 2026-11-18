#!/usr/bin/env python3
"""Check every listing link on the What's On / Menu / Community / Consultation Watch pages
and keep data/link-ledger.json up to date. Rules: LINKS.md in dashboards-source.

    python3 tools/check_links.py              check, update the ledger, write a report
    python3 tools/check_links.py --dry-run    check and report, leave the ledger alone
    --no-lychee                               skip the lychee second opinion (it adds ~8 minutes)

Runs on the iMac only: the cloud and device-bridge shells have no internet. Needs curl_cffi and
certifi (both in the pyenv python), dig and /usr/bin/curl. Raw results and reports go to
~/.cache/linkcheck, outside the repo.

Three states per URL (LINKS.md section 1):
  works       2xx/3xx and not a soft 404
  dead        404/410 seen twice, soft 404, redirected to the home page, malformed,
              or NXDOMAIN on BOTH 8.8.8.8 and 1.1.1.1
  cant_check  401/403/429/5xx/other 4xx, bot challenge, timeout, broken TLS,
              DNS failure on one resolver only

The ledger keeps only URLs that are not "works". sync.py drops a URL from published pages once
it has been dead on two runs (dead_runs >= 2), so ledger-dead URLs are re-checked every run even
when no page shows them any more: that is how a revived link gets noticed.
"""
import asyncio, datetime, html, json, os, re, shutil, subprocess, sys, time, urllib.parse
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "link-ledger.json")
CACHE = os.path.expanduser("~/.cache/linkcheck")
SLUGS = {"menu-watch", "whats-on", "whats-on-big", "community-watch", "consultation-watch"}

SOC = re.compile(r'(facebook|fb\.(com|me|watch)|instagram|tiktok|twitter|//x\.com|threads\.net)', re.I)
INFRA = re.compile(r'(w3\.org|fonts\.g|googleapis|gstatic|cdn\.|baskers1\.github\.io|schema\.org)', re.I)
URL_RE = re.compile(r'https?://[^\s"\'<>`\\]+')  # parentheses allowed: Wikipedia URLs carry them
MALFORMED = re.compile(r'(\{\{|\}\}|(?:[=/:])(?:undefined|null|None|NaN)(?:$|[&/#?]))')
SOFT404 = re.compile(r'(page not found|404 error|error 404|not found \||\b404\b|no longer available|'
                     r'event (has )?(ended|expired|not found)|this event is over|sorry, we couldn.t find)', re.I)
CHALLENGE = re.compile(r'(just a moment\.\.\.|cf-chl|attention required|verify you are human|captcha|access denied)', re.I)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def tidy(u):
    """Trim what a regex match drags in after a URL: punctuation, and a ")" with no "(" to close."""
    u = html.unescape(u)
    while u and u[-1] in '.,;:!?]}\'"':
        u = u[:-1]
    while u.endswith(')') and u.count(')') > u.count('('):
        u = u[:-1]
    return u


def wanted(u):
    """True for a data link worth checking. "${" means a JS template literal in page code."""
    return len(u) >= 12 and "${" not in u and not SOC.search(u) and not INFRA.search(u)


def pages():
    m = json.load(open(os.path.join(ROOT, "tools", "dashboards.json"), encoding="utf-8"))
    for d in m["dashboards"]:
        if d.get("slug") in SLUGS and not str(d.get("id", "")).startswith("local:"):
            yield f"{d['area']}/{d['slug']}"


def collect():
    where = defaultdict(set)
    for pg in pages():
        p = os.path.join(ROOT, pg, "index.html")
        if not os.path.exists(p):
            continue
        for u in URL_RE.findall(open(p, encoding="utf-8").read()):
            u = tidy(u)
            if wanted(u):
                where[u].add(pg)
    return where


def classify(url, status=None, final=None, body="", error=None, nx_both=False, curl_code=None):
    """Pure: map one fetch outcome to {"state", "reason"}. No network here, so it is testable."""
    if MALFORMED.search(url):
        return {"state": "dead", "reason": "malformed"}
    if error is not None:
        if re.search(r"resolve|getaddrinfo|Name or service", error, re.I):
            return {"state": "dead", "reason": "nxdomain"} if nx_both else {"state": "cant_check", "reason": "dns_one_resolver"}
        if re.search(r"SSL|certificate|TLS", error, re.I):
            # curl_cffi cannot repair an incomplete chain; browsers and macOS curl can
            if curl_code and 200 <= curl_code < 400:
                return {"state": "works", "reason": "tls_ok_system_curl"}
            if curl_code in (404, 410):
                return {"state": "dead", "reason": f"http_{curl_code}"}
            return {"state": "cant_check", "reason": "tls_broken"}
        if re.search(r"timed out|timeout", error, re.I):
            return {"state": "cant_check", "reason": "timeout"}
        return {"state": "cant_check", "reason": "connection"}
    title = re.search(r'<title[^>]*>(.*?)</title>', body or "", re.S | re.I)
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', body or "", re.S | re.I)
    head = re.sub(r'<[^>]+>', ' ', (title.group(1) if title else "") + " " + (h1.group(1) if h1 else ""))
    if status in (404, 410):
        return {"state": "dead", "reason": f"http_{status}"}
    if status in (401, 403, 429) or (body and status >= 400 and CHALLENGE.search(head + body[:5000])):
        return {"state": "cant_check", "reason": "blocked"}
    if status >= 400:
        return {"state": "cant_check", "reason": f"http_{status}"}
    m = SOFT404.search(head)
    if m:
        return {"state": "dead", "reason": "soft404"}
    sp, fp = urllib.parse.urlsplit(url), urllib.parse.urlsplit(final or url)
    if sp.path.rstrip('/') and not fp.path.rstrip('/') and not sp.query:
        return {"state": "dead", "reason": "redirected_to_homepage"}
    return {"state": "works", "reason": None}


def update_ledger(old, results, today):
    """Pure: fold one run's results into the ledger. Only non-"works" URLs are kept."""
    prev_urls = old.get("urls", {})
    urls = {}
    for u, r in results.items():
        if r["state"] == "works":
            continue
        p = prev_urls.get(u, {})
        e = {"state": r["state"], "reason": r.get("reason"), "status": r.get("status"),
             "pages": r.get("pages") or p.get("pages", []), "first_seen": p.get("first_seen", today),
             "last_checked": today}
        same = p.get("state") == r["state"]
        if r["state"] == "dead":
            e["first_dead"] = p.get("first_dead", today) if same else today
            e["dead_runs"] = p.get("dead_runs", 0) + 1 if same else 1
        else:
            e["cant_check_runs"] = p.get("cant_check_runs", 0) + 1 if same else 1
        urls[u] = e
    runs = (old.get("runs", []) + [today])[-12:]
    counts = {"checked": len(results)}
    for r in results.values():
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"updated": today, "runs": runs, "counts": counts, "urls": dict(sorted(urls.items()))}


def newly_dead(ledger):
    return sorted(u for u, e in ledger["urls"].items() if e["state"] == "dead" and e.get("dead_runs") == 1)


# ---------------------------------------------------------------- network (iMac only)

_dns = {}
def nxdomain_both(host):
    if host not in _dns:
        res = []
        for r in ("8.8.8.8", "1.1.1.1"):
            try:
                o = subprocess.run(["dig", "+time=3", "+tries=1", f"@{r}", host, "A"],
                                   capture_output=True, text=True, timeout=10).stdout
                res.append("status: NXDOMAIN" in o)
            except Exception:
                res.append(False)
        _dns[host] = all(res)
    return _dns[host]


def system_curl(u):
    try:
        o = subprocess.run(["/usr/bin/curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-L", "-m", "20",
                            "-A", UA, u], capture_output=True, text=True, timeout=30).stdout.strip()
        return int(o) if o.isdigit() and o != "000" else None
    except Exception:
        return None


async def fetch(sess, u, sem, locks, certifi_where):
    if MALFORMED.search(u):
        return {"url": u, **classify(u)}
    host = urllib.parse.urlsplit(u).hostname or ""
    async with sem, locks[host]:
        try:
            r = await sess.get(u, timeout=20, allow_redirects=True, impersonate="chrome", verify=certifi_where)
        except Exception as e:
            err = type(e).__name__ + ": " + str(e)[:200]
            nx = curl = None
            if re.search(r"resolve|getaddrinfo|Name or service", err, re.I):
                nx = await asyncio.to_thread(nxdomain_both, host)
            elif re.search(r"SSL|certificate|TLS", err, re.I):
                curl = await asyncio.to_thread(system_curl, u)
            return {"url": u, "error": err, "status": curl, **classify(u, error=err, nx_both=nx, curl_code=curl)}
        body = r.text[:100000] if "html" in r.headers.get("content-type", "") else ""
        return {"url": u, "status": r.status_code, "final": str(r.url),
                **classify(u, r.status_code, str(r.url), body)}


async def run(urls):
    import certifi
    from curl_cffi.requests import AsyncSession
    out = {}
    locks = defaultdict(lambda: asyncio.Semaphore(3))
    async with AsyncSession() as sess:
        sem = asyncio.Semaphore(40)
        t0 = time.time()
        for i, coro in enumerate(asyncio.as_completed([fetch(sess, u, sem, locks, certifi.where()) for u in urls]), 1):
            r = await coro; out[r["url"]] = r
            if i % 1000 == 0:
                print(f"  {i}/{len(urls)} {time.time() - t0:.0f}s", flush=True)
        # a 404/410/soft 404 must be seen twice; cant_check gets one more try (LINKS.md 1)
        again = [u for u, r in out.items() if r["state"] == "cant_check"
                 or (r["state"] == "dead" and r["reason"] not in ("malformed", "nxdomain"))]
        print(f"  retrying {len(again)}", flush=True)
        await asyncio.sleep(30)
        sem = asyncio.Semaphore(10)
        for coro in asyncio.as_completed([fetch(sess, u, sem, locks, certifi.where()) for u in again]):
            r = await coro; out[r["url"]] = r
    return out


def lychee_section(res):
    """Second opinion (LINKS.md 5.2). lychee never changes the ledger; it only lists where the two
    checkers disagree on hard-dead links, for a hand check. lychee reports NXDOMAIN as a generic
    connection failure, and can be fooled by bot walls that answer 200 (National Trust)."""
    exe = shutil.which("lychee") or "/opt/homebrew/bin/lychee"
    if not os.path.exists(exe):
        return ["", "## lychee", "", "Not installed (brew install lychee); skipped."]
    out = os.path.join(CACHE, "lychee.json")
    try:
        subprocess.run([exe, "--no-progress", "--format", "json", "--output", out, "--max-concurrency", "32",
                        "--timeout", "20", "--max-retries", "1", "--user-agent", UA,
                        "--accept", "100..=103,200..=399", os.path.join(CACHE, "urls.txt")],
                       capture_output=True, timeout=3600)
        L = json.load(open(out))
    except Exception as e:
        return ["", "## lychee", "", f"Failed: {type(e).__name__}: {e}"]
    fail = {i["url"].rstrip("/"): i.get("status", {}) for v in L.get("error_map", {}).values() for i in v}
    ly = {u for u, s in fail.items() if s.get("code") in (404, 410)
          or re.search(r"dns|lookup address|no such host|connection failed", s.get("text", ""), re.I)}
    ours = {u.rstrip("/") for u, r in res.items() if r["state"] == "dead" and r["reason"] in ("http_404", "http_410", "nxdomain")}
    a, b = sorted(ours - ly), sorted(ly - ours)
    lines = ["", "## lychee second opinion", "",
             f"Hard-dead: ours {len(ours)}, lychee {len(ly)}, both {len(ours & ly)}. Open the differences by hand."]
    for title, s in (("Only ours", a), ("Only lychee", b)):
        lines += ["", f"### {title} ({len(s)})", ""] + [f"- {u}" for u in s[:30]] + (["- ..."] if len(s) > 30 else [])
    return lines


def main(argv):
    dry = "--dry-run" in argv
    today = datetime.date.today().isoformat()
    where = collect()
    old = json.load(open(LEDGER, encoding="utf-8")) if os.path.exists(LEDGER) else {}
    # re-check ledger-dead URLs too, even when sync.py has already dropped them from the pages
    for u, e in old.get("urls", {}).items():
        if e["state"] == "dead" and u not in where:
            where[u] = set(e.get("pages", []))
    print(f"{len(where)} URLs to check", flush=True)
    res = asyncio.run(run(sorted(where)))
    for u, r in res.items():
        r["pages"] = sorted(where[u])
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"results-{today}.jsonl"), "w") as f:
        for r in res.values():
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(CACHE, "urls.txt"), "w") as f:
        f.write("\n".join(u for u in sorted(res) if not MALFORMED.search(u)) + "\n")
    new = update_ledger(old, res, today)
    fresh = newly_dead(new)
    c = new["counts"]
    lines = [f"# Link check {today}", "",
             f"{c['checked']} checked: {c.get('works', 0)} works, {c.get('dead', 0)} dead, "
             f"{c.get('cant_check', 0)} cant_check ({100 * c.get('dead', 0) / max(1, c['checked']):.1f}% dead).", "",
             f"## Newly dead ({len(fresh)})", ""]
    lines += [f"- {u}  ({new['urls'][u]['reason']}; {', '.join(new['urls'][u]['pages'])})" for u in fresh] or ["None."]
    hidden = [u for u, e in new["urls"].items() if e["state"] == "dead" and e.get("dead_runs", 0) >= 2]
    lines += ["", f"Dead on 2+ runs, so sync.py publishes them without a link: {len(hidden)}."]
    if "--no-lychee" not in argv:
        lines += lychee_section(res)
    report = os.path.join(CACHE, f"report-{today}.md")
    open(report, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    print(f"report: {report}")
    if not dry:
        with open(LEDGER, "w", encoding="utf-8") as f:
            json.dump(new, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print(f"ledger: {LEDGER} ({len(new['urls'])} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
