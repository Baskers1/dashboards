"""Self-check for fetch_npt_social.py (no network): python3 tools/test_fetch_npt_social.py

Every case here is a mistake the first build of this pull actually made, so the asserts are
regression cover, not illustration.
"""
import datetime as dt, importlib.util, json, os, tempfile

os.environ.setdefault("NPT_SOCIAL_CACHE", tempfile.mkdtemp())  # never touch the real cache
spec = importlib.util.spec_from_file_location(
    "fns", os.path.join(os.path.dirname(__file__), "fetch_npt_social.py"))
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
TODAY = dt.date(2026, 11, 3)          # a Tuesday
MON = dt.date(2026, 11, 2)

# --- place filtering: every one of these reached the first pull ---------------------------------
assert f.places("Great pub in Neath") == ["Neath"]
assert f.places("the valley beneath the hills") == [], "'beneath' contains 'neath'"
assert f.places("Imports to the Neath: mushrooms and zee-food, r/fallenlondon") == [], "Fallen London"
assert f.places("Hiked Seven Sisters from Beachy Head to Birling Gap") == [], "the Sussex cliffs"
assert f.places("Coffee One Degree opened in Dubai, specifically in Margam") == [], "Dubai Margam"
assert f.places("be the first to shop Neath the Wreath, Plano") == [], "a gift market in Texas"
# a hard NPT token overrides a collision word, so real posts are not thrown away
assert "Port Talbot" in f.places("Seven Sisters Road chippy vs Port Talbot")

# --- date extraction -----------------------------------------------------------------------------
def d(text, posted=MON):
    return sorted((x[0].isoformat(), x[1]) for x in f.dates_in(text, posted))

assert ("2026-11-07", False) in d("Elvis on Saturday 7th November, 8pm")
assert ("2026-10-03", False) in d("Festival continues November 3rd" .replace("November", "October"))
assert ("2026-12-14", False) in d("spaces left for the 14th December")
assert d("Neath Property Market 7/10") == [], "a bare x/10 is a rating, not a date"
assert ("2026-11-07", False) in d("quiz on 7/11"), "dd/mm with a cue word is a date"
assert ("2026-11-05", True) in d("This Thursday at the Ranch"), "weekday resolves off the post date"
assert ("2026-11-02", True) in d("Live music tonight!")
assert ("2026-11-03", True) in d("Open again tomorrow")
# a weekly round-up names the whole week; fanning it out would invent six venue-nights
assert d("Packed week: Monday league, Tuesday darts, Wednesday quiz, Thursday pool, Friday live") == []
# a stated date wins over an inferred one for the same day
only = f.dates_in("Saturday 7th November", MON)
assert [x[1] for x in only if x[0] == dt.date(2026, 11, 7)] == [False]

# --- the time regex: "93:20" inside a longer number is not a time -------------------------------
assert f.TIME.search("doors 8PM").group(0).lower() == "8pm"
assert f.TIME.search("kick off 19:15").group(0) == "19:15"
assert f.TIME.search("hospitality 93:20") is None, "an out-of-range hour is not a time"

# --- closures must be permanent ------------------------------------------------------------------
def fb(text, author, date="2026-10-01", page="https://www.facebook.com/x", **kw):
    return dict(platform="Facebook", id=text[:12] + author, url="u/" + author, author=author,
                text=text, date=date, views=None, likes=None, comments=None, thumb=None,
                venue_page=page, places=["Neath"], food=True, **kw)

shut = f.closures([
    fb("I have made the incredibly hard decision to close Warner's Bar for good.", "Warners Bar"),
    fb("Due to the heatwave we have taken the decision to close tomorrow, reopening Wednesday.",
       "The Docks Cafe"),
    fb("Just to clarify the rumours. Glynneath Bakery IS NOT closing down.", "Glynneath Bakery"),
    fb("The coastal path is now closed permanently.", "Josh Tuck Councillor for Baglan")])
assert "Warners Bar" in shut, "an apostrophe in the name must not hide a real closure"
assert "The Docks Cafe" not in shut, "closed tomorrow for a heatwave is not a closure"
assert "Glynneath Bakery" not in shut, "a denial is not a closure"
assert "Josh Tuck Councillor for Baglan" not in shut, "a councillor is not a food-and-drink venue"

# --- a closure on file is not forgotten when this run's paging misses it ------------------------
# Observed on 3 November 2026: one run found Warners Bar (closed for good 18 March 2026) and the
# Rock and Fountain; the next found only the Rock and Fountain. Re-deriving the list each run
# forgets closures, and a forgotten closure is a shut pub shown as open.
known = [{"venue": "Warners Bar", "announced": "2026-03-18", "url": "u", "quote": "closed for good"}]
kept = f.carry_closures({}, known, [fb("Quiet week", "Warners Bar", date="2026-03-01")])
assert "Warners Bar" in kept and kept["Warners Bar"]["carried_forward"] is True
# ...but a venue posting AFTER its own closure has reopened, so the closure must not stick for ever
reopened = f.carry_closures({}, known, [fb("We are back open!", "Warners Bar", date="2026-09-01")])
assert "Warners Bar" not in reopened, "a post newer than the closure means it reopened"
# this run's own finding always wins over the stored copy
fresh_find = {"Warners Bar": {"venue": "Warners Bar", "announced": "2026-03-18"}}
assert f.carry_closures(fresh_find, known, [])["Warners Bar"].get("carried_forward") is None

# --- rows need a venue, a date and a usable detail -----------------------------------------------
rows, recurring = f.listing_rows([
    fb("Elvis tribute on Saturday 7th November, doors 8pm, £5 entry", "Blancos Hotel, Bar & Restaurant"),
    fb("Sunday carvery served till 3pm every Sunday", "Le Bistro The Crown Skewen"),
    fb("Lovely weather today", "The Dillwyn Arms"),                       # no date, no detail
    fb("Police hunt driver, 9.05pm Thursday", "Valley Times"),            # a news desk, not a venue
    fb("Karaoke every Friday 7:30pm", "Warners Bar"),                     # closed: must not appear
    fb("Live music this Saturday 8pm", "Port Talbot Town Cricket Club"),  # a club, not a venue
    dict(platform="Google", id="g1", url="g", author=None, date=None, views=None, likes=None,
         comments=None, thumb=None, places=["Briton Ferry"], food=True,
         text="The White Lion, Briton Ferry - Facebook - Dec 20, 2024 ... Crown Inn quiz 8pm"),
], TODAY, shut)
venues = {x["venue"] for x in rows}
assert "Blancos Hotel, Bar & Restaurant" in venues and "2026-11-07" in {x["date"] for x in rows}
assert "Valley Times" not in venues and "Port Talbot Town Cricket Club" not in venues
assert "Warners Bar" not in venues and "Warners Bar" not in {x["venue"] for x in recurring}
assert "The Dillwyn Arms" not in venues, "a post with no date is not a listing"
assert "Crown Inn" not in venues, "a snippet stamped 2024 is a stale result, not a listing"
assert any(x["pattern"].lower().startswith("every sunday") for x in recurring)
row = next(x for x in rows if x["venue"].startswith("Blancos"))
assert row["time"] and row["price"] == "£5" and row["date_inferred"] is False and row["needs_check"] is False

# --- venue ranking counts mentions that are not the venue's own posts ---------------------------
recs = [fb("Come to The Dillwyn Arms for the carvery", "The Dillwyn Arms"),      # self-post
        fb("The Dillwyn Arms does the best breakfast", "A Local"),
        fb("Had a great time at The Dillwyn Arms", "Someone Else"),
        fb("The Dillwyn Arms again!", "Third Person"),
        fb("this is the place to go for a Chinese", "A Local"),
        fb("The Place is open daily", "The Place")]
ranked = {v["venue"]: v for v in f.rank_venues(recs, {"The Dillwyn Arms", "The Place"})}
assert ranked["The Dillwyn Arms"]["independent_mentions"] == 3, ranked
assert ranked["The Dillwyn Arms"]["total_mentions"] == 4, "its own post still counts in the total"
assert "The Place" not in ranked, "'The Place' matches 'this is the place' far more than the venue"

# --- end to end, with a fake provider ------------------------------------------------------------
GOOGLE = {"results": [{"title": "The Dillwyn Arms | Pontardawe", "url": "https://www.facebook.com/thedillwynarms",
                       "description": "pub"},
                      {"title": "Gig Guide", "url": "https://www.facebook.com/groups/1719701018281009",
                       "description": "gigs"},
                      {"title": "off patch", "url": "https://www.facebook.com/baglanhotel",
                       "description": "Treorchy"}]}
def posts_for(url):
    """Distinct ids per source, as the real API gives: the same post never arrives under two urls."""
    return {"posts": [{"id": "p" + str(abs(hash(url)) % 9999),
                       "text": "Carvery every Sunday 12pm, 2 meals for £20",
                       "url": url + "/posts/1", "author": {"name": "The Dillwyn Arms"},
                       "publishTime": 1793664000, "reactionCount": 10, "commentCount": 1,
                       "image": None}], "cursor": None}
calls = []
def fake(path, **q):
    calls.append(path)
    if path == "/v1/google/search":
        return dict(GOOGLE, _q=dict(path=path, **q))
    if path.startswith("/v1/facebook/"):
        return dict(posts_for(q["url"]), _q=dict(path=path, **q))
    if path == "/v1/tiktok/search/keyword":
        return {"_q": dict(path=path, **q), "search_item_list": [{"aweme_info": {
            "aweme_id": "t1", "desc": "Resolven Market is open every Saturday from 6am",
            "create_time": 1793664000, "url": "https://tiktok.com/t1",
            "author": {"unique_id": "someone"}, "statistics": {"play_count": 10, "digg_count": 2,
                                                               "comment_count": 0}}}]}
    if path == "/v1/threads/search":
        return {"_q": dict(path=path, **q), "_error": 500}      # one platform down
    return {"_q": dict(path=path, **q), "posts": [], "results": [], "videos": [], "reels": []}

doc = f.build(fake, TODAY, workers=4, depth_group=1, depth_page=1)
assert doc["generated"] == "2026-11-03" and doc["area"] == "Neath Port Talbot"
assert "Bluesky" in doc["platform_coverage"]["unavailable_404"]
assert doc["counts"]["posts_kept"] > 0 and doc["errors"], "a platform that errors is recorded, not fatal"
assert any("thedillwynarms" in c["source"] for c in doc["feeds"])
assert any("1719701018281009" in g for g in doc["listing_groups"])
assert not any("baglanhotel" in c["source"] for c in doc["feeds"]), "off-patch pages stay dropped"
assert any(x["venue"] == "The Dillwyn Arms" for x in doc["recurring"])
# the published file must carry no commenter text, only venue listings and counts
assert set(doc) >= {"listings", "recurring", "venues", "closed", "feeds", "counts"}

# --- throttle and fail-soft ----------------------------------------------------------------------
out = os.path.join(tempfile.mkdtemp(), "npt-food-social.json")
json.dump(doc, open(out, "w"))
before = len(calls)
assert f.main(["x", out], TODAY, fake) == 0 and len(calls) == before, "fresh file: no network"
assert f.main(["x", out, "--force"], TODAY, fake) == 0 and len(calls) > before, "--force refetches"

def empty(path, **q):
    return {"_q": dict(path=path, **q), "posts": [], "results": [], "videos": [], "reels": []}
kept = json.load(open(out))
assert f.main(["x", out, "--force"], TODAY + dt.timedelta(days=2), empty) == 1, "empty pull must not win"
assert json.load(open(out))["counts"] == kept["counts"], "the previous file is kept intact"

# --- a carried closure still suppresses listings end to end -------------------------------------
doc2 = f.build(fake, TODAY, workers=4, depth_group=1, depth_page=1,
               known_closed=[{"venue": "The Dillwyn Arms", "announced": "2026-01-01", "url": "u",
                              "quote": "closed for good"}])
# the fake's only venue posts a carvery dated 2026-11-03, after that closure, so it reads as reopened
assert not any(c["venue"] == "The Dillwyn Arms" for c in doc2["closed"]), "posted since: reopened"
doc3 = f.build(fake, TODAY, workers=4, depth_group=1, depth_page=1,
               known_closed=[{"venue": "Gone Forever Inn", "announced": "2026-01-01", "url": "u",
                              "quote": "closed for good"}])
assert any(c["venue"] == "Gone Forever Inn" and c["carried_forward"] for c in doc3["closed"])

# --- a failed call must not be cached ------------------------------------------------------------
# A cached 401 from a wrong key would survive fixing the key, and the pull would stay empty with
# nothing to show why. This happened for real: the env file was written with a literal placeholder.
cache = tempfile.mkdtemp()
f.CACHE = cache
f.api("/v1/google/search", _key="not-a-real-key", query="neath")   # 401, or no route in a sandbox
assert os.listdir(cache) == [], "a failed response must not be written to the cache"

# --- the weekly refresh and the quiet-source back-off -------------------------------------------
# A cold pull costs ~700 credits, so a cached response is reused until it is due, and a source that
# keeps serving the same posts is re-read less and less often. A local server stands in for the
# provider: nothing here may touch the real API.
import glob, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

POST = {"id": "1", "url": "u1", "text": "Quiz 8pm", "reactionCount": 1, "videoViewCount": 40}
S = {"body": {"posts": [POST]}, "calls": 0, "code": 200}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        S["calls"] += 1
        b = json.dumps(S["body"]).encode()
        self.send_response(S["code"]); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
f.API = "http://127.0.0.1:%d" % srv.server_port

def new_cache():
    f.CACHE = tempfile.mkdtemp()

def cache_files():
    return [p for p in glob.glob(os.path.join(f.CACHE, "*.json"))
            if os.path.basename(p) != "schedule.json"]

def age(days, path=None):
    t = time.time() - days * 86400
    os.utime(path or cache_files()[0], (t, t))

def pull_one(**q):
    return f.api("/v1/facebook/page/posts", _key="x", url="https://www.facebook.com/x", **q)

def every(n=None):
    """The one schedule entry, or the whole schedule when n is given."""
    s = json.load(open(os.path.join(f.CACHE, "schedule.json")))
    return s if n else s[next(iter(s))]

new_cache()
f.CHECKS.update(checked=0, skipped=0, changed=0)
assert pull_one()["posts"] == [POST] and S["calls"] == 1, "a source with no cache is fetched"
assert every()["interval_days"] == 7, "a new source is checked weekly"
assert pull_one()["posts"] == [POST] and S["calls"] == 1, "a cache younger than its interval: no call"
age(8)
assert pull_one() and S["calls"] == 2 and every()["interval_days"] == 14, "due, same posts: wait 14"
assert time.time() - os.path.getmtime(cache_files()[0]) < 120, \
    "the cache is rewritten even when nothing changed, so the next wait runs from this check"
age(8)
pull_one()
assert S["calls"] == 2, "8 days into a 14-day interval is not due"
age(15)
assert pull_one() and every()["interval_days"] == 28 and S["calls"] == 3, "still quiet: wait 28"
age(29)
assert pull_one() and every()["interval_days"] == 28 and S["calls"] == 4, "28 days is the cap"
# an engagement counter ticking up is not a new post: hashing it would end the back-off for ever
S["body"] = {"posts": [dict(POST, reactionCount=99, videoViewCount=9000)]}
age(29)
assert pull_one() and every()["interval_days"] == 28 and S["calls"] == 5, "only the counts moved"
S["body"] = {"posts": [POST, dict(POST, id="2", url="u2", text="Carvery Sunday")]}
age(29)
assert len(pull_one()["posts"]) == 2 and every()["interval_days"] == 7, "a new post: back to weekly"
assert f.CHECKS["checked"] == 6 and f.CHECKS["skipped"] == 2 and f.CHECKS["changed"] == 2, f.CHECKS
assert pull_one()["_q"]["fetched"] == dt.date.today().isoformat(), "fetch date rides in _q"

# a failed refresh must leave both the cache and the schedule alone, and still serve what we have
new_cache()
assert pull_one()["posts"], "seed the cache"
seeded, before = json.load(open(cache_files()[0])), every()
S["code"] = 500
age(8)
served = pull_one()
S["code"] = 200
assert served["posts"] == seeded["posts"], "a failed refresh serves the copy we already have"
assert json.load(open(cache_files()[0])) == seeded and every() == before, \
    "a failed call changes neither the cache nor the schedule, so it is retried next run"

# a cache file written before this change has no schedule entry and no _q, so it is dated weekly
# by its own mtime - today's cache is 768 such files, and none of them may be refetched at once
new_cache()
S["body"] = {"posts": [POST]}
assert pull_one()["posts"], "seed the cache"
os.remove(os.path.join(f.CACHE, "schedule.json"))
p = cache_files()[0]
json.dump({"posts": [POST]}, open(p, "w"))        # as it looked before _q existed
age(3)
quiet = S["calls"]
d = pull_one()
assert S["calls"] == quiet, "under 7 days with no schedule entry: reused, no call"
assert d["_q"]["fetched"] == dt.date.fromtimestamp(os.path.getmtime(p)).isoformat(), \
    "an entry with no stamp is dated by its file"
assert time.time() - os.path.getmtime(p) > 86400, "reusing an entry must not touch its mtime"
age(8)
assert pull_one() and S["calls"] == quiet + 1, "over 7 days with no schedule entry: refetched"

# a corrupt schedule must not take the run down: everything simply becomes due
new_cache()
open(os.path.join(f.CACHE, "schedule.json"), "w").write("{not json")
assert f.schedule() == {} and f.interval_days(f.schedule(), "x") == 7
assert pull_one()["posts"], "a corrupt schedule is replaced, not fatal"

# build() runs api() in a thread pool, so the schedule must not lose entries to a lost update
new_cache()
with f.ThreadPoolExecutor(8) as ex:
    list(ex.map(lambda i: pull_one(cursor=str(i)), range(16)))
assert len(every(n=1)) == 16, "one schedule entry per source, however many threads wrote it"
assert not glob.glob(os.path.join(f.CACHE, "*.tmp")), "no temp files left behind"
# the churn that is actually out there: TikTok hands back a fresh ?u_code on every call, and the
# play count moves. Same video, so the source is still quiet.
def tik(nonce):
    return {"search_item_list": [{"aweme_info": {
        "aweme_id": "t1", "desc": "Resolven Market every Saturday", "create_time": 1793664000,
        "url": "https://tiktok.com/t1", "share_url": "https://tiktok.com/t1?_r=1&u_code=" + nonce,
        "author": {"unique_id": "someone"},
        "statistics": {"play_count": int(nonce), "digg_count": 2, "comment_count": 0}}}]}

def tiktok():
    return f.api("/v1/tiktok/search/keyword", _key="x", query="neath food")

new_cache()
S["body"] = tik("1")
assert tiktok()["search_item_list"], "seed the cache"
S["body"] = tik("999")
age(8)
assert tiktok() and every()["interval_days"] == 14, \
    "a new share token and a higher play count are not a new video"
S["body"] = {"search_item_list": [tik("1")["search_item_list"][0],
                                  {"aweme_info": dict(tik("1")["search_item_list"][0]["aweme_info"],
                                                      aweme_id="t2", desc="Chip shop reopens")}]}
age(15)
assert tiktok() and every()["interval_days"] == 7, "a second video is a new post"
srv.shutdown()

# the output says when the posts behind it were fetched, since a quiet source is only read monthly
def dated(path, **q):
    d = fake(path, **q)
    d["_q"]["fetched"] = "2026-10-20" if "google" in path else "2026-11-02"
    return d

assert doc["posts_fetched"] == {"oldest": None, "newest": None}, "unstamped responses say nothing"
assert f.build(dated, TODAY, workers=4, depth_group=1, depth_page=1)["posts_fetched"] == \
    {"oldest": "2026-10-20", "newest": "2026-11-02"}

print("fetch_npt_social ok")
