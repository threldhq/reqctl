#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

SETTLING = "SETTLING"


def traced():
    try:
        found = subprocess.run(["reqctl", "--json", "trace"],
                               capture_output=True, text=True, check=False)
    except FileNotFoundError as missing:
        raise SystemExit(f"cannot run reqctl: {missing}")
    try:
        return json.loads(found.stdout)
    except json.JSONDecodeError:
        raise SystemExit("cannot read trace: "
                         f"{found.stderr.strip() or found.stdout.strip()}")


def _stale(data):
    return [f"{row['uid']}: {row['path']} pinned @{row['pinned']}, "
            f"now @{row['held']}" for row in data["stale"]]


def faults(data, settling):
    if "problems" not in data or "stale" not in data:
        raise SystemExit(
            f"cannot read trace: {data.get('error', 'malformed trace output')}")
    found = list(data["problems"])
    return found if settling else found + _stale(data)


def deferred(data, settling):
    return _stale(data) if settling else []


def main():
    data = traced()
    settling = os.environ.get(SETTLING) == "true"
    found = faults(data, settling)
    for row in deferred(data, settling):
        print(f"::notice::{row} -- re-pin it here, or in the pull request "
              "that carries the code")
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    sys.exit(main())
