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
    if not held:
        return [f"{OWNERS}: names no owner, so nothing waits for approval"]
    found = []
    if not any(pattern == EVERYTHING for _, pattern, _ in held):
        found.append(f"{OWNERS}: has no {EVERYTHING} rule, so a new top-level "
                     "path arrives matched by nothing and merges unapproved")
    for wanted in OWNED:
        if not any(pattern == wanted for _, pattern, _ in held):
            found.append(f"{OWNERS}: does not name {wanted}; an agent that can "
                         "reach it can approve its own work indirectly")
    places = [spot for spot, (_, pattern, _) in enumerate(held)
              if pattern in OWNED]
    for spot, (number, pattern, owners) in enumerate(held):
        if places and spot > min(places) and pattern not in OWNED:
            found.append(
                f"{OWNERS}:{number}: {pattern} follows the owned paths. GitHub "
                "takes the last matching rule, so this answers for whatever it "
                "also matches and lifts the owner's approval from it; a "
                "carve-out goes above them, never under")
        if not owners:
            found.append(f"{OWNERS}:{number}: {pattern} names no owner, which "
                         "removes approval rather than requiring it")
    return found


def main():
    try:
        text = OWNERS.read_text()
    except OSError as broken:
        print(f"::error::cannot read {OWNERS}: {broken}")
        return 1
    found = faults(text)
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


mismatched = []


def case(name, got, want):
    if got != want:
        mismatched.append(f"{name}: expected {want}, got {got}")


SOUND = ("*                @threld-dev\n"
         "/requirements/   @threld-dev\n"
         "/reqctl/         @threld-dev\n"
         "/.github/        @threld-dev\n"
         "/.claude/        @threld-dev\n"
         "/CLAUDE.md       @threld-dev\n"
         "/.mcp.json       @threld-dev\n")

case("a sound codeowners text passes", faults(SOUND), [])

NO_WILDCARD = SOUND.replace("*                @threld-dev\n", "")
case("a codeowners naming every owned path but no wildcard is refused",
     any("has no *" in one for one in faults(NO_WILDCARD)), True)

SANDWICHED = SOUND.replace(
    "/reqctl/         @threld-dev\n",
    "/reqctl/extra/   @threld-dev\n/reqctl/         @threld-dev\n")
case("a broader rule sandwiched between two owned paths is refused, "
     "catching whichever owned rule is chosen as the boundary",
     any("follows the owned paths" in one for one in faults(SANDWICHED)), True)

if __name__ == "__main__":
    if mismatched:
        print("\n".join(mismatched))
        sys.exit(1)
    sys.exit(main())
