"""Inject social_signals.json into the three What's On dashboard HTML files.

usage: python3 embed.py near|main|big <in.html> [out.html]   (no out = edit in place)

  main  routine-maintained What's On / Season Ahead pages (QrJx…, LNr1…)
  big   Big Button / friends page (QqFJ…)
  near  the older retired near/season copies

Near/Season share one codebase: adds a "Facebook-only venues" panel (posting-day chart + per-venue tips)
and an "FB only" tag + tip on matching event rows. Big Button: a plain-English note on matching cards
and a short venue list for the chosen area. Re-running replaces a previous injection.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = "/*SOCIAL-SIGNALS*/"
MARK_END = "/*SOCIAL-SIGNALS-END*/"

SHARED_JS = r"""
const SOC=(typeof SOCIAL!=="undefined"&&SOCIAL)||null;
const SDAY={Mon:"Monday",Tue:"Tuesday",Wed:"Wednesday",Thu:"Thursday",Fri:"Friday",Sat:"Saturday",Sun:"Sunday"};
const SOCTOWN={"Broughty Ferry":"Dundee","Newport-on-Tay":"Newport"};
const snrm=s=>String(s||"").toLowerCase().replace(/&/g,"and").replace(/[^a-z0-9]/g,"");
function socialFor(e){
  if(!SOC)return null;const v=snrm(String(e.venue||"").split(",")[0]);if(v.length<4)return null;
  return SOC.venues.find(s=>{const k=snrm(s.venue);return s.social_only&&(v===k||v.startsWith(k)||(k.startsWith(v)&&v.length>5))})||null}
function socialPlain(s){
  if(!s.listing_posts)return "Check their Facebook page for the latest details.";
  let t=`They usually post event details on ${SDAY[s.peak_day]||s.peak_day} ${s.peak_band}s`;
  if(s.median_lead_days!=null)t+=s.median_lead_days<1?", often on the day itself":`, about ${Math.round(s.median_lead_days)} day${Math.round(s.median_lead_days)===1?"":"s"} before`;
  return t+"."}
"""

NEAR_JS = r"""
function panelSocial(){
  if(!SOC)return"";const S=SOC.summary,s=S.groups.social_only,o=S.groups.own_site;
  // main template filters with placeOk(); the older near/season template keeps a st.towns set
  const inArea=t=>typeof placeOk==="function"?placeOk(SOCTOWN[t]||t)||placeOk(t):(!st.towns.size||st.towns.has(t));
  const vs=SOC.venues.filter(v=>v.social_only&&inArea(v.town));
  const max=Math.max(1,...Object.values(s.by_day));
  const peak=Object.entries(s.by_day).sort((a,b)=>b[1]-a[1])[0][0];
  const pc=x=>Math.round(100*(x||0))+"%";
  return `<section class="panel soc-panel"><h3>Facebook-only venues <small>${s.venues} of ${S.venues_checked} checked</small></h3>
    <p class="s">No website of their own, so listings here come second-hand. Compared with venues that do have a site, they post listings less often (${pc(s.listing_share)} of posts vs ${pc(o.listing_share)}) but further ahead (median <b>${s.median_lead_days} days</b> vs ${o.median_lead_days}). Prices appear in only ${pc(s.field_coverage.price)} of their listings, times in ${pc(s.field_coverage.time)}. Busiest posting day: <b>${SDAY[peak]}</b>.</p>
    <div class="socbars" role="img" aria-label="Listing posts by weekday: ${Object.entries(s.by_day).map(([d,n])=>d+" "+n).join(", ")}">${Object.entries(s.by_day).map(([d,n])=>`<div class="sb${d===peak?" pk":""}"><b>${n}</b><span style="height:${Math.round(100*n/max)}%"></span><i>${d}</i></div>`).join("")}</div>
    <ul class="list">${vs.map(v=>`<li><a href="${esc(v.facebook)}" target="_blank" rel="noopener">${esc(v.venue)}</a> <span class="k">${esc(v.town)}${v.last_listing_post?" · last listing "+fmtShort(v.last_listing_post):""}</span><div class="s">${esc(v.check_tip)}</div></li>`).join("")||"<li class='s'>None in the towns you picked.</li>"}</ul>
    <div class="k">Checked ${fmtShort(SOC.generated)} · ${esc(SOC.method)}</div></section>`}
"""

NEAR_CSS = """
.soc{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;border:1px solid var(--line);color:var(--ink-2);margin-left:6px;vertical-align:1px}
.soc-tip{font-size:12.5px;color:var(--ink-3);margin-top:3px}
.soc-tip a{color:var(--accent)}
.socbars{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;height:96px;align-items:end;margin:10px 0 6px}
.sb{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;font-size:11px;color:var(--ink-3)}
.sb span{display:block;width:70%;min-height:2px;background:var(--line);border-radius:3px 3px 0 0}
.sb.pk span{background:var(--accent)}
.sb b{font-weight:700;color:var(--ink-2);font-variant-numeric:tabular-nums}
.sb i{font-style:normal;margin-top:3px}
"""

BIG_CSS = """
.soc{border-left:6px solid var(--accent);padding-left:.6rem;margin-top:.5rem}
.socvenues{margin-top:1.75rem;background:var(--card);border:2px solid var(--line);border-radius:14px;padding:1rem 1.1rem}
.socvenues h2{font-size:1.2rem}
.socvenues li{margin:.6rem 0}
"""

BIG_JS = r"""
function socialSection(towns){
  if(!SOC)return"";const vs=SOC.venues.filter(v=>v.social_only&&towns.includes(SOCTOWN[v.town]||v.town));
  if(!vs.length)return"";
  return `<section class="socvenues"><h2>Places that only post on Facebook</h2><p class="row">These venues don't have their own website. Their plans can change at short notice, so check their Facebook page before you go.</p><ul>${vs.map(v=>`<li><b>${esc(v.venue)}</b>, ${esc(v.town)}. ${esc(socialPlain(v))} <a href="${esc(v.facebook)}" target="_blank" rel="noopener">Their Facebook page</a></li>`).join("")}</ul></section>`}
"""


def strip_old(html):
    # Remove a previous injection so reruns are idempotent.
    return re.sub(r"(<style>)?" + re.escape(MARK) + r".*?" + re.escape(MARK_END) + r"(</style>)?\n?", "", html, flags=re.S)


def inject_data(html, data):
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    i = html.index("const DATA={")
    return html[:i] + f"{MARK}const SOCIAL={js};\n{SHARED_JS}{MARK_END}\n" + html[i:]


def sub1(html, old, new):
    if new in html:  # already patched on a previous run
        return html
    assert html.count(old) == 1, f"anchor not unique/missing: {old[:60]!r} ({html.count(old)})"
    return html.replace(old, new)


def add_css(html, css):
    # Pages carry several <style> blocks; add ours as its own block just before the page body.
    i = html.index('<div class="wrap">')
    return html[:i] + f"<style>{MARK}{css}{MARK_END}</style>\n" + html[i:]


def patch_near(html, data):
    html = strip_old(html)
    html = add_css(html, NEAR_CSS)
    html = inject_data(html, data)
    html = sub1(html, "/* ---------- near mode ---------- */", f"{MARK}{NEAR_JS}{MARK_END}\n/* ---------- near mode ---------- */")
    html = sub1(html, '${e.highlight?`<span class="star-hl">Pick</span>`:""}</div>',
                '${e.highlight?`<span class="star-hl">Pick</span>`:""}${(s=>s?`<span class="soc">FB only</span>`:"")(socialFor(e))}</div>')
    html = sub1(html, '      <div class="meta"><span class="town">${esc(e.town)}</span> · ${esc(venue(e))}</div>',
                '      <div class="meta"><span class="town">${esc(e.town)}</span> · ${esc(venue(e))}</div>\n'
                '      ${(s=>s?`<div class="soc-tip">Facebook-only venue — ${esc(s.check_tip)} <a href="${esc(s.facebook)}" target="_blank" rel="noopener">Check page ↗</a></div>`:"")(socialFor(e))}')
    html = sub1(html, "${panelCouncil(from,addDays(from,41))}${panelCinemas()}", "${panelCouncil(from,addDays(from,41))}${panelSocial()}${panelCinemas()}")
    html = sub1(html, '<div class="twocol">${panelNotes()}${panelSources()}</div>', '<div class="twocol">${panelSocial()}${panelNotes()}${panelSources()}</div>')
    return html


def patch_main(html, data):
    """Template behind the routine-maintained What's On / Season Ahead pages."""
    html = strip_old(html)
    html = add_css(html, NEAR_CSS)
    html = inject_data(html, data)
    html = sub1(html, "/* ---------- near mode ---------- */", f"{MARK}{NEAR_JS}{MARK_END}\n/* ---------- near mode ---------- */")
    html = sub1(html, '    <div class="meta"><b>${esc(e.town)}</b> · ${esc(venue(e))}</div>',
                '    <div class="meta"><b>${esc(e.town)}</b> · ${esc(venue(e))}</div>\n'
                '    ${(s=>s?`<div class="soc-tip"><b>Only posts on Facebook.</b> ${esc(socialPlain(s))} <a href="${esc(s.facebook)}" target="_blank" rel="noopener">Check their page</a></div>`:"")(socialFor(e))}')
    html = sub1(html, "${panelClubs()}${panelNotes()}${panelSources()}</aside>", "${panelClubs()}${panelSocial()}${panelNotes()}${panelSources()}</aside>")
    html = sub1(html, '<div class="twocol">${panelNotes()}${panelSources()}</div>', '<div class="twocol">${panelSocial()}${panelNotes()}${panelSources()}</div>')
    return html


def patch_big(html, data):
    html = strip_old(html)
    html = add_css(html, BIG_CSS)
    html = inject_data(html, data)
    html = sub1(html, "function card(e,opts={}){", f"{MARK}{BIG_JS}{MARK_END}\nfunction card(e,opts={{}}){{")
    html = sub1(html, '    <p class="row"><b>Where:</b> ${esc(venue(e))}, ${esc(e.town)}</p>',
                '    <p class="row"><b>Where:</b> ${esc(venue(e))}, ${esc(e.town)}</p>\n'
                '    ${(s=>s?`<p class="row soc"><b>Good to know:</b> this venue only posts on Facebook. ${esc(socialPlain(s))} <a href="${esc(s.facebook)}" target="_blank" rel="noopener">Check their Facebook page</a></p>`:"")(socialFor(e))}')
    html = sub1(html, '  $("#main").innerHTML=html;\n}', '  $("#main").innerHTML=html+socialSection(towns);\n}')
    return html


PATCH = {"near": patch_near, "main": patch_main, "big": patch_big}


def main(kind, src, dst=None):
    data = json.load(open(os.path.join(HERE, "social_signals.json")))
    # Dashboards only need the public summary — drop post URLs/excerpts to keep pages light.
    slim = {**data, "venues": [{k: v for k, v in x.items() if k != "recent_listings"} for x in data["venues"]]}
    out = PATCH[kind](open(src).read(), slim)
    open(dst or src, "w").write(out)
    print(kind, dst or src, len(out))


if __name__ == "__main__":
    main(*sys.argv[1:4])
