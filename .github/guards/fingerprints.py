#!/usr/bin/env python3
import hashlib
import importlib.util
import sys
from pathlib import Path

from plugin_components import COMPONENTS, stated, tracked

HOOK = "requirements_guard_hook"


def names_corpus(guard, data):
    if guard.CORPUS_ROOT_NAME.encode() not in data:
        return False
    text = guard.flatten(data.decode(errors="replace"))
    return bool(guard.CORPUS_DIR.search(text) or guard.ROOT_QUOTED.search(text))


def main():
    top, root, owned = stated()
    paths = owned.get(HOOK)
    if not isinstance(paths, list) or len(paths) != 1:
        raise SystemExit(f"{COMPONENTS}: {HOOK} states {paths!r}, not one path")
    hook = root + paths[0]
    spec = importlib.util.spec_from_file_location("requirements_guard", Path(top) / hook)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    # @req+ GUARD-58772071@qal1M_8xilDP cezbrd
    expected = {
        hashlib.sha256(data).hexdigest(): file
        for file in tracked(top)
        if file.startswith(root) and file != hook
        and names_corpus(guard, data := (Path(top) / file).read_bytes())
    }
    missing = sorted(set(expected) - guard.FINGERPRINTS)
    extra = sorted(guard.FINGERPRINTS - set(expected))
    for digest in missing:
        print(f"::error::{hook}: FINGERPRINTS lacks {digest}, the digest of "
              f"{expected[digest]}; add it")
    for digest in extra:
        print(f"::error::{hook}: FINGERPRINTS holds {digest}, which no plugin file naming "
              "the corpus has; drop it")
    return 1 if missing or extra else 0
    # @req- cezbrd


if __name__ == "__main__":
    sys.exit(main())
