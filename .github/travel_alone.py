#!/usr/bin/env python3
import posixpath
import re
import subprocess
import sys

import yaml

from reqctl import corpus

# @req+ REQ-50816200@5wr7JJhod9Gm kzojze
LISTED = (corpus.CITATION_LIST,)
CARRIED = ("assessed",) + LISTED
GOVERNED = "requirements/"
DERIVED = GOVERNED + "baseline.yml"
COMPONENTS = f"{GOVERNED}{corpus.FOLDERS['data']}/plugin_components.yml"
PLUGIN_FOLDERS = f"{GOVERNED}{corpus.FOLDERS['data']}/plugin_folders.yml"
# @req- kzojze
# @req> REQ-41600593@dauTiMee9rmb o3tsro
STAMPED = re.compile(
    rf"(@req[+>]\s+[^\s@]+)@[A-Za-z0-9_-]{{{corpus.TAG_STAMP}}}")
# @req+ REQ-50816200@5wr7JJhod9Gm dyii6c
ABSENT = object()


def _git(*args):
    done = subprocess.run(["git", *args], capture_output=True, check=False)
    done.stdout = done.stdout.decode(errors="surrogateescape")
    done.stderr = done.stderr.decode(errors="surrogateescape")
    return done


def without(ref, path, keys, digests=False, dropped=()):
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
    whole = kept.get(corpus.WHOLE_FILES)
    if digests and isinstance(whole, dict):
        kept[corpus.WHOLE_FILES] = {
            cited: ({field: value for field, value in fields.items()
                     if field not in ("digest", "pinned")}
                    if isinstance(fields, dict) else fields)
            for cited, fields in whole.items()}
    held_entries = corpus.entries(kept)
    if dropped and held_entries is not None:
        kept["entries"] = {name: fields for name, fields in held_entries.items()
                           if name not in dropped}
    return kept


def only(base, path, keys, digests=False, dropped=()):
    return (without(base, path, keys, digests, dropped)
            == without("HEAD", path, keys, digests, dropped))


def entries_at(ref, path):
    held = without(ref, path, ())
    return (corpus.entries(held) or {}) if isinstance(held, dict) else {}


def stated_paths(root, components):
    return [root + path for fields in components.values() if isinstance(fields, dict)
            for path in fields.get("paths") or [] if isinstance(path, str)
            and posixpath.normpath(path).split("/")[0] not in ("", "..", ".")]


def added_paths(fork):
    was = entries_at(fork, COMPONENTS)
    added = {name: fields for name, fields in entries_at("HEAD", COMPONENTS).items()
             if name not in was}
    root = (entries_at(fork, PLUGIN_FOLDERS).get("root") or {}).get("path")
    if not isinstance(root, str) or not root.endswith("/"):
        return added, [], []
    return added, stated_paths(root, added), stated_paths(root, was)


def covered(paths, file):
    return any(file.startswith(path) if path.endswith("/") else file == path
               for path in paths)


def wholes(ref, path):
    held = without(ref, path, ())
    found = held.get(corpus.WHOLE_FILES) if isinstance(held, dict) else None
    return set(found) if isinstance(found, dict) else set()


def moved_wholes(fork, governed):
    return {cited for path in governed
            for cited in wholes(fork, path) ^ wholes("HEAD", path)}


def without_stamps(ref, path):
    found = _git("show", f"{ref}:{path}")
    if found.returncode != 0:
        return ABSENT
    return STAMPED.sub(r"\1", found.stdout)


def repins_only(base, path):
    was = without_stamps(base, path)
    return was is not ABSENT and was == without_stamps("HEAD", path)


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
        return [], other, []
    pinned = ([path for path in governed
               if only(fork, path, CARRIED, digests=True)]
              + [path for path in other
                 if textual[path] and repins_only(fork, path)])
    added, paths, held = added_paths(fork) if COMPONENTS in governed else ({}, [], [])
    carriers = [path for path in governed if path not in pinned
                and only(fork, path, CARRIED + (corpus.WHOLE_FILES,))]
    moved = moved_wholes(fork, carriers)
    if paths and only(fork, COMPONENTS, CARRIED, digests=True, dropped=added):
        carriers.append(COMPONENTS)
    loose = [path for path in other if path not in pinned]
    if carriers and loose and all(
            path in moved or (covered(paths, path) and not covered(held, path))
            for path in loose):
        pinned += [*carriers, *loose]
    return ([path for path in governed if path not in pinned],
            [path for path in other if path not in pinned], pinned)


def main(base):
    content, other, pinned = classify(base)
    for path in pinned:
        print(f"pins, citation list, whole-file citations or added plugin "
              f"components only, travelling with what moved them: {path}")
    if not content or not other:
        return 0
    print("::error::this pull request changes requirements and other things; "
          "split the requirement change out")
    print("requirements:")
    print("\n".join(f"  {path}" for path in content))
    print("everything else:")
    print("\n".join(f"  {path}" for path in other))
    return 1
# @req- dyii6c


def cli(argv):
    if len(argv) != 2:
        print("usage: travel_alone.py BASE_REF", file=sys.stderr)
        return 2
    return main(argv[1])


if __name__ == "__main__":
    sys.exit(cli(sys.argv))
