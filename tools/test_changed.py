"""Self-check for changed.py: python3 tools/test_changed.py

The first case is the bug this file exists to prevent: same date, different
version, must mirror. On 20 October 2026 the date comparison said "unchanged"
and three weather pages served data five hours stale while every step reported
success.
"""
import importlib.util, json, os, tempfile

_here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("changed", os.path.join(_here, "changed.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

TAYSIDE = "MVLXSXWcDGro4CG3zdWYtW"
EASTKENT = "FEHxzoKP7H3Xnn9oQD7w3d"
WESTHERTS = "85RFURpU8jkhfq2rUHGzSq"

# --- the regression: a second change on the same day must be seen -----------
# Real values. The artifact was at version 1792500103-e10f (12:41 UTC) while
# state.json held "2026-10-20" from the 07:53 mirror.
todo, unknown = c.changed({TAYSIDE: "1792500103-e10f"}, {TAYSIDE: "2026-10-20"}, [TAYSIDE])
assert todo == [TAYSIDE], "a date in state must never match a version"
assert unknown == []

todo, _ = c.changed({TAYSIDE: "1792500103-e10f"}, {TAYSIDE: "1792498258-33ae"}, [TAYSIDE])
assert todo == [TAYSIDE], "a newer version on the same day must mirror"

# Same version: genuinely nothing to do.
todo, _ = c.changed({TAYSIDE: "1792500103-e10f"}, {TAYSIDE: "1792500103-e10f"}, [TAYSIDE])
assert todo == [], "an unchanged version must not mirror"

# Never mirrored before.
todo, _ = c.changed({TAYSIDE: "1792500103-e10f"}, {}, [TAYSIDE])
assert todo == [TAYSIDE], "an id absent from state has never been mirrored"

# --- versions are opaque ----------------------------------------------------
# A version that is not epoch-shaped must still compare correctly, because
# nothing may depend on the token's internal format.
todo, _ = c.changed({TAYSIDE: "v2-abc"}, {TAYSIDE: "v1-abc"}, [TAYSIDE])
assert todo == [TAYSIDE], "versions must be compared as opaque strings"
todo, _ = c.changed({TAYSIDE: "v1-abc"}, {TAYSIDE: "v1-abc"}, [TAYSIDE])
assert todo == [], "equal opaque versions must not mirror"

# A LOWER version is still a change: the rule is difference, not ordering, so
# a rollback or a re-publish of older content still reaches the page.
todo, _ = c.changed({TAYSIDE: "1792400000-aaaa"}, {TAYSIDE: "1792500103-e10f"}, [TAYSIDE])
assert todo == [TAYSIDE], "any difference is a change, including a rollback"

# The WHOLE version must be compared, not a prefix of it. Added after a
# sabotage run: truncating the comparison to ten characters -- the same
# truncation that made the old date comparison blind -- passed every other case
# here, because their epoch prefixes already differ. These two differ only in
# the suffix, so they pin the full-string comparison.
todo, _ = c.changed({TAYSIDE: "1792500103-e10f"}, {TAYSIDE: "1792500103-f300"}, [TAYSIDE])
assert todo == [TAYSIDE], "versions sharing a prefix but differing later must mirror"
todo, _ = c.changed({TAYSIDE: "2026-10-20-aaaa"}, {TAYSIDE: "2026-10-20-bbbb"}, [TAYSIDE])
assert todo == [TAYSIDE], "a date-like prefix must not swallow the rest of the version"

# --- "cannot tell" must not read as "nothing changed" -----------------------
todo, unknown = c.changed({TAYSIDE: "1792500103-e10f"}, {}, [TAYSIDE, EASTKENT])
assert todo == [TAYSIDE]
assert unknown == [EASTKENT], "a missing version must be reported, not assumed unchanged"

# --- state writing ----------------------------------------------------------
versions = {TAYSIDE: "1792500103-e10f", EASTKENT: "1792498258-33ae",
            WESTHERTS: "1792499222-f300"}
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "state.json")

    # Only the ids that synced are recorded; a skipped one keeps its old value
    # so the next run retries it.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({WESTHERTS: "2026-10-19"}, fh)
    state = c.record(versions, [TAYSIDE, EASTKENT], path)
    assert state[TAYSIDE] == versions[TAYSIDE]
    assert state[EASTKENT] == versions[EASTKENT]
    assert state[WESTHERTS] == "2026-10-19", "a dashboard left out must keep its old value"

    # An id with no version is not recorded: marking it mirrored on a version
    # we never saw would strand it permanently.
    state = c.record({}, ["ZZZZZZZZZZZZZZZZZZZZZZ"], path)
    assert "ZZZZZZZZZZZZZZZZZZZZZZ" not in state, "never record a version we did not see"

    # Round-trips as sorted JSON, so the committed diff stays readable.
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert text.endswith("\n")
    assert json.loads(text) == state
    keys = list(json.loads(text).keys())
    assert keys == sorted(keys), "state.json keys must be sorted"

    # A missing state file means nothing has been mirrored, not a crash.
    assert c.load_state(os.path.join(d, "absent.json")) == {}

# --- legacy detection -------------------------------------------------------
assert c.looks_like_a_date("2026-10-20")
assert not c.looks_like_a_date("1792500103-e10f")
assert not c.looks_like_a_date("")

# --- the real dashboards.json ----------------------------------------------
ids = c.mirrored_ids()
assert ids, "dashboards.json must list some dashboards"
assert not any(i.startswith("local:") for i in ids), "local: entries are not ours to mirror"
assert len(ids) == len(set(ids)), "duplicate id in dashboards.json"
# Every id we are responsible for is a real artifact id, not a path or a name.
assert all(len(i) == 22 and i.isalnum() for i in ids), f"unexpected id shape: {ids}"

print(f"changed.py: all checks passed ({len(ids)} dashboards mirrored by this task)")
