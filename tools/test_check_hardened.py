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

# --- broken link values in page data are refused even on a fully hardened page (LINKS.md 3.2)
for bad_value in ('https://x.org/{{ links.menu }}', 'https://x.org/e?id=undefined',
                  'https://cal.example/?dates=NaN', 'https://x.org/${a.a?'):
    pg = c.page_text(plain.replace("var A=1;", 'var D={"url":"%s"};' % bad_value))
    assert any("broken link" in w for w in c.reasons(pg)), (bad_value, c.reasons(pg))
for ok_value in ('https://x.org/events/1', '', '/_blob/bd6b59', 'https://x.org/undefined-stories'):
    pg = c.page_text(plain.replace("var A=1;", 'var D={"url":"%s","Menu":"Bwydlen"};' % ok_value))
    assert c.reasons(pg) == [], (ok_value, c.reasons(pg))
# page code is not data: a template literal URL in JS must not trip the check
pg = c.page_text(plain.replace("var A=1;", 'var f=a=>`https://t.example/${a}`;'))
assert c.reasons(pg) == [], c.reasons(pg)
print("broken data links ok")
