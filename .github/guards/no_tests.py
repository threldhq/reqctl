#!/usr/bin/env python3
import subprocess
import sys

from reqctl import corpus


def tracked():
    found = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=False)
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    held = sorted({path for path in found.stdout.split("\0") if path})
    if not held:
        raise SystemExit("cannot list files: git lists none")
    return held


def main():
    # @req+ GUARD-86063188@GFGejAdpTlxL gcor4z
    held = [path for path in tracked() if corpus.is_test(path)]
    for path in held:
        print(f"::error file={path}::{path} is a test; delete it")
    return 1 if held else 0
    # @req- gcor4z


if __name__ == "__main__":
    sys.exit(main())
