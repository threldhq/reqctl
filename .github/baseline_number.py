#!/usr/bin/env python3
import subprocess
import sys

import yaml

DERIVED = "requirements/baseline.yml"
NUMBER = "baseline"
ABSENT = object()
BROKEN = object()


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=False)


def stated(ref):
    if _git("cat-file", "-e", f"{ref}^{{commit}}").returncode != 0:
        return BROKEN, BROKEN
    found = _git("show", f"{ref}:{DERIVED}")
    if found.returncode != 0:
        return ABSENT, ABSENT
    try:
        read = yaml.safe_load(found.stdout)
    except yaml.YAMLError:
        read = None
    held = read.get(NUMBER) if isinstance(read, dict) else None
    return found.stdout, held


def main(base):
    was, before = stated(base)
    now, after = stated("HEAD")
    if was is BROKEN or now is BROKEN:
        print(f"::error::{base if was is BROKEN else 'HEAD'} names no commit "
              "here, so the baseline it states cannot be read; fetch it, then "
              "run this again")
        return 1
    if was is ABSENT or now is ABSENT or was == now:
        return 0
    if type(before) is not int or type(after) is not int:
        print(f"::error::the baseline states {after!r} where {base} states "
              f"{before!r}, and a baseline names its number as a whole number; "
              "`reqctl baseline --check` names the fault")
        return 1
    if after > before:
        return 0
    print(f"::error::this pull request states baseline {after}, but {base} "
          f"states {before}; merge {base}, then run `reqctl baseline "
          "--generate` so the number follows the one it supersedes")
    return 1


def cli(argv):
    if len(argv) != 2:
        print("usage: baseline_number.py BASE_REF", file=sys.stderr)
        return 2
    return main(argv[1])


if __name__ == "__main__":
    sys.exit(cli(sys.argv))
