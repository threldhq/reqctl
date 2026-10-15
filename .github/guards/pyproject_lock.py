#!/usr/bin/env python3
import re
import sys
import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

PROJECT = Path("reqctl/pyproject.toml")
LOCK = Path("reqctl/requirements-lock.txt")
PINNED = re.compile(r"([A-Za-z0-9][\w.-]*)(?:\[[^\]]*\])?==(\S+)")
REMEDY = ("-- correct the range, or regenerate the lock with the pip-compile "
          "command its header names")


def read(path):
    # @req+ GUARD-83168738@zhoOQpGgBd9R de3ihq
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as broken:
        raise SystemExit(f"::error::{path}: cannot read: {broken}") from broken
    # @req- de3ihq


def declared():
    # @req+ GUARD-83168738@zhoOQpGgBd9R ehhsto
    try:
        held = tomllib.loads(read(PROJECT))
        return [Requirement(line) for line in
                held["project"]["dependencies"] + held["build-system"]["requires"]]
    except (tomllib.TOMLDecodeError, KeyError, TypeError,
            InvalidRequirement) as broken:
        raise SystemExit(f"::error::{PROJECT}: cannot parse: {broken}") from broken
    # @req- ehhsto


def locked():
    held = {}
    for line in read(LOCK).splitlines():
        found = PINNED.match(line)
        if not found:
            continue
        # @req+ GUARD-83168738@zhoOQpGgBd9R us7ggv
        try:
            held[canonicalize_name(found[1])] = Version(found[2])
        except InvalidVersion as broken:
            raise SystemExit(f"::error::{LOCK}: cannot parse: {broken}") from broken
        # @req- us7ggv
    return held


def main():
    wanted, held = declared(), locked()
    if not wanted or not held:
        print(f"::error::found {len(wanted)} requirement(s) in {PROJECT} and "
              f"{len(held)} pin(s) in {LOCK}; nothing left to compare means "
              "this check is broken, not passing")
        return 1
    found = []
    # @req> GUARD-39842261@bWyFMC8rM_YC qko53r
    for requirement in wanted:
        pinned = held.get(canonicalize_name(requirement.name))
        if pinned is None:
            found.append(f"{PROJECT} requires {requirement}, which {LOCK} does "
                         f"not hold {REMEDY}")
        elif not requirement.specifier.contains(pinned, prereleases=True):
            found.append(f"{PROJECT} requires {requirement}, but {LOCK} holds "
                         f"{requirement.name}=={pinned} {REMEDY}")
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
