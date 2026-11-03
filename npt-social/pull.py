"""Keyword social pull for Neath Port Talbot across the ScrapeCreators platforms
that exist (tiktok, reddit, youtube, threads, instagram reels, google->facebook).
Writes raw.json. Never prints the key."""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
API="https://api.scrapecreators.com"; KEY=os.environ["SCRAPECREATORS_API_KEY"]

def call(path, **q):
    url=f"{API}{path}?"+urllib.parse.urlencode(q)
    req=urllib.request.Request(url, headers={"x-api-key":KEY})
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as f: return json.load(f)
        except Exception as e:
            if a==2: return {"_err": str(e)[:200]}
            time.sleep(2*(a+1))

TOWNS=["neath","port talbot","pontardawe","briton ferry","aberavon","skewen",
       "glynneath","margam","baglan","seven sisters","resolven","cwmavon","sandfields","cimla"]
JOBS=[]
for t in TOWNS:
    JOBS += [("/v1/tiktok/search/keyword", {"query": t}),
             ("/v1/tiktok/search/keyword", {"query": f"{t} wales"})]
for q in ["neath port talbot","neath events","port talbot gig","neath pub","neath food",
          "margam park","pontardawe arts centre","aberavon beach","neath market",
          "things to do neath","neath town centre","port talbot beach"]:
    JOBS += [("/v1/tiktok/search/keyword", {"query": q}),
             ("/v1/reddit/search", {"query": q}),
             ("/v1/youtube/search", {"query": q}),
             ("/v1/threads/search", {"query": q}),
             ("/v2/instagram/reels/search", {"query": q}),
             ("/v1/google/search", {"query": f"site:facebook.com {q}"})]
for sub in ["Wales","Swansea","neath","Newport","CasualUK"]:
    for q in ["neath","port talbot","pontardawe","margam"]:
        JOBS.append(("/v1/reddit/subreddit/search", {"subreddit": sub, "query": q}))

out=[]
for i,(p,q) in enumerate(JOBS,1):
    r=call(p,**q)
    items = r.get("posts") or r.get("items") or r.get("videos") or r.get("results") \
            or r.get("search_item_list") or r.get("data") or [] if isinstance(r,dict) else []
    out.append({"endpoint":p,"query":q,"err":r.get("_err") if isinstance(r,dict) else None,
                "n":len(items) if isinstance(items,list) else 0,"raw":r})
    print(f"{i:3}/{len(JOBS)} {p:34} {str(q)[:48]:48} n={len(items) if isinstance(items,list) else 0} {(r.get('_err') or '') if isinstance(r,dict) else ''}", flush=True)
    time.sleep(0.6)
json.dump(out, open("raw.json","w"), ensure_ascii=False)
print(f"\n{sum(o['n'] for o in out)} items across {len(out)} calls -> raw.json")
