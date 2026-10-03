#!/usr/bin/env python3
import json
import os
import sys
import tomllib

from corpus_write import Refused, ran

WHEEL = "reqctl/pyproject.toml"
MARKETPLACE = ".claude-plugin/marketplace.json"
MANIFEST = ".claude-plugin/plugin.json"


def shown(commit, path, parse):
    try:
        held = parse(ran("git", "show", f"{commit}:{path}").stdout)
    except ValueError as broken:
        raise Refused(f"{commit}:{path}: {broken}") from broken
    if not isinstance(held, dict):
        raise Refused(f"{commit}:{path}: not a mapping")
    return held


def pinned(commit):
    name = (shown(commit, WHEEL, tomllib.loads).get("project") or {}).get("name")
    entry = next((one for one in shown(commit, MARKETPLACE, json.loads)
                  .get("plugins") or []
                  if isinstance(one, dict) and one.get("name") == name), {})
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "git-subdir":
        return None
    manifest = shown(commit, f"{source.get('path')}/{MANIFEST}", json.loads)
    tag = f"{manifest.get('name')}--v{manifest.get('version')}"
    return tag if source.get("ref") == tag else None


def main(before, after):
    # @req+ GUARD-60575106@QWS2QB-n2_dH s6dmsl
    try:
        tag = pinned(after)
        if tag is None or pinned(before) == tag:
            return 0
        if ran("git", "rev-parse", "--verify", f"refs/tags/{tag}",
               check=False).returncode == 0:
            return 0
        ran("gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/git/refs",
            "-f", f"ref=refs/tags/{tag}", "-f", f"sha={after}")
    except Refused as refused:
        print(f"::error::{refused}")
        return 1
    print(f"pushed {tag} at {after}")
    return 0
    # @req- s6dmsl


def cli(argv):
    if len(argv) != 3:
        print("usage: release_tag.py BEFORE AFTER", file=sys.stderr)
        return 2
    return main(argv[1], argv[2])


if __name__ == "__main__":
    sys.exit(cli(sys.argv))
