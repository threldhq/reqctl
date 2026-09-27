#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import unicodedata

COMMANDS = ("new", "revise", "relate", "unrelate", "delete")
MINTED = re.compile(r"\$([0-9]+)")
PAYLOAD = "CORPUS_CHANGE"
BODY = ("Dispatched from the requirements portal.\n\n"
        "Every item here was written by `reqctl`; nothing hand-edited the "
        "corpus.\n\nSteps dispatched:\n\n```json\n{}\n```\n")


class Refused(Exception):
    pass


def flag(name):
    return name[:1].isalpha() and all(
        unicodedata.category(each) == "Ll" or each.isdecimal() or each == "-"
        for each in name)


def bare(word):
    return word[:1].isalpha() and all(
        each.isalpha() or each.isdecimal() or each in "-_" for each in word)


def resolve(value, minted):
    # @req+ REQ-81313171@3CV_M8XsRLpd 3dpv3v
    found = MINTED.fullmatch(value)
    if not found:
        return value
    at = int(found.group(1))
    # @req+ REQ-21669490@tWohKLmNox8d rkzzkl
    if at >= len(minted):
        raise Refused(f"{value}: step {at} has not run")
    if not minted[at]:
        raise Refused(f"{value}: step {at} minted nothing")
    # @req- rkzzkl
    return minted[at]
    # @req- 3dpv3v


def shaped(payload):
    # @req+ REQ-48601729@IX7_y_xH1FkV 7ycfsi
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise Refused("the change names no steps")
    for step in steps:
        if not isinstance(step, dict):
            raise Refused(f"{step!r}: a step is a mapping")
        args = step.get("args", [])
        if not isinstance(args, list):
            raise Refused(f"{args!r}: args is a list")
        for arg in args:
            if not isinstance(arg, str):
                raise Refused(f"{arg!r}: an argument is a string")
        options = step.get("options", {})
        if not isinstance(options, dict):
            raise Refused(f"{options!r}: options is a mapping")
        for name, value in options.items():
            if value is None:
                continue
            held = value if isinstance(value, list) else [value]
            if not held:
                raise Refused(f"--{name}: given nothing, so it would vanish")
            for each in held:
                if not isinstance(each, str):
                    raise Refused(f"--{name}: {each!r} is not a string")
    return steps
    # @req- 7ycfsi


def argv(step, minted):
    # @req+ REQ-25363659@x2KAEtIScy4m 43rpbl
    command = step.get("command")
    if command not in COMMANDS:
        raise Refused(f"{command!r}: not one of {', '.join(COMMANDS)}")
    made = ["reqctl", "--json", command]
    # @req- 43rpbl
    for arg in step.get("args", []):
        # @req+ REQ-72545168@yUfWE3RsMOFD dwzirn
        held = resolve(arg, minted)
        if not bare(held):
            raise Refused(f"{held!r}: not a bare word")
        # @req- dwzirn
        made.append(held)
    for name, value in step.get("options", {}).items():
        # @req> REQ-99251609@o1kDTOHxcWxW e6n66c
        if not flag(name):
            raise Refused(f"{name!r}: not a flag reqctl could carry")
        if value is None:
            made.append(f"--{name}")
            continue
        for each in value if isinstance(value, list) else [value]:
            # @req> REQ-52483245@AHTmVTTc0QE_ eburqo
            made.append(f"--{name}={resolve(each, minted)}")
    return made


def ran(*made, check=True):
    done = subprocess.run(made, capture_output=True, text=True, check=False)
    if check and done.returncode:
        said = done.stderr.strip() or done.stdout.strip()
        raise Refused(f"{' '.join(made)}: {said or 'failed silently'}")
    return done


def run(made):
    # @req+ REQ-44900066@qaXVLJO6m5rP n6gx3k
    said = ran(*made).stdout.strip()
    if not said:
        raise Refused(f"{' '.join(made)}: said nothing")
    try:
        return json.loads(said)
    except json.JSONDecodeError as broken:
        raise Refused(f"{' '.join(made)}: said no json: {broken}") from broken
    # @req- n6gx3k


def apply(payload):
    minted = []
    for step in shaped(payload):
        held = run(argv(step, minted))
        minted.append(held.get("uid", "") if isinstance(held, dict) else "")
    return minted


def proposed(raw, env):
    ran("reqctl", "validate")
    slug, title, trunk = env["APP_SLUG"], env["TITLE"], env["DEFAULT_BRANCH"]
    bot = f"{slug}[bot]"
    held = ran("gh", "api", f"/users/{slug}%5Bbot%5D", "--jq", ".id").stdout
    ran("git", "config", "user.name", bot)
    ran("git", "config", "user.email",
        f"{held.strip()}+{bot}@users.noreply.github.com")
    branch = f"corpus/{env['GITHUB_RUN_ID']}"
    ran("git", "checkout", "-b", branch)
    ran("git", "add", "-A")
    if not ran("git", "diff", "--cached", "--name-only").stdout.strip():
        raise Refused("the change altered nothing")
    ran("git", "commit", "-m", title)
    # @req> REQ-64308807@X_7rJjBIYt8C pgupaf
    if ran("reqctl", "baseline", "--check", check=False).returncode:
        ran("git", "remote", "set-head", "origin", trunk)
        # @req+ REQ-44733670@C8Ng3PpXQx7j 66kdp3
        ran("reqctl", "baseline", "--generate")
        ran("reqctl", "baseline", "--check")
        # @req- 66kdp3
        ran("git", "add", "-A")
        ran("git", "commit", "-m", f"{title}: cut the baseline")
    ran("git", "push", "-u", "origin", branch)
    return ran("gh", "pr", "create", "--base", trunk, "--head", branch,
               "--title", title, "--body", BODY.format(raw)).stdout.strip()


def main():
    raw = os.environ.get(PAYLOAD)
    # @req+ REQ-48601729@IX7_y_xH1FkV oxn6if
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
    # @req- oxn6if
    try:
        # @req+ REQ-57492239@hvqdee0u96s6 jvrbb3
        minted = apply(payload)
        opened = proposed(raw, os.environ)
        # @req- jvrbb3
    except Refused as refused:
        print(f"::error::{refused}")
        return 1
    for uid in minted:
        if uid:
            print(uid)
    print(opened)
    return 0


if __name__ == "__main__":
    sys.exit(main())
