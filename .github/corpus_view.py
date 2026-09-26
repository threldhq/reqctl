#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

from corpus_write import Refused, ran

VIEW = "corpus-view"
HELD = "corpus.json"


def view():
    ran("reqctl", "validate")
    ran("reqctl", "baseline", "--check")
    uids = list(json.loads(ran("reqctl", "--json", "export", "--all").stdout))
    return ran("reqctl", "--json", "context", *uids).stdout


def published(text, env):
    slug = env["APP_SLUG"]
    bot = f"{slug}[bot]"
    held = ran("gh", "api", f"/users/{slug}%5Bbot%5D", "--jq", ".id")
    ran("git", "config", "user.name", bot)
    ran("git", "config", "user.email",
        f"{held.stdout.strip()}+{bot}@users.noreply.github.com")
    found = ran("git", "ls-remote", "--exit-code", "--heads", "origin", VIEW,
                check=False).returncode
    if found == 0:
        ran("git", "fetch", "origin", VIEW, "--depth", "1")
        ran("git", "checkout", "-B", VIEW, "FETCH_HEAD")
    elif found == 2:
        ran("git", "checkout", "--orphan", VIEW)
        ran("git", "rm", "-r", "--cached", ".", "--quiet")
    else:
        raise Refused(f"git ls-remote exited {found}; cannot tell whether "
                      f"{VIEW} exists")
    Path(HELD).write_text(text)
    ran("git", "add", HELD)
    if ran("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        return "the corpus has not moved"
    ran("git", "commit", "-m", f"corpus at {env['GITHUB_SHA']}")
    ran("git", "push", "origin", VIEW)
    return f"published the corpus at {env['GITHUB_SHA']}"


def main():
    env = os.environ
    try:
        # @req+ REQ-71344419@No0izFxAdVKW byu3xs
        trunk = f"refs/heads/{env['DEFAULT_BRANCH']}"
        if env["GITHUB_REF"] != trunk:
            said = f"{env['GITHUB_REF']} is not {trunk}; nothing is published"
        else:
            said = published(view(), env)
        # @req- byu3xs
    except Refused as refused:
        print(f"::error::{refused}")
        return 1
    print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main())
