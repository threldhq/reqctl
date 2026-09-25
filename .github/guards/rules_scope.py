#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

import yaml

RULES = Path(".claude/rules")
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
UNSCOPED = "names no paths"


def tracked():
    found = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=False)
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    return sorted({path for path in found.stdout.split("\0") if path})


def matcher(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern[i:i + 3] == "**/":
            out.append(r"(?:[^/]+/)*")
            i += 3
        elif pattern[i:i + 2] == "**":
            out.append(r".*")
            i += 2
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append(r"[^/]")
            i += 1
        elif pattern[i] == "[":
            end = pattern.find("]", i + 2)
            if end == -1:
                raise re.error("unclosed bracket expression")
            body = pattern[i + 1:end]
            held = f"^{body[1:]}" if body.startswith("!") else body
            out.append(f"[{held}]")
            i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def faults(text, where, files):
    front = FRONT.match(text)
    if not front:
        return [f"{where}: {UNSCOPED}"]
    try:
        held = yaml.safe_load(front.group(1))
    except yaml.YAMLError as broken:
        return [f"{where}: frontmatter is not YAML: {broken}"]
    if not isinstance(held, dict):
        return [f"{where}: frontmatter is not a mapping"]
    patterns = held.get("paths")
    if patterns is None:
        return [f"{where}: {UNSCOPED}"]
    if not isinstance(patterns, list) or not patterns:
        return [f"{where}: paths is {patterns!r}, not a list of globs"]
    found, reached = [], set()
    for pattern in patterns:
        if not isinstance(pattern, str):
            found.append(f"{where}: path {pattern!r} is not a string")
            continue
        if "{" in pattern or "}" in pattern:
            found.append(f"{where}: {pattern!r} expands braces; write each "
                         "pattern out")
            continue
        try:
            reads = matcher(pattern)
        except re.error as broken:
            found.append(f"{where}: {pattern!r} is not a glob: {broken}")
            continue
        hit = {path for path in files if reads.match(path)}
        if not hit:
            found.append(f"{where}: {pattern!r} matches no file in the tree")
        reached |= hit
    if files and reached == set(files):
        found.append(f"{where}: matches every file in the tree")
    return found


def main():
    if not RULES.is_dir():
        found = [f"{RULES}: does not exist"]
    else:
        files = tracked()
        found = []
        for path in sorted(RULES.rglob("*.md")):
            where = str(path)
            try:
                text = path.read_text()
            except OSError as broken:
                found.append(f"cannot read {where}: {broken}")
                continue
            found.extend(faults(text, where, files))
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
