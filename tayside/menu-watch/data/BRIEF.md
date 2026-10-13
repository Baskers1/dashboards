# Menu Watch research brief — Dundee & Tayside

Today: 26 Sep 2026. Build a list of places serving food (pubs, restaurants, cafés) in your area, with the menus each one publishes on its OWN website and where to read them.
Towns (exact spellings for `town`): Dundee, Tayport, Wormit, Newport, Invergowrie, Perth, St Andrews, Carnoustie, Arbroath, Forfar, Kirriemuir, Newbigging, Monifieth, Montrose. (Broughty Ferry, Lochee, West End → "Dundee"; Newport-on-Tay → "Newport".)

Aim for the best-known independent + popular venues first (30–45 in your remit), across types. Skip pure takeaways, fast-food chains, work canteens.
Use WebSearch sparingly (shared budget) and WebFetch the venue's own site to find menu pages/PDFs. Never bypass blocked sites; Facebook/Instagram can't be read — record their URL as `social` only.

## Venue schema (one object per venue)
{"id": kebab-case unique, "name": str, "town": one of the towns, "type": "pub"|"restaurant"|"cafe",
 "address": str incl. street, "postcode": "DD1 1AA" (REQUIRED if you can find it — used to match food hygiene ratings),
 "website": url (optional), "social": url (optional),
 "serves_food": "yes"|"unclear", "cuisine": one of ["British pub food","Modern British & European","Scottish","Italian","Indian & South Asian","Chinese & East Asian","Thai & South-East Asian","Mediterranean & Middle Eastern","Mexican & Latin","Burgers, BBQ & American","Seafood & fish and chips","Cafe & breakfast","Bakery & patisserie","Vegan & vegetarian","Other"],
 "trading": "confirmed"|"unclear",
 "menus": [{"title": str, "type": "main"|"seasonal"|"weekly"|"monthly"|"specials"|"sunday-roast"|"set-menu"|"festive"|"event"|"other", "url": direct menu page/PDF url, "format": "html"|"pdf"|"image"|"social", "valid_dates": str (optional, e.g. "Autumn 2026", "Sundays 12-4pm"), "signal": true only if newly announced/launched now (new autumn menu, Christmas 2026 menu, new opening)}],
 "notices": [{"text": short plain sentence, "url": url}]  # announcements: Christmas bookings open, new menu launching, new owners...
}
Rules: only real menus you saw links to; never invent. Christmas/festive 2026 menus are valuable — flag with type "festive" and signal true.

## Output
Write JSON to the path given: {"venues":[...], "sources":[{"name","url","note"}], "notes":[...gaps...]}. Validate with python3 json.load. Final message: counts + gaps only.
