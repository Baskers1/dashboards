#!/usr/bin/env python3
"""Decide which dashboards need mirroring, by comparing artifact versions.

Usage: python3 tools/changed.py versions.json              list ids needing a mirror
       python3 tools/changed.py --record versions.json <id> ...   update state.json

WHY THIS EXISTS
The mirror task used to decide this in its own prompt: "take its last-updated
value; changed = value differs from tools/state.json". Both sides of that
comparison were *dates*. The artifact listing reports "updated 2026-10-20" and
state.json stored "2026-10-20", so once a dashboard had been mirrored on a given
day, every later run that day concluded nothing had changed -- correctly, by its
own rule -- and stopped with no commit and no message.

The hourly dashboards update their artifacts about eleven times a day. Only the
first reached a reader. On 20 October 2026 all three weather pages were serving
data five hours older than the artifacts they mirror, and nothing had failed:
the builders reported success, the mirror reported nothing to do, no issue was
opened. A silent success with too coarse a contract.

An artifact's *version* is second-level ("1792500103-e10f"), so comparing
versions sees intra-day change. Versions are opaque here and compared only for
equality: the prefix happens to look like an epoch time, but nothing in this
file parses it, because that format is not documented and a wrong guess would
silently resurrect the same class of bug.

The task collects the versions -- only it can call the Artifact tool -- and
passes them in. This file owns the rule, so the rule can be tested.

VERSIONS FILE
    {"<artifact id>": "<version>", ...}
  built by the task from: Artifact action "list", scope "files", url
  https://claude.ai/artifact/<id>, which reports the version WITHOUT downloading
  the page.

OUTPUT
  Changed ids on stdout, one per line, for the task to pass to sync.py.
  A summary goes to stderr so it cannot be mistaken for the id list.

EXIT STATUS
  0  ids printed, or nothing to mirror
  2  a dashboard's version is missing from the versions file -- cannot tell
     whether it changed. "I could not check" must never look like "nothing
     changed"; that is the failure this file exists to end.
  1  bad usage
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARDS = os.path.join(ROOT, "tools", "dashboards.json")
STATE = os.path.join(ROOT, "tools", "state.json")


def mirrored_ids(path: str = DASHBOARDS) -> list[str]:
    """Dashboard ids this task is responsible for, in file order.

    "local:" entries are published by their own task (the sky pages) and only
    appear on the hub, so they are not ours to mirror.
    """
    with open(path, encoding="utf-8") as fh:
        meta = json.load(fh)
    return [d["id"] for d in meta["dashboards"] if not d["id"].startswith("local:")]


def load_state(path: str = STATE) -> dict[str, str]:
    """Versions already mirrored. A missing file means nothing has been."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def looks_like_a_date(value: str) -> bool:
    """True for the legacy "2026-10-20" values this comparison replaced.

    Used only to explain the first run after the switch, which mirrors
    everything because no date equals any version.
    """
    return len(value) == 10 and value[4] == "-" and value[7] == "-"


def changed(versions: dict[str, str], state: dict[str, str],
            ids: list[str]) -> tuple[list[str], list[str]]:
    """Ids whose version differs from what was last mirrored.

    Returns (changed_ids, unknown_ids). Versions are compared as opaque
    strings; an id absent from state has never been mirrored.
    """
    out, unknown = [], []
    for i in ids:
        if i not in versions:
            unknown.append(i)
        elif state.get(i) != versions[i]:
            out.append(i)
    return out, unknown


def record(versions: dict[str, str], synced: list[str],
           path: str = STATE) -> dict[str, str]:
    """Write state.json for the ids that synced AND passed their checks.

    Only the ids named are updated: one that was skipped or restored keeps its
    old value so the next run retries it. An id with no version is not
    recorded, because recording a version we never saw would mark it mirrored
    for good.
    """
    state = load_state(path)
    for i in synced:
        if i in versions:
            state[i] = versions[i]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return state


def main(argv: list[str]) -> int:
    args = argv[1:]
    recording = False
    if args and args[0] == "--record":
        recording, args = True, args[1:]
    if not args:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 1

    with open(args[0], encoding="utf-8") as fh:
        versions = json.load(fh)
    ids = mirrored_ids()

    if recording:
        synced = args[1:]
        if not synced:
            print("--record needs the ids that synced and passed", file=sys.stderr)
            return 1
        state = record(versions, synced)
        print(f"recorded {len(synced)} of {len(ids)} dashboards; "
              f"state.json now holds {len(state)}", file=sys.stderr)
        return 0

    state = load_state()
    todo, unknown = changed(versions, state, ids)

    legacy = sum(1 for i in ids if looks_like_a_date(state.get(i, "")))
    if legacy:
        print(f"note: {legacy} state entries still hold a date rather than a "
              f"version, so those mirror once on this run", file=sys.stderr)

    for i in todo:
        print(i)

    if unknown:
        print(f"ERROR: no version for {len(unknown)} dashboard(s): "
              f"{', '.join(unknown)}. Cannot tell whether they changed -- "
              f"report this rather than mirroring a partial set.", file=sys.stderr)
        return 2

    print(f"{len(todo)} of {len(ids)} dashboards need mirroring"
          if todo else "nothing to mirror", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
