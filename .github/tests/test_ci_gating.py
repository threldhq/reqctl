#!/usr/bin/env python3
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

STEP = "What this change touches"
WORKFLOW = Path(".github/workflows/ci.yml")
MARKED = re.compile(r"^\s*mark (\w+) ", re.M)

WANTED = {
    "a requirement alone": (
        ["requirements/reqs/REQ-11500378.yml", "requirements/baseline.yml"],
        {"deps": "false", "corpus": "true"}),
    "a schema": (
        ["requirements/schemas/requirement.schema.yaml"],
        {"deps": "false", "corpus": "true"}),
    "reqctl itself": (
        ["reqctl/reqctl/write.py"],
        {"deps": "false", "corpus": "false"}),
    "a python lockfile": (
        ["reqctl/requirements-lock.txt"],
        {"deps": "true", "corpus": "false"}),
    "the workflow itself": (
        [".github/workflows/ci.yml"],
        {"deps": "false", "corpus": "false"}),
    "nothing the rules name": (
        ["README.md"],
        {"deps": "false", "corpus": "false"}),
}

def script():
    held = yaml.safe_load(WORKFLOW.read_text())
    steps = held.get("jobs", {}).get("check", {}).get("steps", [])
    for step in steps:
        if isinstance(step, dict) and step.get("name") == STEP:
            rest = json.dumps([other for other in steps if other is not step])
            return step["run"], rest
    raise SystemExit(f"::error::{WORKFLOW}: no step named {STEP!r} to test")


def unread(run, rest):
    return [name for name in MARKED.findall(run)
            if not re.search(rf"steps\.touched\.outputs\.{name}\b", rest)]


def decide(run, changed):
    with tempfile.TemporaryDirectory() as room:
        room = Path(room)
        out = room / "decided"
        out.touch()
        stand_in = room / "git"
        stand_in.write_text("#!/bin/sh\nprintf '%s\\n' "
                            + " ".join(f"'{path}'" for path in changed) + "\n")
        stand_in.chmod(0o755)
        done = subprocess.run(
            ["bash", "-c", run], capture_output=True, text=True, check=False,
            env={"PATH": f"{room}:/usr/bin:/bin", "BASE": "main",
                 "GITHUB_EVENT_NAME": "pull_request", "GITHUB_OUTPUT": str(out)})
        if done.returncode:
            return f"exited {done.returncode}: {done.stderr.strip()}"
        return dict(line.split("=", 1)
                    for line in out.read_text().splitlines() if line)


def main():
    run, rest = script()
    faults = [f"{STEP}: marks {name}, which no step reads"
              for name in unread(run, rest)]
    for name, (changed, wanted) in WANTED.items():
        held = decide(run, changed)
        if held != wanted:
            faults.append(f"{name}: wanted {wanted}, got {held}")
    for fault in faults:
        print(f"::error::{fault}")
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
