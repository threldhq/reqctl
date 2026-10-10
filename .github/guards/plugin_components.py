#!/usr/bin/env python3
import posixpath
import subprocess
import sys

from reqctl import corpus

FOLDERS = "plugin_folders"
COMPONENTS = "plugin_components"


def tracked(top):
    found = subprocess.run(
        ["git", "-C", str(top), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard"],
        capture_output=True, text=True, check=False)
    # @req> GUARD-83168738@zhoOQpGgBd9R pb3q4p
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    return sorted({path for path in found.stdout.split("\0") if path})


def stated():
    # @req+ GUARD-83168738@zhoOQpGgBd9R srriau
    try:
        store, top = corpus.load()
        folders = corpus.entries(corpus.find(store, FOLDERS).data) or {}
        components = corpus.entries(corpus.find(store, COMPONENTS).data) or {}
    except corpus.ReqctlError as broken:
        raise SystemExit(f"cannot read the corpus: {broken}") from broken
    # @req- srriau
    root = (folders.get("root") or {}).get("path")
    # @req> GUARD-83168738@zhoOQpGgBd9R et4qu4
    if not isinstance(root, str) or not root.endswith("/"):
        raise SystemExit(f"{FOLDERS}: root states no path ending in a slash; "
                         f"`reqctl revise {FOLDERS} --entry root --set path=...`")
    owned = {name: (fields or {}).get("paths") for name, fields in components.items()}
    # @req> GUARD-83168738@zhoOQpGgBd9R hf3iq2
    if not owned:
        raise SystemExit(f"{COMPONENTS}: states no entries")
    return top, root, owned


def outside(path):
    return posixpath.normpath(path).split("/")[0] in ("", "..")


# @req> GUARD-87984565@VEipgV2EseNW jp53yq
def covers(path, file):
    return file.startswith(path) if path.endswith("/") else file == path


def faults(root, owned, files):
    # @req> GUARD-87984565@VEipgV2EseNW 7jy76s
    held = [file[len(root):] for file in files if file.startswith(root)]
    # @req> GUARD-83168738@zhoOQpGgBd9R cfvd63
    if not held:
        return [f"{root}: holds no tracked file; fix the path of {FOLDERS}' root"]
    found = []
    for name, paths in owned.items():
        # @req> GUARD-83168738@zhoOQpGgBd9R cqu7df
        if not isinstance(paths, list) or not paths:
            found.append(f"{COMPONENTS}: {name} states {paths!r}, not a list of paths")
            owned[name] = []
        for path in owned[name]:
            # @req> GUARD-83168738@zhoOQpGgBd9R 234iqr
            if not isinstance(path, str):
                found.append(f"{COMPONENTS}: {name} states {path!r}, not a path")
                continue
            # @req+ GUARD-46345440@qP_IWjdqHBUF o6fai7
            if outside(path):
                found.append(f"{COMPONENTS}: {name} states {path!r}, which reaches "
                             f"outside {root}; state it relative to {root}")
            elif not any(covers(path, file) for file in held):
                found.append(f"{COMPONENTS}: {name} states {path!r}, which covers "
                             f"no file tracked under {root}; drop it or add the file")
            # @req- o6fai7
    # @req> GUARD-87984565@VEipgV2EseNW m7ltuf
    for file in held:
        owners = [name for name, paths in owned.items()
                  if any(isinstance(path, str) and not outside(path)
                         and covers(path, file) for path in paths)]
        if not owners:
            found.append(f"{root}{file}: belongs to none of the {COMPONENTS}; "
                         "add its path to the component that ships it, or delete it")
        elif len(owners) > 1:
            found.append(f"{root}{file}: belongs to {', '.join(owners)}; keep its "
                         "path in one of them")
    return found


def main():
    top, root, owned = stated()
    found = faults(root, owned, tracked(top))
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
