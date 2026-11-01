"""Self-check for check_hardened.py: python3 tools/test_check_hardened.py"""
import importlib.util, os

d = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, name + ".py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


c = load("check_hardened")

plain = ('<!doctype html><html><head><meta charset="utf-8"><title>T</title>'
         '<script>var A=1;</script></head><body><p>hi</p></body></html>')

why = c.reasons(plain)
assert why, "an unhardened page must be refused"
assert any("Content-Security-Policy" in w for w in why), why
assert any("dash-guard" in w for w in why), why

good = c.page_text(plain)
assert c.reasons(good) == [], c.reasons(good)
assert c.page_text(good) == good, "page_text must be idempotent, or every commit would be refused"

# A page that is hardened but still carries a rewritable link is not publishable either,
# and must not be waved through just because the CSP and guard are present.
import re
known = c.page_text.__globals__["M"]["dashboards"][0]
linky = good.replace("<p>hi</p>", f'<p><a href="https://claude.ai/artifact/{known["id"]}">x</a></p>')
assert re.search(r"Content-Security-Policy", linky) and 'id="dash-guard"' in linky
why = c.reasons(linky)
assert why == ["sync.py would still rewrite it (links, redaction or hardening)"], why

print("ok")
