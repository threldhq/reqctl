#!/usr/bin/env python3
import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

GOVERNED = "requirements/"
SUFFIXES = "py|yml|yaml|json|mjs|html|md|sh|in|txt"
PATHISH = re.compile(rf"(?<![\w-])\.?[\w./<>-]*[\w>-]+\.(?:{SUFFIXES})(?![\w-])")
PLACEHOLDER = re.compile(r"NN|FILE|DIR|MEMBER|PATH|<[^>]*>")
QUOTED_FLAG = re.compile(r"`(--[a-z][\w-]*)`")
SKILL_DIR = "${CLAUDE_SKILL_DIR}"
BARE_FLAG = re.compile(r"--[a-z][\w-]*")


def tracked(*globs):
    found = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         *globs],
        capture_output=True, text=True, check=False)
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    return sorted({path for path in found.stdout.split("\0") if path})


def listed(*globs):
    return [path for path in tracked(*globs)
            if not path.startswith(GOVERNED)]


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as broken:
        raise SystemExit(f"cannot read {path}: {broken}") from broken


def parsed(path):
    try:
        return ast.parse(read(path), filename=str(path))
    except SyntaxError as broken:
        raise SystemExit(f"cannot read {path}: {broken}") from broken


def flags_defined():
    held = set()
    for path in listed("*.py"):
        for node in ast.walk(parsed(path)):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", None) != "add_argument":
                continue
            for given in node.args:
                if isinstance(given, ast.Constant) \
                   and str(given.value).startswith("--"):
                    held.add(given.value)
    return held


def paths_named(text, holder, known):
    faults = []
    if Path(holder).name == "SKILL.md":
        text = text.replace(SKILL_DIR, str(Path(holder).parent))
    for number, line in enumerate(text.splitlines(), 1):
        for found in PATHISH.finditer(line):
            named = found.group(0)
            if PLACEHOLDER.search(named) or "/" not in named:
                continue
            if named.startswith("//") and line[:found.start()].endswith(":"):
                continue
            bare = named[2:] if named.startswith("./") else named
            if bare in known or str(Path(holder).parent / bare) in known:
                continue
            faults.append((holder, number,
                           f"{named} names no file this repository tracks"))
    return faults


def flags_named(text, holder, defined):
    faults = []
    for number, line in enumerate(text.splitlines(), 1):
        for found in QUOTED_FLAG.finditer(line):
            if found.group(1) not in defined:
                faults.append((holder, number,
                               f"{found.group(1)} is named here but no parser "
                               "in this repository defines it"))
    return faults


def flags_in_faults(path, defined):
    faults = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "ReqctlError":
            continue
        for given in node.args:
            if isinstance(given, ast.Constant):
                said = str(given.value)
            elif isinstance(given, ast.JoinedStr):
                said = "".join(piece.value for piece in given.values
                               if isinstance(piece, ast.Constant))
            else:
                continue
            for flag in set(BARE_FLAG.findall(said)):
                if flag not in defined:
                    faults.append((path, given.lineno,
                                   f"this fault names {flag}, which no parser "
                                   "defines"))
    return faults


def survey():
    known = set(tracked())
    defined = flags_defined()
    faults = []
    for path in listed("*.md"):
        text = read(path)
        faults += paths_named(text, path, known)
        faults += flags_named(text, path, defined)
    for path in listed("reqctl/reqctl/*.py"):
        faults += flags_in_faults(path, defined)
    return faults


def main():
    faults = survey()
    for path, line, why in faults:
        print(f"::error file={path},line={line}::{why}")
    print(f"{len(faults)} names that resolve to nothing")
    return 1 if faults else 0


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    sys.exit(main())
