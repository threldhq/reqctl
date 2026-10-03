#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tomllib

WHEEL = "reqctl/pyproject.toml"
MARKETPLACE = ".claude-plugin/marketplace.json"
MANIFEST = ".claude-plugin/plugin.json"


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=False)


def shown(commit, path, parse):
    found = _git("show", f"{commit}:{path}")
    if found.returncode != 0:
        return {}
    try:
        held = parse(found.stdout)
    except ValueError:
        return {}
    return held if isinstance(held, dict) else {}


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
    tag = pinned(after)
    if tag is None or pinned(before) == tag:
        return 0
    if _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode == 0:
        return 0
    pushed = subprocess.run(
        ["gh", "api", "--method", "POST",
         f"repos/{os.environ['GITHUB_REPOSITORY']}/git/refs",
         "-f", f"ref=refs/tags/{tag}", "-f", f"sha={after}"],
        capture_output=True, text=True, check=False)
    if pushed.returncode != 0:
        print(f"::error::cannot push {tag} at {after}: "
              f"{pushed.stderr.strip() or pushed.stdout.strip()}")
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
