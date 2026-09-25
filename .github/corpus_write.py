#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys

COMMANDS = ("new", "revise", "relate", "unrelate", "delete")
FLAG = re.compile(r"^[a-z][a-z0-9-]*$")
WORD = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
MINTED = re.compile(r"^\$(\d+)$")
PAYLOAD = "CORPUS_CHANGE"


class Refused(Exception):
    pass


def resolve(value, minted):
    found = MINTED.match(value)
    if not found:
        return value
    at = int(found.group(1))
    if at >= len(minted):
        raise Refused(f"{value}: step {at} has not run")
    if not minted[at]:
        raise Refused(f"{value}: step {at} minted nothing")
    return minted[at]


def argv(step, minted):
    command = step.get("command")
    if command not in COMMANDS:
        raise Refused(f"{command!r}: not one of {', '.join(COMMANDS)}")
    made = ["reqctl", "--json", command]
    args = step.get("args") or []
    if not isinstance(args, list):
        raise Refused(f"{args!r}: args is a list")
    for arg in args:
        if not isinstance(arg, str):
            raise Refused(f"{arg!r}: an argument is a string")
        held = resolve(arg, minted)
        if not WORD.match(held):
            raise Refused(f"{held!r}: not a bare word")
        made.append(held)
    options = step.get("options") or {}
    if not isinstance(options, dict):
        raise Refused(f"{options!r}: options is a mapping")
    for name, value in options.items():
        if not FLAG.match(name):
            raise Refused(f"{name!r}: not a flag reqctl could carry")
        if value is None:
            made.append(f"--{name}")
            continue
        held = value if isinstance(value, list) else [value]
        if not held:
            raise Refused(f"--{name}: given nothing, so it would vanish")
        for each in held:
            if not isinstance(each, str):
                raise Refused(f"--{name}: {each!r} is not a string")
            made.append(f"--{name}={resolve(each, minted)}")
    return made


def run(made, root):
    done = subprocess.run(made, cwd=root, capture_output=True, text=True,
                          check=False)
    if done.returncode:
        said = done.stderr.strip() or done.stdout.strip()
        raise Refused(f"{' '.join(made[1:])}: {said or 'failed silently'}")
    if not done.stdout.strip():
        raise Refused(f"{' '.join(made[1:])}: said nothing")
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as broken:
        raise Refused(f"{' '.join(made[1:])}: said no json: {broken}") from broken


def apply(payload, root, ran=run):
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise Refused("the change names no steps")
    minted = []
    for step in steps:
        if not isinstance(step, dict):
            raise Refused(f"{step!r}: a step is a mapping")
        held = ran(argv(step, minted), root)
        minted.append(held.get("uid", "") if isinstance(held, dict) else "")
    return minted


def main():
    raw = os.environ.get(PAYLOAD)
    if not raw:
        print(f"::error::{PAYLOAD} is empty; nothing was dispatched")
        return 1
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as broken:
        print(f"::error::{PAYLOAD} is not JSON: {broken}")
        return 1
    if not isinstance(payload, dict):
        print(f"::error::{PAYLOAD} is not a mapping")
        return 1
    try:
        minted = apply(payload, os.environ.get("GITHUB_WORKSPACE") or ".")
    except Refused as refused:
        print(f"::error::{refused}")
        return 1
    for uid in minted:
        if uid:
            print(uid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
