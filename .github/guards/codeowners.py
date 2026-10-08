#!/usr/bin/env python3
import sys
from pathlib import Path

OWNERS = Path(".github/CODEOWNERS")
EVERYTHING = "*"
OWNED = ("/requirements/", "/reqctl/", "/.github/", "/.claude/", "/CLAUDE.md",
         "/.mcp.json")


def rules(text):
    held = []
    for number, line in enumerate(text.splitlines(), 1):
        bare = line.split("#", 1)[0].strip()
        if not bare:
            continue
        pattern, *owners = bare.split()
        held.append((number, pattern, owners))
    return held


def faults(text):
    held = rules(text)
    # @req+ GUARD-96541664@oB0GqG8AdVP9 nfk4cl
    if not held:
        return [f"{OWNERS}: names no owner, so nothing waits for approval"]
    found = []
    if not any(pattern == EVERYTHING for _, pattern, _ in held):
        found.append(f"{OWNERS}: has no {EVERYTHING} rule, so a new top-level "
                     "path arrives matched by nothing and merges unapproved")
    # @req- nfk4cl
    # @req> GUARD-10823996@bfm-dN6H_Udf lmpkxv
    for wanted in OWNED:
        if not any(pattern == wanted for _, pattern, _ in held):
            found.append(f"{OWNERS}: does not name {wanted}; an agent that can "
                         "reach it can approve its own work indirectly")
    # @req> GUARD-27748979@G-APnovHS9P3 hgyrkk
    places = [spot for spot, (_, pattern, _) in enumerate(held)
              if pattern in OWNED]
    for spot, (number, pattern, owners) in enumerate(held):
        # @req> GUARD-27748979@G-APnovHS9P3 a2bfib
        if places and spot > min(places) and pattern not in OWNED:
            found.append(
                f"{OWNERS}:{number}: {pattern} follows the owned paths. GitHub "
                "takes the last matching rule, so this answers for whatever it "
                "also matches and lifts the owner's approval from it; a "
                "carve-out goes above them, never under")
        # @req> GUARD-32820195@-N_pWkH7K8rC 32oezj
        if not owners:
            found.append(f"{OWNERS}:{number}: {pattern} names no owner, which "
                         "removes approval rather than requiring it")
    return found


def main():
    # @req+ GUARD-83168738@zhoOQpGgBd9R jakglm
    try:
        text = OWNERS.read_text()
    except (OSError, UnicodeDecodeError) as broken:
        print(f"::error::cannot read {OWNERS}: {broken}")
        return 1
    # @req- jakglm
    found = faults(text)
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
