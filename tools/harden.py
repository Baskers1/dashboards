"""Security and accessibility fixes applied to every page sync.py mirrors.

The dashboards build links from scraped data with string concatenation, so a hostile or
malformed URL (one containing a quote, or a javascript: link) could run script on
baskers1.github.io, where every dashboard shares one origin. harden() makes each page safe
whatever its template does:

  * a Content-Security-Policy <meta> that allows only the page's own inline scripts (by
    sha256 hash), so injected <script>, event-handler attributes and javascript: links
    don't run;
  * a small guard script that strips unsafe link/src schemes and on* attributes from
    anything the page adds at runtime, and adds rel="noopener noreferrer" to new-tab links
    (covers older browsers that ignore parts of the CSP);
  * lang="en-GB" on <html> when the page has no lang, so screen readers pick the right voice;
  * a page that was wrapped twice (a full document published inside the artifact wrapper)
    is merged into one document.

harden() is idempotent: running it on an already hardened page gives the same page.
"""
import base64, hashlib, re

LANG = "en-GB"
# Inline event handlers the dashboards are allowed to use (Menu Watch hides broken thumbnails).
# Handlers smuggled in through scraped data won't match and are blocked by the CSP.
ALLOWED_HANDLERS = ("this.remove()",)
# Hosts pages may fetch() from at runtime (Weather pulls a live forecast).
CONNECT_HOSTS = ("https://api.open-meteo.com",)
GUARD_ID = "dash-guard"

GUARD = r"""(function(){
var SCHEME=/^\s*([a-z][a-z0-9+.\-]*):/i,HREF={http:1,https:1,mailto:1,tel:1},SRC={http:1,https:1,blob:1};
function okUrl(v,isSrc){var c=String(v).replace(/[\u0000- ]/g,""),m=SCHEME.exec(c);if(!m)return true;var s=m[1].toLowerCase();
if(isSrc&&s==="data")return /^data:image\//i.test(c);return !!(isSrc?SRC:HREF)[s];}
function fixOne(n){if(n.nodeType!==1)return;var a=n.attributes;
for(var j=a.length-1;j>=0;j--){var k=a[j].name.toLowerCase(),v=a[j].value;
if(k.slice(0,2)==="on"){if(!(k==="onerror"&&v==="this.remove()"))n.removeAttribute(a[j].name);}
else if((k==="href"||k==="xlink:href"||k==="action"||k==="formaction")&&!okUrl(v,false))n.removeAttribute(a[j].name);
else if((k==="src"||k==="srcset"||k==="poster")&&!okUrl(v,true))n.removeAttribute(a[j].name);}
if(n.tagName==="A"&&n.getAttribute("target")==="_blank"&&n.getAttribute("rel")!=="noopener noreferrer")n.setAttribute("rel","noopener noreferrer");}
function fixTree(n){if(n.nodeType!==1)return;fixOne(n);var all=n.getElementsByTagName("*");for(var i=0;i<all.length;i++)fixOne(all[i]);}
new MutationObserver(function(ms){for(var i=0;i<ms.length;i++){var m=ms[i];if(m.type==="attributes")fixOne(m.target);
else for(var j=0;j<m.addedNodes.length;j++)fixTree(m.addedNodes[j]);}}).observe(document.documentElement,{childList:true,subtree:true,attributes:true});
})();"""

DOCTYPE = re.compile(r"<!doctype[^>]*>", re.I)
HTML_TAG = re.compile(r"<html\b([^>]*)>", re.I)
HEAD_TAG = re.compile(r"<head\b[^>]*>", re.I)
HEAD_END = re.compile(r"</head\s*>", re.I)
BODY_TAG = re.compile(r"<body\b([^>]*)>", re.I)
CHARSET = re.compile(r"<meta\s+charset\s*=[^>]*>", re.I)
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
OLD_CSP = re.compile(r'<meta http-equiv="Content-Security-Policy"[^>]*>', re.I)
OLD_GUARD = re.compile(r'<script id="' + GUARD_ID + r'">.*?</script>', re.S)
ATTR = re.compile(r"""([^\s=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?""")


def _sha(text):
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


def _attr_names(attrs):
    return {m.group(1).lower() for m in ATTR.finditer(attrs)}


def _merge_attrs(tag_match, extra, text):
    """Add attributes from `extra` that the matched tag doesn't already have."""
    have = _attr_names(tag_match.group(1))
    add = "".join(" " + m.group(0) for m in ATTR.finditer(extra) if m.group(1).lower() not in have)
    if not add:
        return text
    s, e = tag_match.span()
    return text[:s] + text[s:e - 1].rstrip("/").rstrip() + add + ">" + text[e:]


def unwrap(text):
    """Merge a full HTML document that sits inside the artifact's wrapper document."""
    docs = list(DOCTYPE.finditer(text))
    if len(docs) < 2:
        return text
    outer, inner = text[:docs[1].start()], text[docs[1].end():]
    html_attrs = ""
    m = HTML_TAG.match(inner.lstrip())
    if m:
        html_attrs = m.group(1)
        inner = inner.lstrip()[m.end():]
    head = ""
    hs = HEAD_TAG.search(inner)
    if hs and not inner[:hs.start()].strip():
        he = HEAD_END.search(inner, hs.end())
        if he:
            head, inner = inner[hs.end():he.start()], inner[he.end():]
    body_attrs = ""
    b = BODY_TAG.search(inner)
    if b and not inner[:b.start()].strip():
        body_attrs, inner = b.group(1), inner[b.end():]
    inner = re.sub(r"(\s*</body\s*>\s*</html\s*>\s*)+$", "", inner, flags=re.I)
    outer = re.sub(r"(\s*</body\s*>\s*</html\s*>\s*)+$", "", outer, flags=re.I)
    he = HEAD_END.search(outer)
    if he and head:
        outer = outer[:he.start()] + head + outer[he.start():]
    if html_attrs.strip():
        outer = _merge_attrs(HTML_TAG.search(outer), html_attrs, outer)
    if body_attrs.strip():
        outer = _merge_attrs(BODY_TAG.search(outer), body_attrs, outer)
    return outer + inner.rstrip() + "\n</body></html>\n"


def set_lang(text):
    m = HTML_TAG.search(text)
    if not m or "lang" in _attr_names(m.group(1)):
        return text
    return text[:m.start()] + "<html" + m.group(1).rstrip() + f' lang="{LANG}">' + text[m.end():]


def csp(script_hashes):
    scripts = " ".join(f"'sha256-{h}'" for h in script_hashes)
    handlers = " ".join(f"'sha256-{_sha(h)}'" for h in ALLOWED_HANDLERS)
    return ("default-src 'self'; "
            f"script-src {scripts} 'unsafe-hashes' {handlers}; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https:; "
            f"connect-src 'self' {' '.join(CONNECT_HOSTS)}; "
            "media-src 'self' data: https:; "
            "object-src 'none'; base-uri 'none'; form-action 'none'").replace("  ", " ")


def harden(text):
    text = OLD_GUARD.sub("", OLD_CSP.sub("", text))
    text = set_lang(unwrap(text))
    guard = f'<script id="{GUARD_ID}">{GUARD}</script>'
    at = CHARSET.search(text) or HEAD_TAG.search(text)
    pos = at.end() if at else 0
    text = text[:pos] + guard + text[pos:]
    hashes = sorted({_sha(body) for attrs, body in SCRIPT.findall(text) if "src" not in _attr_names(attrs)})
    meta = f'<meta http-equiv="Content-Security-Policy" content="{csp(hashes)}">'
    return text[:pos] + meta + text[pos:]
