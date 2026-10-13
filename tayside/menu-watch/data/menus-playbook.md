# Dundee & Tayside Menu Watch — playbook

Page: https://claude.ai/artifact/Fgxnsgj32yzut1CFWempEZ (data baked in; no capabilities). Modelled on Thanet Menu Watch.

## Files (menus/)
- `BRIEF.md` — venue research schema for subagents (id, name, town, type, address, postcode, website, social, serves_food, cuisine, trading, menus[], notices[]).
- `data.json` — last published data `{generated, baseline, run_number, history, venues}`; pass as prev to diff menus week on week.
- `ratings.txt` — FSA food hygiene match per venue: `venue-id|FHRSID|P/E/I/A/X|YYYY-MM-DD|FSA name`, or `venue-id|-` for no confident match. P=Pass, E=Pass and Eat Safe, I=Improvement Required, A=Awaiting Inspection, X=Exempt.
- `menus-template.html` — page with `__DATA__` placeholder; hygiene pill, FSA link, "Food hygiene result" bars and hygiene selector.
- `reviews.txt` — Tripadvisor + OpenTable per venue: `venue-id|ta_url|ta_rating|ta_reviews|ot_url|ot_rating|ot_reviews`; `-` = not listed, blank rating = listing found but score not read. build_menus.py reads it from beside ratings.txt.
- `build_menus.py` — `python3 build_menus.py research/ ratings.txt menus-template.html out/menu-watch.html TODAY [prev data.json]`.

## Monday refresh (two scheduled tasks, Europe/London)
- ~06:47 full refresh: restore files from the artifact's data/ folder, re-research menus, refresh hygiene, build, republish.
- ~11:47 second pass: retry unreadable venues and unmatched hygiene rows, rebuild (same-day rerun keeps one history row and diffs against last week), republish only if changed.
- Hygiene from the cloud: Firecrawl scrape (formats rawHtml, maxAge 0) of `https://ratings.food.gov.uk/api/download-data/json/establishments/{FHRSID}` returns JSON with RatingValue and RatingDate. New matches: firecrawl_search `site:ratings.food.gov.uk "<name>" <town>` → /business/{id}, then confirm name + postcode via the JSON.

## Food hygiene (ratings.food.gov.uk)
- API `https://api.ratings.food.gov.uk/Establishments?localAuthorityId=ID&pageSize=5000&pageNumber=N` with header `x-api-version: 2`. The cloud proxy blocks it; run fetches in the user's built-in browser (javascript_tool) and bring back the compact table.
- Councils: Dundee City 209, Angus 199, Fife 212, Perth and Kinross 223. Business types: 1 Restaurant/Cafe/Canteen, 7843 Pub/bar/nightclub, 7844 Takeaway, 7842 Hotel, 7841 Other catering.
- Scotland = FHIS results, not stars. Match by name + postcode; hotels share one record (e.g. Road Hole + Jigger Inn = Old Course Hotel; 18/Rusacks + The Bridge = Rusacks).
- Refresh: re-fetch ratings by FHRSID (`/Establishments/{id}`) for the matched venues; re-try matching only for new venues and the "-" rows.
- 2026-09-26 baseline: 181 venues, 290 menus; Pass 154, Improvement Required 7, Awaiting Inspection 4, no record 16.

## Tripadvisor + OpenTable (added 2026-09-26)
- Tools: TinyFish (`mcp__TinyFish__search` $0.005/query, `fetch_content` $0.001/url, 30 requests/min shared; wallet ~$10 on 26 Sep, top up at agent.tinyfish.ai) and Firecrawl (ran OUT of credits on 26 Sep; use only if it works again).
- Tripadvisor: search `"<name>" <town> tripadvisor` (include_domains tripadvisor.co.uk,tripadvisor.com, location GB). Take rating/count only from snippets naming the venue or with the same d-number ("rated 4.2 of 5", "554 reviews"). Never fetch Tripadvisor pages.
- OpenTable: search `"<name>" <town> opentable` (include_domains opentable.co.uk); accept /r/<slug> (or a profile like /no-1-the-bank) whose title names venue + town. OpenTable /r/ pages are bot-blocked for TinyFish fetch; Firecrawl json scrape works when it has credits.
- Weekly: refresh rating/count for listed venues (1 TA query each); OpenTable re-search only for restaurants/hotels not listed + confirm existing ones still resolve; new venues get both lookups.
- 2026-09-26 baseline: Tripadvisor found 171/181 (167 with rating), OpenTable 32.
- Hygiene fallback: TinyFish fetch_content (format markdown) of https://ratings.food.gov.uk/api/download-data/json/establishments/{FHRSID} returns the JSON (tested).
- Bulk hygiene (tested 2026-09-28): TinyFish fetch_content (markdown) of `https://ratings.food.gov.uk/api/open-data-files/FHRS{code}en-GB.json` returns each council's full FHIS extract (weekly). Codes: Angus 762, Dundee City 772, Fife 775, Perth and Kinross 786. Un-escape markdown backslashes (`\_`, `\&` ...) before json.loads. Use for matching "-" rows by name/postcode/street; confirm with the per-FHRSID JSON.
