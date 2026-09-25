#!/usr/bin/env python3
import re
import sys
from pathlib import Path

from reqctl import write

PORTAL = Path("reqctl/reqctl/portal.html")
KINDS = ("requirement", "term", "parameter", "data")
SPELT = {"alias": "aliases", "value-type": "value_type"}
ONLY = {"criteria": ("requirement",), "default": ("parameter", "data"),
        "entry": ("data",), "text": ("requirement", "parameter", "data")}


def block(text, name):
    start = text.index(f"const {name} = {{")
    depth, spot = 0, text.index("{", start)
    index = spot
    while True:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[spot:index + 1]
        index += 1


def per_kind(body, first):
    held = {}
    for kind in KINDS:
        found = re.search(
            rf"\b{kind}:\s*\[(.*?)\],?\s*(?=\n\s*(?:{'|'.join(KINDS)})\b|\}})",
            body, re.S)
        if found:
            held[kind] = re.findall(
                r'\["([a-z-]+)"' if first else r'"([a-z-]+)"', found.group(1))
    return held


def named(field):
    held = "criteria" if field == "criterion" else field
    return SPELT.get(held, held.replace("-", "_"))


def accepts(kind, field):
    if field in ONLY:
        return kind in ONLY[field]
    return field in write.FIELDS[kind]


def faults(text):
    found = []
    shape = per_kind(block(text, "SHAPE"), True)
    needed = per_kind(block(text, "NEEDED"), False)
    clears = dict(re.findall(r'([\w-]+):\s*"(no-[\w-]+)"',
                             block(text, "CLEARS")))
    for kind in KINDS:
        if kind not in shape:
            found.append(f"{PORTAL}: SHAPE names no {kind}")
            continue
        for field in shape[kind]:
            if not accepts(kind, named(field)):
                found.append(
                    f"{PORTAL}: SHAPE offers --{field} on a {kind}, which "
                    f"reqctl refuses; the form would compose a change the "
                    f"corpus rejects")
        if needed.get(kind) is None:
            found.append(f"{PORTAL}: NEEDED names no {kind}")
            continue
        wanted = {named(field) for field in needed[kind]}
        if wanted != set(write.REQUIRED[kind]):
            found.append(
                f"{PORTAL}: NEEDED makes {sorted(wanted)} required for a "
                f"{kind}; reqctl requires {sorted(write.REQUIRED[kind])}")
        for field in write.REQUIRED[kind]:
            if field not in {named(offered) for offered in shape[kind]}:
                found.append(f"{PORTAL}: SHAPE offers no --{field} on a "
                             f"{kind}, which reqctl needs to create one")
    flags = {f"--{flag}" for flag in clears.values()}
    empties = {flag for flag, _ in write.CLEARABLE.values()} | {"--no-criteria"}
    for spare in sorted(flags - empties):
        found.append(f"{PORTAL}: CLEARS offers {spare}, which reqctl has no "
                     "flag for; the box would empty into a refusal")
    for missing in sorted(empties - flags):
        found.append(f"{PORTAL}: CLEARS offers no {missing}, so a field reqctl "
                     "can empty cannot be emptied from the page")
    return found


def main():
    try:
        text = PORTAL.read_text()
    except OSError as broken:
        print(f"::error::cannot read {PORTAL}: {broken}")
        return 1
    found = faults(text)
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
