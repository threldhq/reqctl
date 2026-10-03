#!/usr/bin/env python3
import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path

from corpus_write import Refused, ran

WHEEL = "reqctl/pyproject.toml"
MARKETPLACE = ".claude-plugin/marketplace.json"
MANIFEST = ".claude-plugin/plugin.json"
ABSENT = "(HTTP 404)"


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


def marked(tag):
    return ran("git", "rev-parse", "--verify", "--quiet",
               f"refs/tags/{tag}^{{commit}}", check=False).stdout.strip() or None


def released(repo, tag):
    asked = f"repos/{repo}/releases/tags/{tag}"
    done = ran("gh", "api", asked, check=False)
    if done.returncode and ABSENT in done.stderr:
        return None
    if done.returncode:
        raise Refused(f"gh api {asked}: {done.stderr.strip() or 'failed silently'}")
    try:
        return json.loads(done.stdout)
    except ValueError as broken:
        raise Refused(f"gh api {asked}: {broken}") from broken


# @req> GUARD-14769016@T01UILpAY633 z2onys
def attach(repo, tag, commit):
    name = shown(commit, WHEEL, tomllib.loads)["project"]["name"]
    prefix = re.sub(r"[-_.]+", "_", name).lower() + "-"
    release = released(repo, tag)
    if release is not None and any(
            str(asset.get("name")).startswith(prefix)
            and str(asset.get("name")).endswith(".whl")
            for asset in release.get("assets") or []):
        return f"the release for {tag} already carries a {name} wheel"
    if ran("git", "rev-parse", "HEAD").stdout.strip() != commit:
        raise Refused(f"the checkout is not at {commit}, the commit {tag} "
                      "marks; check that commit out to build its wheel")
    with tempfile.TemporaryDirectory() as out:
        ran(sys.executable, "-m", "pip", "wheel", "--no-deps",
            "--no-build-isolation", "--wheel-dir", out,
            str(Path(WHEEL).resolve().parent))
        wheel = next(Path(out).glob(f"{prefix}*.whl"), None)
        if wheel is None:
            raise Refused(f"pip wheel built no {name} wheel from {WHEEL}")
        if release is None:
            ran("gh", "release", "create", tag, str(wheel), "--repo", repo,
                "--verify-tag", "--title", tag, "--notes", "")
        else:
            ran("gh", "release", "upload", tag, str(wheel), "--repo", repo)
        return f"attached {wheel.name} to the release for {tag}"


def main(before, after):
    repo = os.environ["GITHUB_REPOSITORY"]
    try:
        # @req+ GUARD-60575106@cyDaQHsIDZhK nc7w6k
        tag = pinned(after)
        if tag is None:
            return 0
        held = marked(tag)
        if held is None and pinned(before) != tag:
            ran("gh", "api", f"repos/{repo}/git/refs",
                "-f", f"ref=refs/tags/{tag}", "-f", f"sha={after}")
            print(f"pushed {tag} at {after}")
            held = after
        # @req- nc7w6k
        # @req> GUARD-14769016@T01UILpAY633 huv5w6
        if held == after:
            print(attach(repo, tag, after))
    except Refused as refused:
        print(f"::error::{refused}")
        return 1
    return 0


def cli(argv):
    if len(argv) != 3:
        print("usage: release_tag.py BEFORE AFTER", file=sys.stderr)
        return 2
    return main(argv[1], argv[2])


if __name__ == "__main__":
    sys.exit(cli(sys.argv))
