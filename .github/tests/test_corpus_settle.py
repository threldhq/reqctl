#!/usr/bin/env python3
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

STEP = "Settle the baseline"
WORKFLOW = Path(".github/workflows/corpus-write.yml")

STAND_IN = """#!/bin/sh
printf '%s\\n' "$*" >> "$LOG"
if [ "$MOOD" = stands ]; then exit 0; fi
if [ "$2" = --generate ]; then
  if [ "$MOOD" = settles ]; then : > "$CUT"; fi
  exit 0
fi
if [ "$MOOD" = settles ] && [ -f "$CUT" ]; then exit 0; fi
exit 1
"""

WANTED = {
    "a change that moved nothing leaves the baseline alone": (
        "stands", 0, ["baseline --check"]),
    "a change that moved what is approved is cut and proved": (
        "settles", 0, ["baseline --check", "baseline --generate",
                       "baseline --check"]),
    "a baseline that will not settle fails the run": (
        "stuck", 1, ["baseline --check", "baseline --generate",
                     "baseline --check"]),
}


def script():
    held = yaml.safe_load(WORKFLOW.read_text())
    steps = held.get("jobs", {}).get("write", {}).get("steps", [])
    for step in steps:
        if isinstance(step, dict) and step.get("name") == STEP:
            return step["run"]
    raise SystemExit(f"::error::{WORKFLOW}: no step named {STEP!r} to test")


def settle(run, mood):
    with tempfile.TemporaryDirectory() as room:
        room = Path(room)
        log = room / "asked"
        log.touch()
        stand_in = room / "reqctl"
        stand_in.write_text(STAND_IN)
        stand_in.chmod(0o755)
        done = subprocess.run(
            ["bash", "-c", run], capture_output=True, text=True, check=False,
            env={"PATH": f"{room}:/usr/bin:/bin", "MOOD": mood,
                 "LOG": str(log), "CUT": str(room / "cut")})
        return done.returncode, [line for line in log.read_text().splitlines()
                                 if line]


def main():
    run = script()
    faults = []
    for name, (mood, code, asked) in WANTED.items():
        got_code, got_asked = settle(run, mood)
        if bool(got_code) != bool(code) or got_asked != asked:
            faults.append(f"{name}: wanted exit {code} having asked {asked}, "
                          f"got exit {got_code} having asked {got_asked}")
    for fault in faults:
        print(f"::error::{fault}")
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
