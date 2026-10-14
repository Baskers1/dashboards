#!/usr/bin/env python3
"""Self-tests for tools/check_contacts.py. Run: python3 tools/test_check_contacts.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_contacts import hits  # noqa: E402

# Built at runtime so this file never holds a literal that the checker itself would flag.
REAL_PHONE = "07" + "811 223 344"
REAL_EMAIL = "jo.bloggs" + "@gmail.com"

text = f"line one\ncall {REAL_PHONE}\nmail {REAL_EMAIL}\n"
assert [n for n, _ in hits(text)] == [2, 3], list(hits(text))

# fictional values pass
assert not list(hits("ring 07700 900123 or 07700900456, or example.club@hotmail.co.uk"))
# organisational addresses aren't personal-provider ones
assert not list(hits("help@example.gov.uk, info@thanet.gov.uk"))
# digits inside an embedded image are ignored
assert not list(hits("data:image/png;base64,AAAA" + REAL_PHONE.replace(" ", "") + "AAAA"))

print("check_contacts: all tests passed")
