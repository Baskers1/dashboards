#!/usr/bin/env python3
"""Pull Neath Port Talbot food-and-drink social signal and save data/npt-food-social.json.

Usage: python3 tools/fetch_npt_social.py [out_path]   (default data/npt-food-social.json)
       NPT_SOCIAL_CACHE=<dir>   where raw API responses are cached (default ~/.cache/npt-social)
       --force                  ignore the freshness throttle

Needs SCRAPECREATORS_API_KEY in the environment. The key is sent as a header and never printed.

Scope: restaurants, pubs, cafes, pop-ups and markets, across Neath, Port Talbot, Pontardawe and the
surrounding villages. Times in the output are UK local, as posted.

Costs roughly 700 API credits for a cold run, so it is throttled to MIN_AGE_HOURS and every response
is cached. A re-run with a warm cache is free, which is what makes iterating on the parsers cheap.

The cache holds the raw corpus - posts, usernames, comment text - and defaults to a directory OUTSIDE
this repository on purpose. This repo is public and served by GitHub Pages, so only the aggregated
output below is committed: business listings and mention counts, no commenter text. Keep it that way.

What the provider actually serves (verified 2026-11-03, re-check before trusting):
  works  - TikTok keyword search and profile videos, YouTube search, Reddit search, Threads search,
           Instagram reels search, Google search, Facebook group and profile posts
  HTTP 404 - Bluesky, Mastodon, Snapchat, Discord, X/Twitter, and Facebook keyword search
Facebook has no keyword search, so its pages and groups are discovered via Google and then read
directly. That is where the dated listings live; nothing else in the pull carries many.

Output: {listings, recurring, venues, closed, feeds, listing_groups, counts, platform_coverage}.
A post counts as a listing when it names a date; it becomes a row when one venue-night carries a
usable detail (a time, a price, or what is on).

Fails soft: a platform that errors is recorded in "errors" and the rest of the pull still writes.
If nothing at all came back, the previous file is kept and this exits non-zero.

Not produced here: the prose Trend Discovery Brief and its thumbnails under npt-social/. Those are a
write-up over this data, not a scheduled artefact.
"""
import datetime as dt, hashlib, itertools, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.scrapecreators.com"
MIN_AGE_HOURS = 20
CACHE = os.environ.get("NPT_SOCIAL_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "npt-social")

TOWNS = {"neath": "Neath", "port talbot": "Port Talbot", "pontardawe": "Pontardawe",
         "aberavon": "Aberavon", "aberafan": "Aberavon", "skewen": "Skewen",
         "briton ferry": "Briton Ferry", "glynneath": "Glynneath", "resolven": "Resolven",
         "margam": "Margam", "baglan": "Baglan", "cwmavon": "Cwmavon", "cwmafan": "Cwmavon",
         "sandfields": "Sandfields", "cimla": "Cimla", "tonna": "Tonna", "ystalyfera": "Ystalyfera",
         "bryncoch": "Bryncoch", "crynant": "Crynant", "seven sisters": "Seven Sisters",
         "melincourt": "Melincourt", "pontrhydyfen": "Pontrhydyfen", "taibach": "Taibach",
         "melin": "Melin", "pencaerau": "Neath", "tollgate": "Port Talbot", "gnoll": "Neath",
         "neath port talbot": "Neath Port Talbot", "npt": "Neath Port Talbot"}

# Name collisions that all reached the first pull. They are encoded, not re-judged by eye each time:
# re-deriving this list costs an afternoon and silently pollutes the output until someone notices.
BAD = [re.compile(p, re.I) for p in [
    r"\bbeneath\b",                                   # "beneath" contains "neath"
    r"fallen ?london|r/fallenlondon",                 # Fallen London's underground "the Neath"
    r"\bthe neath\b.*(mushroom|zee|surface|london)",  # same, in prose
    r"seven sisters (cliff|sussex|eastbourne|birling|road|station|tube|london)",
    r"beachy head|birling gap|\beastbourne\b|\bseaford\b|belle tout",  # the Sussex Seven Sisters walk
    r"\bdubai\b",                                     # "Margam" is also a Dubai neighbourhood
    r"neath the wreath|jlccntw|collincounty|\bplano\b|\bdfw\b",  # a gift market in Plano, Texas
    r"\b(sydney|ontario|massachusetts|nsw)\b"]]

HARD_NPT = re.compile(r"port talbot|pontardawe|aberavon|briton ferry|glynneath|resolven|ystalyfera|"
                      r"neath port talbot|skewen|cwmavon|cwmafan", re.I)
FOOD = re.compile(
    r"restaurant|pub\b|bar\b|cafe|caff|coffee|coffi|takeaway|take away|chippy|chip shop|food|eat\b|menu|"
    r"breakfast|brunch|lunch|dinner|roast|carvery|curry|chinese|indian|pizza|kebab|bakery|bake|market|"
    r"street food|pop[- ]?up|bistro|tapas|deli|brewery|ale\b|beer|pint|gig|live music|quiz|karaoke|"
    r"open mic|afternoon tea|ice cream|dessert|burger|tearoom|tea room|eatery", re.I)

CORE = ["Neath", "Port Talbot", "Pontardawe", "Aberavon", "Skewen", "Briton Ferry", "Glynneath",
        "Resolven", "Margam", "Neath Port Talbot"]
TERMS = ["restaurant", "pub", "cafe", "food", "takeaway", "market"]
EXTRA = [
    "Neath breakfast", "Port Talbot breakfast", "Neath sunday lunch", "Port Talbot sunday roast",
    "Neath coffee shop", "Port Talbot coffee", "Neath street food", "Neath pop up food", "Neath bakery",
    "Port Talbot curry", "Neath chinese takeaway", "Neath pizza", "Pontardawe live music pub",
    "Neath live music pub", "Neath quiz night", "Resolven market", "Neath indoor market",
    "Pontardawe market", "Port Talbot market", "Neath food festival", "best place to eat Neath",
    "Neath brunch", "Cimla pub", "Tonna Neath food", "Ystalyfera pub", "Baglan pub", "Sandfields pub",
    "Cwmavon pub", "Neath bistro", "Neath beer garden", "Aberavon seafront cafe", "Margam park cafe",
    "Neath farmers market", "Neath christmas market", "Neath vegan", "Neath curry house"]
GOOGLE = ["site:facebook.com " + q for q in [
    "Neath pub live music", "Port Talbot pub live music", "Neath cafe", "Port Talbot cafe",
    "Neath restaurant", "Port Talbot restaurant", "Pontardawe pub", "Neath market", "Resolven market",
    "Neath street food", "Neath pop up kitchen", "groups Neath Port Talbot gig guide",
    "groups what's on Neath Port Talbot", "Neath takeaway", "Neath bakery", "Aberavon cafe",
    "Skewen pub", "Glynneath pub", "Briton Ferry pub", "Neath Port Talbot food festival",
    "Neath quiz night", "Neath christmas market", "Cimla pub", "Cwmavon pub", "Baglan pub"]]

# Venues that exist only in other people's comments: takeaways, breakfast bars and cafes with no
# Facebook page of their own. The Chinese takeaway canon in particular is crowdsourced in comment
# threads and appears nowhere else, so without this seed the best-liked takeaways rank nowhere.
NAMED_VENUES = [
    "Chopsticks", "Tonna Chinese", "Shun Da", "Jade Garden", "Central House", "Lucky Star",
    "China Kitchen", "Seventh Heaven", "New Garden", "Lees Garden", "Wok 2 Yip", "Golden Dragon",
    "Golden Grill", "Hot Flames", "Fortune House", "Mint Masala", "Highlander Thai", "Chandni",
    "Mandy's", "Mandies", "Bros Cafe", "Belly Busters", "Seletions", "Selections", "Cadno Lounge",
    "Number 46", "Forty Six", "Tambini's", "The Front", "Sand Rabbit", "The Mine", "Bella Ciao",
    "Carnivore by the Mine", "Flame & Bake", "Steeltown", "Ashed Raspberry", "Casa Pizza",
    "Grand Sultan", "T Bones", "The Ranch", "Pop In Cafe", "The Hideout", "Memo", "Franco's",
    "Remos", "Portablo Coffi", "Rosa's Bakery", "Saint Hugo", "Leicester House", "La Casona",
    "The Loft", "Dillwyn Arms", "Blancos", "The Brit", "Rolling Mill", "Afan Tavern", "Pig Iron",
    "Castell-Nedd Arms", "Bryncoch Inn", "Le Bistro", "Rock & Fountain", "Resolven Market",
    "Neath Market", "Neath Indoor Market", "Jerk Yard", "Skippys", "ZakInTheBox", "Welsh House",
    "Meze & Grill", "Docks Cafe", "Woody's", "Gossip Cafe", "Old Skool", "Ferrari's",
    "Neath Food and Drink Festival", "Big Food Festival", "Glynneath Bakery", "Baked.ByJones",
    "The Duke", "Green Dragon", "Crown and Sceptre", "Puddlers", "Britannia Inn", "Ferryman",
    "Mulligans", "The Arch", "Bar 98", "Pink Geranium", "Lamb and Flag", "Old White Horse",
    "Bollywood Lounge", "The Tyn", "Margam Deer", "Bagle Brook", "Booths by the Bridge",
    "Food at The Shed", "Sgwd Gwladys", "Neath Kitchen", "Fusion Pizza", "Mint Masala"]

# Facebook sources that the Google sweep finds but which are not in this area, or not venues.
FB_DROP = {"baglanhotel", "TheSmithsRhos", "travellerswell", "milfordtravel", "NeaththeWreath",
           "faithfullyyoursgiftboutique", "RocklandFallFestival", "Jersey-Bakery-61568288601435",
           "The-Vale-of-Neath-pub-Llanelli-61577320043153"}
FB_OFFPATCH = ("llanelli", "treorchy", "rhos,", "plano", "rockland")
NOT_FB_HANDLE = {"groups", "events", "watch", "reel", "photo", "story.php", "pages", "marketplace",
                 "sharer", "login", "permalink.php", "media", "profile.php", "hashtag", "share"}


def api(path, _key=None, **q):
    """GET with an on-disk cache. Returns parsed JSON, or {"_error": ...}. Never logs the key."""
    key = _key or os.environ.get("SCRAPECREATORS_API_KEY")
    if not key:
        raise SystemExit("SCRAPECREATORS_API_KEY is not set")
    name = hashlib.sha1((path + "|" + urllib.parse.urlencode(sorted(q.items()))).encode()).hexdigest()[:16]
    cached = os.path.join(CACHE, name + ".json")
    if os.path.exists(cached):
        try:
            with open(cached, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            pass  # a truncated cache entry: refetch it
    url = API + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"x-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        d = {"_error": e.code}
    except Exception as e:
        d = {"_error": str(e)[:120]}
    d["_q"] = dict(path=path, **q)
    os.makedirs(CACHE, exist_ok=True)
    tmp = cached + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, cached)
    return d


def iso(ts):
    try:
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def places(text):
    """Towns named in this text, or [] if it is one of the known collisions."""
    t = (text or "").lower()
    if any(b.search(t) for b in BAD) and not HARD_NPT.search(t):
        return []
    return sorted({v for k, v in TOWNS.items() if re.search(r"\b" + re.escape(k) + r"\b", t)})


def normalise(responses):
    """Flatten every cached response into one shape: platform, id, url, author, text, date, metrics."""
    out = []
    def add(**kw):
        out.append(kw)
    for d in responses:
        q = d.get("_q") or {}
        path = q.get("path", "")
        if d.get("_error"):
            continue
        src = q.get("url")
        if "tiktok/search" in path or "tiktok/profile" in path:
            items = [i.get("aweme_info", i) for i in d.get("search_item_list", [])] or d.get("aweme_list", [])
            for a in items:
                st = a.get("statistics") or {}
                cover = (((a.get("video") or {}).get("cover") or {}).get("url_list") or [None])[0]
                add(platform="TikTok", id=a.get("aweme_id"), url=a.get("url") or a.get("share_url"),
                    author=(a.get("author") or {}).get("unique_id"), text=a.get("desc") or "",
                    date=iso(a.get("create_time")), views=st.get("play_count"),
                    likes=st.get("digg_count"), comments=st.get("comment_count"), thumb=cover)
        elif "youtube/search" in path:
            for v in d.get("videos", []) + d.get("shorts", []):
                add(platform="YouTube", id=v.get("id"), url=v.get("url"),
                    author=(v.get("channel") or {}).get("title"), text=v.get("title") or "",
                    date=(v.get("publishedTime") or "")[:10] or None, views=v.get("viewCountInt"),
                    likes=None, comments=None, thumb=v.get("thumbnail"))
        elif "reddit/search" in path:
            for p in d.get("posts", []):
                add(platform="Reddit", id=p.get("id"),
                    url="https://www.reddit.com" + (p.get("permalink") or ""),
                    author="r/" + (p.get("subreddit") or ""),
                    text=(p.get("title") or "") + " - " + (p.get("selftext") or "")[:1200],
                    date=(p.get("created_at_iso") or "")[:10] or None, views=None,
                    likes=p.get("ups"), comments=p.get("num_comments"), thumb=None)
        elif "threads/" in path:
            for p in d.get("posts", []):
                cap = p.get("caption")
                add(platform="Threads", id=p.get("pk") or p.get("id"),
                    url=p.get("url") or p.get("canonical_url"),
                    author=(p.get("user") or {}).get("username"),
                    text=(cap.get("text") if isinstance(cap, dict) else cap) or "",
                    date=iso(p.get("taken_at")), views=None, likes=p.get("like_count"),
                    comments=None, thumb=None)
        elif "instagram/" in path:
            for r in d.get("reels", []) + d.get("items", []):
                add(platform="Instagram", id=r.get("shortcode") or r.get("id"), url=r.get("url"),
                    author=(r.get("owner") or {}).get("username"), text=r.get("caption") or "",
                    date=iso(r.get("taken_at")), views=r.get("video_view_count"),
                    likes=r.get("like_count"), comments=r.get("comment_count"),
                    thumb=r.get("thumbnail_src"))
        elif "google/search" in path:
            for r in d.get("results", []):
                add(platform="Google", id=r.get("url"), url=r.get("url"), author=None,
                    text=(r.get("title") or "") + " - " + (r.get("description") or ""),
                    date=None, views=None, likes=None, comments=None, thumb=None)
        elif "facebook/" in path:
            for p in d.get("posts", []):
                img = p.get("image")
                add(platform="Facebook", id=p.get("id"), url=p.get("url"),
                    author=(p.get("author") or {}).get("name"), text=p.get("text") or "",
                    date=iso(p.get("publishTime")) or iso(p.get("creation_time")),
                    views=p.get("videoViewCount"), likes=p.get("reactionCount"),
                    comments=p.get("commentCount"),
                    thumb=img.get("uri") if isinstance(img, dict) else img, venue_page=src)
    seen = {}
    for r in out:
        seen.setdefault((r["platform"], str(r.get("id"))), r)
    return list(seen.values())


def relevant(recs):
    """Keep posts that concern NPT. A Facebook source was itself found by an NPT-targeted search,
    so its geography comes from the page, not the text: "LIVE MUSIC FRIDAY 8PM" names no town."""
    kept = []
    for r in recs:
        blob = (r.get("text") or "") + " " + (r.get("author") or "")
        if r["platform"] == "Facebook":
            low = blob.lower()
            if any(b in low for b in FB_OFFPATCH) and not HARD_NPT.search(low) and "neath" not in low:
                continue
            r["places"] = places(blob) or ["Neath Port Talbot"]
        else:
            p = places(blob)
            if not p:
                continue
            r["places"] = p
        r["food"] = bool(FOOD.search(r.get("text") or "") or FOOD.search(r.get("author") or ""))
        kept.append(r)
    return kept


_FULL = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
         "october", "november", "december"]
# Every accepted spelling is listed in full. An earlier version matched a 3-letter abbreviation
# followed by [a-z]*, which read "Market 7" as 7 March and "Mayor" as May.
MONTHS = {}
for _i, _m in enumerate(_FULL):
    MONTHS[_m] = MONTHS[_m[:3]] = _i + 1
MONTHS["sept"] = 9
# Welsh month names, as official accounts post bilingually. "Mawrth" is left out on purpose:
# it means both March and Tuesday, so it cannot be resolved from the word alone.
MONTHS.update({"ionawr": 1, "chwefror": 2, "ebrill": 4, "mehefin": 6, "gorffennaf": 7, "awst": 8,
               "medi": 9, "hydref": 10, "tachwedd": 11, "rhagfyr": 12})
MONRX = "|".join(sorted(MONTHS, key=len, reverse=True))   # longest first: "march" before "mar"
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5,
            "sunday": 6, "mon": 0, "tue": 1, "tues": 1, "wed": 2, "weds": 2, "thu": 3, "thur": 3,
            "thurs": 3, "fri": 4, "sat": 5, "sun": 6,
            "llun": 0, "mercher": 2, "iau": 3, "gwener": 4, "sadwrn": 5, "sul": 6}
# hour bounded and no adjacent digits, or "93:20" inside a longer number parses as a time
TIME = re.compile(r"(?<!\d)(1[0-2]|0?\d)([:.][0-5]\d)?\s*(am|pm)\b|(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)", re.I)
PRICE = re.compile(r"£\s?\d+(\.\d{2})?|\bfree (entry|admission)\b", re.I)
DETAIL = re.compile(
    r"live music|live band|quiz|karaoke|open mic|bingo|dj\b|acoustic|disco|tribute|menu|special|market|"
    r"festival|street food|pop[- ]?up|tasting|afternoon tea|sunday lunch|sunday roast|carvery|breakfast|"
    r"brunch|curry|steak night|burger|bottomless|supper|dinner|buffet|book(ing|ings)?\b|tickets?\b|"
    r"opening|launch|fun day|craft fair|artisan", re.I)
RECUR = re.compile(r"\bevery\s+(mon|tues?|weds?|thur?s?|fri|sat|sun)[a-z]*|\b(weekly|each week)\b", re.I)
VENUE_KIND = re.compile(
    r"\b(inn|arms|tavern|pub|public house|bar|cafe|caffe|café|coffee|coffi|kitchen|bakery|bakes|"
    r"brasserie|bistro|restaurant|takeaway|chippy|grill|market|lounge|tearoom|tea room|deli|burger|"
    r"pizza|tapas|brewery|streetfood|street food|eatery|hotel|fountain)\b", re.I)
# news desks, clubs, councils and photographers publish dates but are not food-and-drink venues
NOT_VENUE = re.compile(
    r"\b(valley times|walesonline|wales online|council|councillor|cricket club|rfc\b|rugby|property|"
    r"photos|photography|video|theatre|library|school|church|chapel|police|news|radio|gazette)\b", re.I)
OFFPATCH_TEXT = re.compile(r"\banfield\b|\bliverpool f\.?c\b|\bold trafford\b|\bemirates\b", re.I)
# Venue names that are ordinary English phrases match far more text than the venue ever does:
# "The Place" scored 16 on "this is the place to go", "Base" on "baseball", "Miners" on the strike.
GENERIC_VENUES = {"the place", "base", "miners", "the castle", "the shed", "craig y nos", "prince's"}
# permanent only: "closed tomorrow" during a heatwave is not a closure
CLOSED = re.compile(r"clos\w*\s+(?:\S+\s+){0,4}for good|closing down sale|last day of trading|"
                    r"closed permanently|permanently closed|ceased trading", re.I)
NOT_CLOSED = re.compile(r"not closing|isn.t closing", re.I)


def near_year(month, day, base):
    """Pick the year that puts this day and month closest to the post's own date."""
    best = None
    for y in (base.year - 1, base.year, base.year + 1):
        try:
            c = dt.date(y, month, day)
        except ValueError:
            continue
        if best is None or abs((c - base).days) < abs((best - base).days):
            best = c
    return best


def dates_in(text, posted):
    """Dates this text names, as (date, inferred, matched_text). inferred means a weekday was
    resolved against the post's own date rather than stated outright."""
    found, t = [], text or ""
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th|ydd|ed|fed|ain)?\s+(?:of\s+)?(" + MONRX + r")\b\.?", t, re.I):
        d = near_year(MONTHS[m.group(2).lower()], int(m.group(1)), posted or dt.date.today())
        if d:
            found.append((d, False, m.group(0)))
    for m in re.finditer(r"\b(" + MONRX + r")\b\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t, re.I):
        d = near_year(MONTHS[m.group(1).lower()], int(m.group(2)), posted or dt.date.today())
        if d:
            found.append((d, False, m.group(0)))
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])", t):
        dd, mm, yy = int(m.group(1)), int(m.group(2)), m.group(3)
        cue = t[max(0, m.start() - 24):m.end() + 10]
        # a bare "7/10" is a rating, not a date, so require a year or a nearby date cue
        if not (yy or re.search(r"\bon\b|\bfrom\b|\buntil\b|date|📅|🗓|\bmon|\btue|\bwed|\bthu|\bfri|"
                                r"\bsat|\bsun", cue, re.I)):
            continue
        if not (1 <= dd <= 31 and 1 <= mm <= 12):
            continue
        if yy:
            yy = int(yy)
            try:
                found.append((dt.date(yy + 2000 if yy < 100 else yy, mm, dd), False, m.group(0)))
            except ValueError:
                pass
        else:
            d = near_year(mm, dd, posted or dt.date.today())
            if d:
                found.append((d, False, m.group(0)))
    # A weekly round-up names many weekdays; fanning one post across the week invents venue-nights.
    # And a post that states a date ("Saturday 7th November") must not also have its weekday
    # resolved to a different Saturday, which would invent a second venue-night from one event.
    distinct = {m.group(0).lower() for m in re.finditer(r"\b(" + "|".join(WEEKDAYS) + r")(day)?\b", t, re.I)}
    if posted and len(distinct) <= 2 and not found:
        for m in re.finditer(r"\b(this|next)?\s*\b(" + "|".join(WEEKDAYS) + r")(day)?\b", t, re.I):
            w = WEEKDAYS.get(m.group(2).lower())
            if w is None:
                continue
            delta = (w - posted.weekday()) % 7
            if (m.group(1) or "").lower() == "next":
                delta += 7
            found.append((posted + dt.timedelta(days=delta), True, m.group(0).strip()))
        if re.search(r"\btonight\b", t, re.I):
            found.append((posted, True, "tonight"))
        if re.search(r"\btomorrow\b|\byfory\b", t, re.I):
            found.append((posted + dt.timedelta(days=1), True, "tomorrow"))
    best = {}
    for d, inferred, src in found:
        if d not in best or not inferred:  # a stated date beats an inferred one for the same day
            best[d] = (d, inferred, src)
    return list(best.values())


def closures(recs):
    """Venues that have announced a permanent closure, so they are never shown as open."""
    out = {}
    for r in recs:
        if r["platform"] != "Facebook":
            continue
        t = r.get("text") or ""
        a = re.sub(r"\s+", " ", r.get("author") or "").strip()
        if CLOSED.search(t) and not NOT_CLOSED.search(t) and a and VENUE_KIND.search(a):
            out.setdefault(a, {"venue": a, "announced": r.get("date"), "url": r.get("url"),
                               "quote": re.sub(r"\s+", " ", t)[:200]})
    return out


def listing_rows(recs, today, closed=()):
    """Dated venue-night rows and recurring weekly fixtures."""
    closed = {c.lower() for c in closed}
    rows, recurring = [], []
    for r in recs:
        txt = re.sub(r"[ \t]+", " ", (r.get("text") or "")).strip()
        if not txt or OFFPATCH_TEXT.search(txt):
            continue
        posted = None
        if r.get("date"):
            try:
                posted = dt.date.fromisoformat(r["date"])
            except ValueError:
                posted = None
        venue = re.sub(r"\s+", " ", r.get("author") or "").strip()
        is_page = r["platform"] == "Facebook" and r.get("venue_page") and "/groups/" not in r["venue_page"]
        if venue and NOT_VENUE.search(venue):
            continue
        if not (is_page or (venue and VENUE_KIND.search(venue))):
            m = re.search(r"\b((?:The\s+)?[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){0,3}\s+"
                          r"(?:Inn|Arms|Tavern|Hotel|Cafe|Café|Bakery|Kitchen|Brasserie|Bistro|"
                          r"Market|Lounge|Hall))\b", txt)
            if not m or not re.search(r"neath|port talbot|pontardawe|aberavon|skewen|briton ferry|"
                                      r"glynneath|resolven|margam|baglan|cwmavon|cimla|tonna|"
                                      r"ystalyfera", txt, re.I):
                continue
            venue = m.group(1)
        if not venue or NOT_VENUE.search(venue) or not VENUE_KIND.search(venue):
            continue
        if venue.lower() in closed or venue.lower() in GENERIC_VENUES:
            continue
        tm, pr = TIME.search(txt), PRICE.search(txt)
        if not (tm or pr or DETAIL.search(txt)):
            continue  # a date with no usable detail is not a row
        snippet = re.sub(r"\s+", " ", txt)[:220]
        rec = RECUR.search(txt)
        if rec:
            recurring.append({"venue": venue, "pattern": re.sub(r"\s+", " ", rec.group(0)).strip(),
                              "time": tm.group(0) if tm else None, "towns": r.get("places"),
                              "detail": snippet, "platform": r["platform"], "url": r.get("url"),
                              "posted": r.get("date")})
        for d, inferred, src in dates_in(txt, posted):
            if posted and not (posted - dt.timedelta(days=1) <= d <= posted + dt.timedelta(days=180)):
                continue
            if not posted and not (today <= d <= today + dt.timedelta(days=180)):
                continue  # a Google result carries no post date, so window it against today
            if r["platform"] == "Google":
                if inferred:
                    continue
                years = [int(y) for y in re.findall(r"\b(20\d{2})\b", txt)]
                if any(y < today.year for y in years) and not re.search(r"\b(hour|hours|day|days) ago\b", txt, re.I):
                    continue  # a snippet stamped with an older year is a stale result
            rows.append({"date": d.isoformat(), "venue": venue, "towns": r.get("places"),
                         "time": tm.group(0) if tm else None, "price": pr.group(0) if pr else None,
                         "detail": snippet, "platform": r["platform"], "url": r.get("url"),
                         "posted": r.get("date"), "date_inferred": inferred, "date_text": src,
                         "recurring": bool(rec),
                         "needs_check": r["platform"] == "Google" or inferred})
    one = {}
    for x in rows:  # one row per venue-night per announcement
        one.setdefault((x["date"], x["venue"].lower(), x["detail"][:60]), x)
    seen = {}
    for x in recurring:
        k = (x["venue"].lower(), x["pattern"].lower())
        if k not in seen or (x["time"] and not seen[k]["time"]):
            seen[k] = x
    return (sorted(one.values(), key=lambda x: (x["date"], x["venue"].lower())),
            sorted(seen.values(), key=lambda x: x["venue"].lower()))


def rank_venues(recs, names, min_independent=3):
    """Rank venues by mentions that are not the venue posting about itself: a page naming itself
    measures publishing effort, not popularity."""
    tally = {}
    for r in recs:
        t = r.get("text") or ""
        author = (r.get("author") or "").lower()
        for n in names:
            # The council and the local paper have busy pages but are not venues. Note there is no
            # VENUE_KIND test here: "The Mine", "Chopsticks" and "Mandy's" name no venue type.
            if n.lower() in GENERIC_VENUES or NOT_VENUE.search(n):
                continue
            if not re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", t, re.I):
                continue
            e = tally.setdefault(n, {"venue": n, "total_mentions": 0, "independent_mentions": 0,
                                     "platforms": set()})
            e["total_mentions"] += 1
            e["platforms"].add(r["platform"])
            if n.lower().rstrip("s'’") not in author:
                e["independent_mentions"] += 1
    out = [dict(v, platforms=sorted(v["platforms"])) for v in tally.values()
           if v["independent_mentions"] >= min_independent]
    return sorted(out, key=lambda x: -x["independent_mentions"])


def search_jobs():
    """Every keyword search, one job per call. Only the platforms the provider actually serves."""
    tiktok = [f"{t} {k}" for t, k in itertools.product(CORE, TERMS)] + EXTRA
    yt = [f"{t} {k}" for t, k in itertools.product(["Neath", "Port Talbot", "Pontardawe"],
                                                   ["restaurant", "pub", "cafe", "food review", "market"])]
    reddit = [f"{t} {k}" for t, k in itertools.product(["Neath", "Port Talbot", "Pontardawe"],
                                                       ["restaurant", "pub", "cafe", "food", "takeaway"])]
    reddit += ["Neath market", "Resolven market", "Neath breakfast", "Neath curry", "Neath coffee"]
    social = ["Neath pub", "Neath cafe", "Neath restaurant", "Neath food", "Neath takeaway",
              "Port Talbot cafe", "Port Talbot pub", "Port Talbot food", "Port Talbot restaurant",
              "Pontardawe cafe", "Aberavon cafe", "Neath market", "Resolven market", "Margam cafe",
              "Skewen food", "Briton Ferry pub", "Glynneath cafe", "Neath coffee", "Neath bakery",
              "Neath brunch"]
    jobs = [("/v1/tiktok/search/keyword", {"query": q}) for q in tiktok]
    jobs += [("/v1/youtube/search", {"query": q}) for q in yt]
    jobs += [("/v1/reddit/search", {"query": q, "sort": "relevance"}) for q in reddit]
    jobs += [("/v1/threads/search", {"query": q}) for q in social]
    jobs += [("/v2/instagram/reels/search", {"query": q}) for q in social]
    jobs += [("/v1/google/search", {"query": q}) for q in GOOGLE]
    return jobs


def facebook_targets(responses):
    """Groups and pages named by the Google results. Facebook has no keyword search, so this
    discovery step is the only way into the layer that actually carries dated listings."""
    groups, pages = [], []
    for d in responses:
        if (d.get("_q") or {}).get("path") != "/v1/google/search":
            continue
        for r in d.get("results", []):
            u = r.get("url") or ""
            m = re.search(r"facebook\.com/groups/([0-9A-Za-z._-]+)", u)
            if m:
                if m.group(1) not in groups:
                    groups.append(m.group(1))
                continue
            m = re.search(r"facebook\.com/(?:p/)?([0-9A-Za-z._-]{3,})(?:/|$)", u)
            if m and m.group(1) not in NOT_FB_HANDLE and m.group(1) not in FB_DROP \
                    and m.group(1) not in pages:
                pages.append(m.group(1))
    return groups, pages


def pull(fetch, workers=8, depth_group=6, depth_page=4):
    """Run the searches, discover the Facebook sources, then page through them.
    One Facebook call returns about three posts, so the paging depth is what decides whether any
    forward listings are seen at all: the first unpaged pass found 17 rows, paging found 34."""
    responses, errors = [], []
    def run(job):
        return job, fetch(job[0], **job[1])
    with ThreadPoolExecutor(workers) as ex:
        for job, d in ex.map(run, search_jobs()):
            responses.append(d)
            if d.get("_error"):
                errors.append({"call": job[0], "query": job[1].get("query"), "error": d["_error"]})
    groups, pages = facebook_targets(responses)
    targets = [("/v1/facebook/group/posts", f"https://www.facebook.com/groups/{g}", depth_group)
               for g in groups]
    targets += [("/v1/facebook/profile/posts", f"https://www.facebook.com/{p}", depth_page)
                for p in pages]
    def chain(target):
        path, url, depth = target
        got, cursor = [], None
        for _ in range(depth):
            d = fetch(path, **({"url": url} if cursor is None else {"url": url, "cursor": cursor}))
            got.append(d)
            if d.get("_error") or not d.get("posts"):
                break
            cursor = d.get("cursor")
            if not cursor:
                break
        return got
    with ThreadPoolExecutor(workers) as ex:
        for got in ex.map(chain, targets):
            responses += got
    return responses, errors, groups, pages


def comment_texts(fetch, recs, limit=22, workers=6):
    """Comment threads on the most-engaged food posts. The local canon - which takeaway, which
    breakfast, which roast - is argued out in comments, not in the posts themselves."""
    def score(r):
        return (r.get("comments") or 0) * 10 + (r.get("likes") or 0)
    pick = [r for r in recs if r["platform"] in ("TikTok", "Reddit") and r.get("food") and r.get("url")]
    pick.sort(key=score, reverse=True)
    jobs = [("/v1/tiktok/video/comments" if r["platform"] == "TikTok" else "/v1/reddit/post/comments",
             r["url"], r["platform"]) for r in pick[:limit]]
    out = []
    def run(job):
        path, url, platform = job
        return platform, fetch(path, url=url)
    with ThreadPoolExecutor(workers) as ex:
        for platform, d in ex.map(run, jobs):
            if d.get("_error"):
                continue
            for c in (d.get("comments") or [])[:60]:
                text = c.get("text") if platform == "TikTok" else (c.get("body") or c.get("selftext"))
                if text:
                    out.append({"platform": platform, "text": text, "author": ""})
    return out


def build(fetch, today=None, redact=lambda s: s, **kw):
    today = today or dt.date.today()
    responses, errors, groups, pages = pull(fetch, **kw)
    recs = relevant(normalise(responses))
    closed = closures(recs)
    rows, recurring = listing_rows(recs, today, closed)
    # the gazetteer is the venue pages' own names: whatever posted in this area is a venue here
    names = {re.sub(r"\s+", " ", r["author"]).strip() for r in recs
             if r["platform"] == "Facebook" and r.get("author") and r.get("venue_page")
             and "/groups/" not in r["venue_page"] and 3 < len(r["author"]) < 48}
    names.update(NAMED_VENUES)
    comments = comment_texts(fetch, recs)
    venues = rank_venues(recs + comments, names)
    yielded = {}
    for r in recs:
        if r["platform"] != "Facebook" or not r.get("venue_page"):
            continue
        e = yielded.setdefault(r["venue_page"], {"source": r["venue_page"], "posts": 0, "dated": 0})
        e["posts"] += 1
        if dates_in(r.get("text") or "", dt.date.fromisoformat(r["date"]) if r.get("date") else None):
            e["dated"] += 1
    feeds = sorted((f for f in yielded.values() if f["dated"]), key=lambda f: -f["dated"])
    def clean(rows_):
        for x in rows_:
            for k in ("detail", "venue", "quote"):
                if isinstance(x.get(k), str):
                    x[k] = redact(x[k])
        return rows_
    return {
        "generated": today.isoformat(),
        "area": "Neath Port Talbot",
        "scope": "restaurants, pubs, cafes, pop-ups and markets",
        "timezone": "Europe/London",
        "source": "ScrapeCreators API",
        "row_rule": "a post counts as a listing when it names a date; it becomes a row when one "
                    "venue-night carries a usable detail (a time, a price, or what is on). "
                    "date_inferred means a weekday was resolved against the post's own publish date. "
                    "needs_check means the evidence is a search snippet or an inferred date.",
        "platform_coverage": {
            "searchable": ["TikTok", "YouTube", "Reddit", "Threads", "Instagram", "Google",
                           "Facebook (page and group feeds only)"],
            "unavailable_404": ["Bluesky", "Mastodon", "Snapchat", "Discord", "X/Twitter",
                                "Facebook keyword search"],
            "note": "Those five networks have no ScrapeCreators endpoint and return HTTP 404. "
                    "Facebook has no keyword search, so its pages and groups are found via Google "
                    "and read directly.",
        },
        "counts": {"api_responses": len(responses), "posts_kept": len(recs),
                   "comments_read": len(comments),
                   "food_and_drink_posts": sum(1 for r in recs if r.get("food")),
                   "listing_rows": len(rows),
                   "listing_rows_forward": sum(1 for x in rows if x["date"] >= today.isoformat()),
                   "recurring_fixtures": len(recurring), "venues_ranked": len(venues),
                   "closed_venues": len(closed), "facebook_groups": len(groups),
                   "facebook_pages": len(pages)},
        "listings": clean([x for x in rows if x["date"] >= today.isoformat()]),
        "recurring": clean(recurring),
        "venues": venues,
        "closed": clean(sorted(closed.values(), key=lambda c: str(c["announced"]), reverse=True)),
        "feeds": feeds[:30],
        "listing_groups": [f"https://www.facebook.com/groups/{g}" for g in groups],
        "errors": errors[:40],
    }


def fresh(old, now, hours=MIN_AGE_HOURS):
    try:
        t = dt.date.fromisoformat(old["generated"])
    except (KeyError, TypeError, ValueError):
        return False
    return (now.date() - t) < dt.timedelta(hours=hours)


def main(argv, today=None, fetch=api):
    args = [a for a in argv[1:] if a != "--force"]
    out = args[0] if args else os.path.join(ROOT, "data", "npt-food-social.json")
    today = today or dt.date.today()
    try:
        with open(out, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    if old and "--force" not in argv and fresh(old, dt.datetime.combine(today, dt.time())):
        print(os.path.basename(out), "is under", MIN_AGE_HOURS, "hours old - not fetching")
        return 0
    # Reuse the repo's own redaction so the published file holds no personal contact detail.
    # This must not degrade quietly: a silent fallback to identity would publish phone numbers.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from sync import redact
    except ImportError as e:
        raise SystemExit(f"cannot import redact from tools/sync.py ({e}); refusing to write an "
                         f"unredacted file")
    doc = build(fetch, today, redact)
    if not doc["listings"] and not doc["venues"]:
        if old:
            print("nothing came back; keeping the previous", os.path.basename(out))
            return 1
        raise SystemExit("nothing came back and nothing saved before: " + json.dumps(doc["errors"][:5]))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    os.replace(tmp, out)  # never leave a half-written file for the page to read
    c = doc["counts"]
    print(f"saved {out} | {c['listing_rows_forward']} forward rows, {c['recurring_fixtures']} recurring, "
          f"{c['venues_ranked']} venues, {c['closed_venues']} closed | failed calls: {len(doc['errors'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
