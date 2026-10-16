#!/usr/bin/env python3
import re
import subprocess
import sys

import yaml

from reqctl import corpus

LISTED = (corpus.CITATION_LIST,)
# @req> REQ-43374441@FrpNFcj-eNb_ c6qh2i
CARRIED = ("assessed",) + LISTED
GOVERNED = "requirements/"
DERIVED = GOVERNED + "baseline.yml"
COMPONENTS = "plugin_components"
FOLDERS = "plugin_folders"
# @req> REQ-41600593@dauTiMee9rmb o3tsro
STAMPED = re.compile(
    rf"(@req[+>]\s+[^\s@]+)@[A-Za-z0-9_-]{{{corpus.TAG_STAMP}}}")
ABSENT = object()


def _git(*args):
    done = subprocess.run(["git", *args], capture_output=True, check=False)
    done.stdout = done.stdout.decode(errors="surrogateescape")
    done.stderr = done.stderr.decode(errors="surrogateescape")
    return done


def without(ref, path, keys, digests=False):
    found = _git("show", f"{ref}:{path}")
    if found.returncode != 0:
        return ABSENT
    try:
        held = yaml.safe_load(found.stdout)
    except yaml.YAMLError:
        return found.stdout
    if not isinstance(held, dict):
        return found.stdout
    kept = {key: value for key, value in held.items() if key not in keys}
    # @req+ REQ-43374441@FrpNFcj-eNb_ burjli
    whole = kept.get(corpus.WHOLE_FILES)
    if digests and isinstance(whole, dict):
        kept[corpus.WHOLE_FILES] = {
            cited: ({field: value for field, value in fields.items()
                     if field not in ("digest", "pinned")}
                    if isinstance(fields, dict) else fields)
            for cited, fields in whole.items()}
    # @req- burjli
    return kept


def only(base, path, keys, digests=False):
    return (without(base, path, keys, digests)
            == without("HEAD", path, keys, digests))


def without_stamps(ref, path):
    found = _git("show", f"{ref}:{path}")
    if found.returncode != 0:
        return ABSENT
    return STAMPED.sub(r"\1", found.stdout)


def repins_only(base, path):
    was = without_stamps(base, path)
    return was is not ABSENT and was == without_stamps("HEAD", path)


# @req+ REQ-43374441@FrpNFcj-eNb_ qya7yo
def covered(fork, files):
    try:
        store, top = corpus.load()
        listing = corpus.find(store, COMPONENTS)
        root = (corpus.entries(corpus.find(store, FOLDERS).data) or {}).get("root")
    except corpus.ReqctlError:
        return []
    prefix = root.get("path") if isinstance(root, dict) else None
    if not isinstance(prefix, str) or not prefix.endswith("/"):
        return []
    held = listing.path.relative_to(top).as_posix()
    was, now = (without(ref, held, ()) for ref in (fork, "HEAD"))
    before = (corpus.entries(was) if isinstance(was, dict) else None) or {}
    after = (corpus.entries(now) if isinstance(now, dict) else None) or {}
    stated = [path for key, fields in after.items()
              if key not in before and isinstance(fields, dict)
              and isinstance(fields.get("paths"), list)
              for path in fields["paths"] if isinstance(path, str)]
    return [file for file in files if file.startswith(prefix) and any(
        file[len(prefix):].startswith(path) if path.endswith("/")
        else file[len(prefix):] == path for path in stated)]


def classify(base):
    found = _git("diff", "--no-renames", "--raw", "-z", f"{base}...HEAD")
    fork = _git("merge-base", base, "HEAD")
    if found.returncode or fork.returncode:
        raise SystemExit(f"cannot diff against {base}: "
                         f"{(found.stderr or fork.stderr).strip()}")
    fork = fork.stdout.strip()
    fields = found.stdout.split("\0")
    textual = {path: header[1:7] == header[8:14]
               for header, path in zip(fields[::2], fields[1::2])}
    changed = [path for path in textual if path != DERIVED]
    governed = [path for path in changed if path.startswith(GOVERNED)]
    other = [path for path in changed if not path.startswith(GOVERNED)]
    if not governed or not other:
        return [], other, [], []
    joined = covered(fork, other)
    other = [path for path in other if path not in joined]
    pinned = ([path for path in governed
               if only(fork, path, CARRIED, digests=True)]
              + [path for path in other
                 if textual[path] and repins_only(fork, path)])
    return ([path for path in governed if path not in pinned],
            [path for path in other if path not in pinned], pinned, joined)


def main(base):
    content, other, pinned, joined = classify(base)
    for path in pinned:
        print(f"pins or citation list only, travelling with what moved them: "
              f"{path}")
    for path in joined:
        print(f"covered by a plugin component this change adds, travelling "
              f"with it: {path}")
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
