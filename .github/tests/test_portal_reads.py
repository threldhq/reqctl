#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

PORTAL = Path("reqctl/reqctl/portal.html")
ITEM = re.compile(r"\bitem\.([A-Za-z_][A-Za-z0-9_]*)")
ROWS = re.compile(r"\(item\.([A-Za-z_][A-Za-z0-9_]*) \?\? \[\]\)\.map\("
                  r"\((\w+)\) =>")


def reqctl(*args):
    found = subprocess.run(["reqctl", "--json", *args],
                           capture_output=True, text=True, check=False)
    if found.returncode:
        raise SystemExit(f"reqctl {' '.join(args)}: "
                         f"{found.stderr.strip() or found.stdout.strip()}")
    return json.loads(found.stdout)


def rows_read(text):
    held = {}
    for found in ROWS.finditer(text):
        field, name = found.group(1), found.group(2)
        rest = text[found.end():]
        reads = re.compile(rf"\b{re.escape(name)}\.([A-Za-z_][A-Za-z0-9_]*)")
        held.setdefault(field, set()).update(
            hit.group(1) for hit in reads.finditer(rest[:rest.index(".join(")])
        )
    return held


def emitted(items):
    top, nested = set(), {}
    for item in items:
        top |= set(item)
        for field, value in item.items():
            if isinstance(value, list):
                for member in value:
                    if isinstance(member, dict):
                        nested.setdefault(field, set()).update(member)
    return top, nested


def faults(text, items):
    top, nested = emitted(items)
    found = [f"portal.html reads item.{field}, which reqctl context emits "
             "for no item"
             for field in sorted(ITEM.findall(text)) if field not in top]
    for field, names in sorted(rows_read(text).items()):
        if field not in top:
            continue
        for name in sorted(names - nested.get(field, set())):
            found.append(f"portal.html reads {name} off a row of "
                         f"item.{field}, which reqctl context never puts there")
    return found


def main():
    text = PORTAL.read_text()
    uids = list(reqctl("export", "--all"))
    if not uids:
        raise SystemExit("the corpus holds nothing to read the portal against")
    found = sorted(set(faults(text, reqctl("context", *uids))))
    for fault in found:
        print(f"::error file={PORTAL}::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
