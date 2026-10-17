#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEPENDABOT = "dependabot[bot]"
ISSUE = "https://api.github.com/repos/{}/issues/{}"
SECONDS = 30


def keywords():
    try:
        found = subprocess.run(["reqctl", "--json", "context", "issue_keywords"],
                               capture_output=True, text=True, check=False)
    except FileNotFoundError as missing:
        raise SystemExit(f"::error::cannot run reqctl: {missing}")
    try:
        return sorted(json.loads(found.stdout)[0]["entries"])
    except (json.JSONDecodeError, LookupError, TypeError):
        said = (found.stderr.strip() or found.stdout.strip()
                or f"reqctl exited {found.returncode} printing nothing")
        raise SystemExit(f"::error::cannot read issue_keywords: {said}")


# @req> GUARD-80881960@UfZQs_f1P8Qb rlj2ox
def named(body, words):
    form = re.compile(rf"\b(?:{'|'.join(map(re.escape, words))})(?::\s*|\s+)#(\d+)\b",
                      re.IGNORECASE)
    return sorted({int(number) for number in form.findall(body or "")})


# @req> GUARD-80881960@UfZQs_f1P8Qb flffzz
def unnamed(repository, number, token):
    request = urllib.request.Request(
        ISSUE.format(repository, number),
        headers={"Accept": "application/vnd.github+json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=SECONDS) as answer:
            held = json.load(answer)
    except urllib.error.HTTPError as refused:
        if refused.code in (404, 410):
            return f"#{number} is no issue of {repository}"
        return f"#{number} could not be looked up: GitHub answered {refused.code}"
    except (urllib.error.URLError, TimeoutError, ValueError) as broken:
        return f"#{number} could not be looked up: {broken}"
    if not isinstance(held, dict):
        return f"#{number} could not be looked up: GitHub answered no issue record"
    if "pull_request" in held:
        return f"#{number} is a pull request, not an issue"
    return None


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        pull = event["pull_request"]
        repository = os.environ["GITHUB_REPOSITORY"]
    except (KeyError, TypeError, OSError, ValueError) as broken:
        print(f"::error::cannot read the pull request event: {broken!r}")
        return 1
    # @req+ GUARD-54236737@mQ9hKg4LFSMf r44fy4
    if (pull.get("user") or {}).get("login") == DEPENDABOT:
        print("dependabot opened this pull request, so it need not name an issue")
        return 0
    numbers = named(pull.get("body"), keywords())
    reasons = [unnamed(repository, number, os.environ.get("GH_TOKEN", ""))
               for number in numbers]
    if any(reason is None for reason in reasons):
        return 0
    print(f"::error::the pull request body names no issue of {repository} -- write "
          "Refs #N, or Closes #N on the pull request that finishes it, where N is "
          "an issue of this repository, then save the body; the check runs again "
          "on the edit")
    for reason in reasons:
        print(f"::error::{reason}")
    return 1
    # @req- r44fy4


if __name__ == "__main__":
    sys.exit(main())
