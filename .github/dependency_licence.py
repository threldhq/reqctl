#!/usr/bin/env python3
import base64
import http.client
import json
import os
import sys
import urllib.request

COMPARE = "https://api.github.com/repos/{}/dependency-graph/compare/{}...{}"
SECONDS = 30
# @req> copyable_licences@ns-krxMVBL57 r3cf6d
COPYABLE = ("Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT", "0BSD")
UNDETECTED = ("NOASSERTION", "LicenseRef-")
UNPROCESSED = "x-github-dependency-graph-snapshot-warnings"


def added(repository, base, head, token):
    request = urllib.request.Request(
        COMPARE.format(repository, base, head),
        headers={"Accept": "application/vnd.github+json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=SECONDS) as answer:
            held, pending = json.load(answer), answer.headers.get(UNPROCESSED)
    except (OSError, http.client.HTTPException, ValueError) as broken:
        said = getattr(broken, "read", bytes)().decode(errors="replace").strip()
        raise SystemExit(f"::error::cannot read the dependencies {base}...{head} adds "
                         f"in {repository}: {broken} {said} -- enable the "
                         "repository's dependency graph, or run the gate again "
                         "once GitHub's dependency review answers") from broken
    if not isinstance(held, list) or not all(isinstance(one, dict) for one in held):
        raise SystemExit("::error::GitHub's dependency review answered no list of "
                         "changes -- run the gate again")
    if pending and pending.strip():
        try:
            said = base64.b64decode(pending).decode(errors="replace").strip()
        except ValueError:
            said = pending
        raise SystemExit("::error::GitHub's dependency graph has not processed "
                         f"{base}...{head} yet: {said} -- run the gate again")
    return [one for one in held if one.get("change_type") == "added"]


def fault(dependency):
    named = (f"{dependency.get('manifest')}: {dependency.get('name')} "
             f"{dependency.get('version')}")
    licence = dependency.get("license")
    if not isinstance(licence, str) or not licence.strip() or licence.startswith(UNDETECTED):
        return (f"{named} adds a dependency whose licence cannot be detected -- "
                f"remove it, or add one under {', '.join(COPYABLE)}")
    words = licence.replace("(", " ").replace(")", " ").split()
    if (len(words) % 2 == 0 or any(word.upper() != "OR" for word in words[1::2])
            or not set(words[0::2]) & set(COPYABLE)):
        return (f"{named} adds a dependency under {licence} -- remove it, or add "
                f"one under {', '.join(COPYABLE)}")
    return None


# @req> REQ-36851513@1OptO4udNoIP 4ilqgs
# @req> REQ-43266463@Ea4ulHYAmCfN r6hgpy
def main():
    repository, base, head = (os.environ.get(name, "") for name in
                               ("GITHUB_REPOSITORY", "BASE_REF", "HEAD_SHA"))
    if not (repository and base and head):
        raise SystemExit("::error::the dependency licence gate needs "
                         "GITHUB_REPOSITORY, BASE_REF and HEAD_SHA -- pass them "
                         "from the pull request")
    found = [one for one in map(fault, added(repository, base, head,
                                             os.environ.get("GH_TOKEN", "")))
             if one]
    for one in found:
        print(f"::error::{one}")
    return 1 if found else 0


# @req> REQ-36851513@1OptO4udNoIP h27djc
# @req> REQ-43266463@Ea4ulHYAmCfN 4vx66w
if __name__ == "__main__":
    sys.exit(main())
