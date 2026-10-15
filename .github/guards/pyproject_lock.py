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
PINNED = re.compile(r"([A-Za-z0-9][\w.-]*)(?:\[[^\]]*\])?==([^\s\\;]+)")
REMEDY = ("-- correct the range, or regenerate the lock with the pip-compile "
          "command its header names")


def read(path):
    # @req+ GUARD-83168738@zhoOQpGgBd9R de3ihq
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as broken:
        raise SystemExit(f"{path}: cannot read: {broken}") from broken
    # @req- de3ihq


def declared():
    # @req+ GUARD-83168738@zhoOQpGgBd9R ehhsto
    try:
        project = tomllib.loads(read(PROJECT))
        return [Requirement(spec) for spec in
                project["project"]["dependencies"]
                + project["build-system"]["requires"]]
    except (tomllib.TOMLDecodeError, KeyError, TypeError,
            InvalidRequirement) as broken:
        raise SystemExit(f"{PROJECT}: cannot parse: {broken}") from broken
    # @req- ehhsto


def locked():
    pins = {}
    for line in read(LOCK).splitlines():
        found = PINNED.match(line)
        if not found:
            continue
        # @req+ GUARD-83168738@zhoOQpGgBd9R us7ggv
        try:
            pins[canonicalize_name(found[1])] = Version(found[2])
        except InvalidVersion as broken:
            raise SystemExit(f"{LOCK}: cannot parse: {broken}") from broken
        # @req- us7ggv
    return pins


def main():
    wanted, pins = declared(), locked()
    if not wanted or not pins:
        print(f"::error::found {len(wanted)} requirement(s) in {PROJECT} and "
              f"{len(pins)} pin(s) in {LOCK}; nothing left to compare means "
              "this check is broken, not passing")
        return 1
    found = []
    # @req> GUARD-39842261@bWyFMC8rM_YC qko53r
    for requirement in wanted:
        pinned = pins.get(canonicalize_name(requirement.name))
        if requirement.marker and not requirement.marker.evaluate():
            continue
        if requirement.url:
            found.append(f"{PROJECT} requires {requirement} from a URL, which "
                         f"{LOCK} cannot pin -- name a version range instead")
        elif pinned is None:
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
