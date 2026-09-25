#!/usr/bin/env python3
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import taxonomy

SKILLS = Path(".claude/skills")
SET = re.compile(r'--value\s+"\[([^\]]*)\]"')
LOOSE = re.compile(r"--value\b(?!-)\W{0,3}\[")
TYPED = re.compile(r"--value-type\s+`?([a-z_]+)`?")

faults = []


def paragraphs(text):
    held, run = [], []
    for line in text.splitlines():
        if line.strip():
            run.append(line)
        elif run:
            held.append("\n".join(run))
            run = []
    if run:
        held.append("\n".join(run))
    return held


def minted(root, where, name, value_type, members):
    held = root / "requirements" / "params" / f"{name}.yml"
    held.parent.mkdir(parents=True, exist_ok=True)
    held.write_text(
        f"name: {name}\nkind: parameter\nstatus: draft\n"
        f"text: What {where} states.\nvalue_type: {value_type}\nentries:\n"
        + "".join(f"  '{member}': {{}}\n" for member in members))
    return held


def checked(path):
    found_faults = []
    for where, block in enumerate(paragraphs(path.read_text()), 1):
        found = SET.search(block)
        if not found:
            if LOOSE.search(block):
                found_faults.append(
                    f"{path}: paragraph {where} shows a --value example this "
                    "guard cannot parse; use --value \"[a, b]\"")
            continue
        members = [part.strip() for part in found.group(1).split(",")
                   if part.strip()]
        typed = TYPED.search(block)
        if not typed:
            found_faults.append(
                f"{path}: paragraph {where} shows --value \"[{found.group(1)}]\" "
                "and names no --value-type beside it, so what it mints cannot "
                "be checked; state the type with the example")
            continue
        with tempfile.TemporaryDirectory() as room:
            root = Path(room)
            held = minted(root, f"{path.name} paragraph {where}",
                          "shown_set", typed.group(1), members)
            try:
                mint_faults = taxonomy.faults(root)
            except SystemExit as broken:
                found_faults.append(
                    f"{path}: paragraph {where} shows values that do not "
                    f"mint readable YAML -- {broken}")
                mint_faults = []
            for fault in mint_faults:
                found_faults.append(
                    f"{path}: paragraph {where} mints what the corpus refuses "
                    f"-- {fault}")
            held.unlink()
    return found_faults


def probed(text):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "SKILL.md"
        spot.write_text(text)
        return checked(spot)


UNRECOGNISED = "shown as `--value '[10, 20]'` with `--value-type count`\n"
if not any("cannot parse" in one for one in probed(UNRECOGNISED)):
    faults.append("a --value example in an unrecognised format is skipped, "
                  "not reported")

UNQUOTABLE = ("shown as `--value \"[can't stop, wont stop]\"` with "
             "`--value-type text`\n")
if not any("do not mint readable YAML" in one for one in probed(UNQUOTABLE)):
    faults.append("a SystemExit from taxonomy.faults crashes this guard "
                  "rather than becoming a fault")

found = sorted(SKILLS.rglob("SKILL.md"))
if not found:
    print(f"::error::{SKILLS}: no SKILL.md to check")
    sys.exit(1)
for path in found:
    faults += checked(path)

for fault in faults:
    print(f"::error::{fault}")
sys.exit(1 if faults else 0)
