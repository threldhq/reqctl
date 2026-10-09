#!/usr/bin/env python3
import re
import subprocess
import sys

import yaml

from reqctl import corpus

LISTED = (corpus.CITATION_LIST,)
# @req> REQ-43374441@7pCJVe7pf8Mg c6qh2i
CARRIED = ("assessed",) + LISTED
GOVERNED = "requirements/"
DERIVED = GOVERNED + "baseline.yml"
GITLINK = "160000"
# @req> REQ-41600593@dauTiMee9rmb o3tsro
STAMPED = re.compile(
    rf"(@req[+>]\s+[^\s@]+)@[A-Za-z0-9_-]{{{corpus.TAG_STAMP}}}")
ABSENT = object()


def _git(*args):
    done = subprocess.run(["git", *args], capture_output=True, check=False)
    done.stdout = done.stdout.decode(errors="surrogateescape")
    done.stderr = done.stderr.decode(errors="surrogateescape")
    return done


def without(ref, path, keys):
    found = _git("show", f"{ref}:{path}")
    if found.returncode != 0:
        return ABSENT
    try:
        held = yaml.safe_load(found.stdout)
    except yaml.YAMLError:
        return found.stdout
    if not isinstance(held, dict):
        return found.stdout
    return {key: value for key, value in held.items() if key not in keys}


def only(base, path, keys):
    return without(base, path, keys) == without("HEAD", path, keys)


def without_stamps(ref, path):
    found = _git("show", f"{ref}:{path}")
    if found.returncode != 0:
        return ABSENT
    return STAMPED.sub(r"\1", found.stdout)


def repins_only(base, path):
    return without_stamps(base, path) == without_stamps("HEAD", path)


# @req+ REQ-43374441@7pCJVe7pf8Mg qya7yo
def classify(base):
    found = _git("merge-base", base, "HEAD")
    if found.returncode != 0:
        raise SystemExit(f"cannot diff against {base}: "
                         f"{found.stderr.strip() or 'it shares no commit with HEAD'}")
    fork = found.stdout.strip()
    found = _git("diff", "--no-renames", "--raw", "-z", fork, "HEAD")
    if found.returncode != 0:
        raise SystemExit(f"cannot diff against {base}: {found.stderr.strip()}")
    fields = found.stdout.split("\0")
    modes = {path: header.lstrip(":").split()[:2]
             for header, path in zip(fields[::2], fields[1::2])}
    changed = [path for path in modes if path != DERIVED]
    governed = [path for path in changed if path.startswith(GOVERNED)]
    other = [path for path in changed if not path.startswith(GOVERNED)]
    if not governed or not other:
        return [], other, []
    textual = {path for path, (was, now) in modes.items() if was == now != GITLINK}
    pinned = ([path for path in governed if only(fork, path, CARRIED)]
              + [path for path in other
                 if path in textual and repins_only(fork, path)])
    return ([path for path in governed if path not in pinned],
            [path for path in other if path not in pinned], pinned)


def main(base):
    content, other, pinned = classify(base)
    for path in pinned:
        print(f"pins or citation list only, travelling with what moved them: "
              f"{path}")
    if not content or not other:
        return 0
    print("::error::this pull request changes requirements and other things; "
          "split the requirement change out")
    print("requirements:")
    print("\n".join(f"  {path}" for path in content))
    print("everything else:")
    print("\n".join(f"  {path}" for path in other))
    return 1
# @req- qya7yo


def cli(argv):
    if len(argv) != 2:
        print("usage: travel_alone.py BASE_REF", file=sys.stderr)
        return 2
    return main(argv[1])


if __name__ == "__main__":
    sys.exit(cli(sys.argv))
