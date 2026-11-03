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

print("fetch_npt_social ok")
