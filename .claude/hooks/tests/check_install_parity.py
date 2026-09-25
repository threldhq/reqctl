#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COSMETIC = ("--quiet", "--disable-pip-version-check")


def installs(text):
    found = []
    for line in text.replace("\\\n", " ").splitlines():
        words = line.replace('"', "").split()
        if "install" not in words:
            continue
        at = words.index("install")
        if at == 0 or not words[at - 1].split("/")[-1].startswith("pip"):
            continue
        rest = words[at + 1:]
        flags, files, editable, positional = [], [], [], []
        i = 0
        while i < len(rest):
            word = rest[i]
            if word == "-r":
                files.append(rest[i + 1])
                i += 2
            elif word == "-e":
                editable.append(rest[i + 1])
                i += 2
            elif word.startswith("-"):
                if word.startswith("--") and word not in COSMETIC:
                    flags.append(word)
                i += 1
            else:
                positional.append(word)
                i += 1
        found.append((sorted(flags), sorted(files), editable, sorted(positional)))
    return found


hook = installs((ROOT / ".claude" / "hooks" / "session-start.sh").read_text())
ci = installs((ROOT / ".github" / "workflows" / "ci.yml").read_text())

if not hook or not ci:
    print(f"found {len(hook)} hook install(s) and {len(ci)} CI install(s); "
          "nothing left to compare means this check is broken, not passing")
    sys.exit(1)
if hook != ci:
    print("session-start.sh and ci.yml install differently:")
    print(f"  hook: {hook}")
    print(f"  ci:   {ci}")
    sys.exit(1)
sys.exit(0)
