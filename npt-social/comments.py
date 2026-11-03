import json, os, time, urllib.parse, urllib.request
API="https://api.scrapecreators.com"; KEY=os.environ["SCRAPECREATORS_API_KEY"]
def call(path, **q):
    url=f"{API}{path}?"+urllib.parse.urlencode(q)
    r=urllib.request.Request(url, headers={"x-api-key":KEY})
    try:
        with urllib.request.urlopen(r, timeout=120) as f: return json.load(f)
    except Exception as e: return {"_err":str(e)[:160]}

REDDIT=[
 ("https://www.reddit.com/r/swansea/comments/1vith93/staying_in_neath/","Staying in Neath"),
 ("https://www.reddit.com/r/swansea/comments/1r34j99/cool_things_to_doplaces_to_eat_iinaround/","Pontardawe things to do"),
 ("https://www.reddit.com/r/Wales/comments/1dxbpnr/looking_for_a_nice_breakfast_place_in_port_talbot/","Breakfast PT/Neath"),
 ("https://www.reddit.com/r/Wales/comments/upkisq/port_talbot_such_a_shithole/","PT shithole"),
 ("https://www.reddit.com/r/Wales/comments/1gjc14m/morrisons_port_talbot/","Morrisons PT"),
 ("https://www.reddit.com/r/swansea/comments/1msytid/margam_park/","Margam Park"),
 ("https://www.reddit.com/r/Wales/comments/12m4v3w/im_so_torn_between_llanelli_and_neath_hows_your/","Llanelli vs Neath"),
 ("https://www.reddit.com/r/neath/comments/1akmhry/living_in_cimla/","Living in Cimla"),
 ("https://www.reddit.com/r/Wales/comments/1fjoqy7/how_has_life_in_port_talbot_changed_recently/","PT changed"),
 ("https://www.reddit.com/r/swansea/comments/120jzd9/neath_vs_llanelli/","Neath vs Llanelli 2"),
]
TIKTOK=[
 ("https://www.tiktok.com/@walesonline/video/7702182700068769057","Chubby Brown refused Plaza"),
 ("https://www.tiktok.com/@chickenpie_83/video/7693155256997399830","Ave you been to NPT"),
 ("https://www.tiktok.com/@tomjoneswales/video/7663111344660417814","Briton Ferry review"),
 ("https://www.tiktok.com/@worcesterslife/video/7561393316600892694","Central House Chinese Neath"),
 ("https://www.tiktok.com/@christopherlevans/video/7677558340578315542","Resolven Market"),
]
out={}
for u,label in REDDIT:
    r=call("/v1/reddit/post/comments", url=u)
    if r.get("_err") or not r.get("comments"):
        r2=call("/v1/reddit/comments", url=u); r = r2 if r2.get("comments") else r
    out[label]={"url":u,"platform":"reddit","r":r}
    print(f"reddit  {label:28} {len(r.get('comments') or [])} comments {r.get('_err') or r.get('message') or ''}", flush=True)
    time.sleep(1)
for u,label in TIKTOK:
    r=call("/v1/tiktok/video/comments", url=u)
    out[label]={"url":u,"platform":"tiktok","r":r}
    print(f"tiktok  {label:28} {len(r.get('comments') or []) } comments {r.get('_err') or r.get('message') or ''}", flush=True)
    time.sleep(1)
json.dump(out, open("comments.json","w"), ensure_ascii=False)
