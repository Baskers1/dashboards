"""Flatten raw.json into posts.json: one normalised record per post, deduped."""
import json, re, time

PLACES = ["neath","port talbot","porttalbot","pontardawe","briton ferry","aberavon",
 "skewen","glynneath","glyn neath","margam","baglan","seven sisters","resolven","cwmavon",
 "cwmafan","sandfields","cimla","melincourt","tonna","crynant","bryncoch","ystalyfera",
 "gwaun-cae-gurwen","pontrhydyfen","taibach","sker","afan forest","gnoll","npt"]
# "neath" alone is also the Welsh-English contraction of "beneath"; require a second
# local cue when the only hit is a bare "neath" inside running text.
STRONG = [p for p in PLACES if p != "neath"]
WALES = ["wales","welsh","cymru","swansea","bridgend","glamorgan","valleys","uk","britain","afan","neath port talbot"]
EXCLUDE = ["ontario","canada","australia","new zealand","massachusetts","connecticut"]

def tt_num(x):
    try: return int(x or 0)
    except Exception: return 0

def flatten(o):
    ep, r = o["endpoint"], o["raw"]
    out = []
    if ep == "/v1/tiktok/search/keyword":
        for it in r.get("search_item_list") or []:
            a = it.get("aweme_info") or {}
            st = a.get("statistics") or {}
            au = a.get("author") or {}
            cov = ((a.get("video") or {}).get("cover") or {}).get("url_list") or []
            thumb = next((u for u in cov if ".jpeg" in u or ".jpg" in u), cov[0] if cov else None)
            out.append(dict(platform="TikTok", id=a.get("aweme_id"),
                text=a.get("desc") or "", url=a.get("share_url"),
                author=au.get("unique_id"), author_name=au.get("nickname"),
                likes=tt_num(st.get("digg_count")), views=tt_num(st.get("play_count")),
                comments=tt_num(st.get("comment_count")), shares=tt_num(st.get("share_count")),
                created=a.get("create_time"), thumb=thumb))
    elif ep in ("/v1/reddit/search","/v1/reddit/subreddit/search"):
        for p in r.get("posts") or []:
            out.append(dict(platform="Reddit", id=p.get("id"),
                text=((p.get("title") or "") + " — " + (p.get("selftext") or "")).strip(" —"),
                title=p.get("title"), url=p.get("url"), author=p.get("author"),
                author_name="r/"+(p.get("subreddit") or ""), subreddit=p.get("subreddit"),
                likes=tt_num(p.get("score")), comments=tt_num(p.get("num_comments")),
                views=0, created=p.get("created_utc"), thumb=p.get("thumbnail")))
    elif ep == "/v1/youtube/search":
        for v in r.get("videos") or []:
            ch = v.get("channel") or {}
            out.append(dict(platform="YouTube", id=v.get("id"), text=v.get("title") or "",
                title=v.get("title"), url=v.get("url"), author=ch.get("handle"),
                author_name=ch.get("title"), views=tt_num(v.get("viewCountInt")),
                likes=0, comments=0, created=None, published=v.get("publishedTimeText"),
                thumb=f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg" if v.get("id") else None))
    elif ep == "/v1/threads/search":
        for p in r.get("posts") or []:
            u = p.get("user") or {}
            tp = p.get("text_post_app_info") or {}
            cap = p.get("caption")
            txt = (cap.get("text") if isinstance(cap, dict) else cap) or ""
            code = p.get("code")
            out.append(dict(platform="Threads", id=p.get("pk"), text=txt,
                url=f"https://www.threads.com/@{u.get('username')}/post/{code}" if code else None,
                author=u.get("username"), author_name=u.get("full_name"),
                likes=tt_num(p.get("like_count")), comments=tt_num(tp.get("direct_reply_count")),
                shares=tt_num(tp.get("repost_count")), views=0,
                created=p.get("taken_at"), thumb=None))
    elif ep == "/v1/google/search":
        for g in r.get("results") or []:
            out.append(dict(platform="Facebook", id=g.get("url"),
                text=((g.get("title") or "") + " — " + (g.get("description") or "")).strip(" —"),
                title=g.get("title"), url=g.get("url"), author=None, author_name=None,
                likes=0, views=0, comments=0, created=None, thumb=None))
    return out

def relevant(p):
    t = (p.get("text") or "").lower() + " " + (p.get("author_name") or "").lower() + " " + (p.get("author") or "").lower()
    if any(x in t for x in EXCLUDE): return False
    if any(s in t for s in STRONG): return True
    if "neath" in t:
        # bare "neath" -> needs a Welsh/UK cue, and must not be the "beneath" contraction
        if re.search(r"\bneath\b", t) and any(w in t for w in WALES): return True
    return False

d = json.load(open("raw.json"))
all_posts, seen = [], set()
for o in d:
    for p in flatten(o):
        k = (p["platform"], p.get("id") or p.get("url"))
        if k in seen or not p.get("url"): continue
        seen.add(k); p["queries"] = [str(o["query"])]
        all_posts.append(p)
rel = [p for p in all_posts if relevant(p)]
for p in rel:
    if isinstance(p.get("created"), (int, float)) and p["created"]:
        p["date"] = time.strftime("%Y-%m-%d", time.gmtime(p["created"]))
json.dump(rel, open("posts.json","w"), ensure_ascii=False, indent=1)
from collections import Counter
print("deduped:", len(all_posts), "-> relevant:", len(rel))
print(Counter(p["platform"] for p in rel))
