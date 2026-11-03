#!/usr/bin/env python3
import subprocess
import sys

from reqctl import corpus

LISTED = "linted_paths"
MYPY_CONFIG = "reqctl/pyproject.toml"


def paths():
    try:
        item = corpus.find(corpus.load()[0], LISTED)
    except corpus.ReqctlError as broken:
        sys.exit(str(broken))
    found = [fields.get("path") if isinstance(fields, dict) else None
             for fields in (corpus.entries(item.data) or {}).values()]
    if not found or not all(isinstance(path, str) and path for path in found):
        sys.exit(f"{LISTED}: every entry states a path, and at least one entry is held "
                 "-- give each entry of the data item a path")
    return found


# @req> GUARD-99113200@u605TKfh4fwm c53mga
def main():
    listed = paths()
    failed = [argv[0] for argv in (["ruff", "check", "--", *listed],
                                   ["mypy", "--config-file", MYPY_CONFIG, "--", *listed])
              if subprocess.run(argv, check=False).returncode]
    if failed:
        print(f"::error::{' and '.join(failed)} report findings under {LISTED} -- "
              "fix each one, or give a deliberate pattern a per-file ignore")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
