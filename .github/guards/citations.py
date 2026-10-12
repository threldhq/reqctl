#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys


def read(*argv):
    # @req+ GUARD-87780053@FAmfCmKiJnLk t2bzx7
    try:
        found = subprocess.run(["reqctl", "--json", *argv],
                               capture_output=True, text=True, check=False)
    except FileNotFoundError as missing:
        raise SystemExit(f"cannot run reqctl: {missing}")
    try:
        return json.loads(found.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"cannot read {argv[0]}: "
                         f"{found.stderr.strip() or found.stdout.strip()}")
    # @req- t2bzx7


def touched(base):
    held = read("compare", "--base", f"origin/{base}")
    if "citations" not in held:
        raise SystemExit(f"cannot compare against origin/{base}: "
                         f"{held.get('error', 'malformed compare output')}")
    # @req> REQ-57367860@Ru8k-xWkVYxO qenuaa
    return {row["id"] for row in held["citations"] if row["state"] != ["deleted"]}


def stale(data):
    named = {}
    for citation in data["citations"]:
        named.setdefault((citation["address"], citation["path"],
                          citation["pinned"]), []).append(citation["id"])
    rows = []
    for row in data["stale"]:
        ids = named.get((row["uid"], row["path"], row["pinned"]))
        identity = ids.pop() if ids else None
        remedy = (f"reqctl repin {identity}" if identity
                  else f"reqctl tag {row['path']} --req {row['uid']}")
        rows.append((identity, (f"{row['uid']}: {row['path']} pinned "
                                f"@{row['pinned']}, now @{row['held']} -- read "
                                f"it against {row['uid']}, then {remedy}")))
    return rows


def faults(data, base):
    if "problems" not in data or "stale" not in data:
        raise SystemExit(
            f"cannot read trace: {data.get('error', 'malformed trace output')}")
    found = list(data["problems"])
    rows = stale(data)
    # @req> REQ-88079673@EiXeHoq_wF_z mle2ez
    if not base or not rows:
        return found + [text for _, text in rows], []
    # @req+ REQ-57367860@Ru8k-xWkVYxO afmuwn
    changed = touched(base)
    problems = [text for identity, text in rows if identity in changed]
    # @req- afmuwn
    # @req> REQ-53246456@QyWuIwzUUElO r65zaf
    behind = [text for identity, text in rows if identity not in changed]
    return found + problems, behind


def main():
    # @req+ GUARD-12397751@ZZpZOVKQVB3u 7skmd6
    found, behind = faults(read("trace"), os.environ.get("BASE_REF", ""))
    # @req> REQ-53246456@QyWuIwzUUElO howxzn
    for row in behind:
        print(f"::notice::behind the corpus: {row}, here or in the pull "
              "request that carries the code")
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0
    # @req- 7skmd6


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    sys.exit(main())
