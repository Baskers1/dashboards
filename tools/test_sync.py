"""Self-check for sync.py: python3 tools/test_sync.py"""
import importlib.util, os

spec = importlib.util.spec_from_file_location("sync", os.path.join(os.path.dirname(__file__), "sync.py"))
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

known = s.M["dashboards"][0]
out = s.rewrite_links(f'<a href="https://claude.ai/artifact/{known["id"]}">x</a> https://claude.ai/artifact/ZZZZZZZZZZZZZZZZZZZZZZ')
assert s.BASE_URL + known["area"] + "/" + known["slug"] + "/" in out, out
assert "https://claude.ai/artifact/ZZZZZZZZZZZZZZZZZZZZZZ" in out, "unknown links must be left alone"
assert len({(d["area"], d["slug"]) for d in s.M["dashboards"]}) == len(s.M["dashboards"]), "duplicate folder"
assert len({d["id"] for d in s.M["dashboards"]}) == len(s.M["dashboards"]), "duplicate id"

# harden.py
import base64, hashlib, re
from harden import harden, unwrap, GUARD_ID

def sha(t):
    return "'sha256-" + base64.b64encode(hashlib.sha256(t.encode()).digest()).decode() + "'"

wrapper = '<!doctype html><html><head><meta charset=utf8><style>x{}</style></head><body>\n'
page = wrapper + '<title>T</title><script>var A=1;</script><p>hi</p></body></html>'
out = harden(page)
policy = re.search(r'Content-Security-Policy" content="([^"]+)"', out).group(1)
assert sha("var A=1;") in policy, "page's own script must be allowed by hash"
assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0], "no unsafe-inline for scripts"
assert sha("this.remove()") in policy and "'unsafe-hashes'" in policy, "Menu Watch thumbnail handler allowed"
assert "object-src 'none'" in policy and "base-uri 'none'" in policy
assert out.index("Content-Security-Policy") < out.index("<script"), "CSP must come before every script"
assert out.index("<meta charset") < out.index("Content-Security-Policy"), "charset stays first"
assert '<html lang="en-GB">' in out, out[:200]
assert f'<script id="{GUARD_ID}">' in out
assert harden(out) == out, "harden must be idempotent"
assert '<html lang="cy">' in harden(wrapper.replace("<html>", '<html lang="cy">') + "</body></html>"), "keep an existing lang"

# A link smuggled in by scraped data is not trusted: its handler isn't hashed into the policy.
evil = page.replace("<p>hi</p>", '<a href="x" onmouseover="steal()">x</a>')
assert sha("steal()") not in harden(evil)

# Double-wrapped page: one doctype, head content moved into head, body attributes kept.
double = (wrapper + '<!doctype html>\n<html lang="en">\n<head><style>y{}</style>'
          '<script>var B=2;</script></head>\n<body class="big">\n<p>inner</p>\n</body></html>\n\n</body></html>')
u = unwrap(double)
assert len(re.findall(r"(?i)<!doctype", u)) == 1 and len(re.findall(r"(?i)<html", u)) == 1, u
assert len(re.findall(r"(?i)<body", u)) == 1 and len(re.findall(r"(?i)</body>", u)) == 1, u
assert u.index("y{}") < u.index("</head>") and u.index("var B=2;") < u.index("</head>")
assert '<body class="big">' in u and '<html lang="en">' in u and "<p>inner</p>" in u
assert sha("var B=2;") in harden(double)
assert unwrap(page) == page, "single documents are left alone"
print("ok")
