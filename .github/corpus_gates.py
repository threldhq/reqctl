#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOVERNED = "requirements/"


def settling(base):
    if not base:
        return "false"
    found = subprocess.run(
        ["git", "diff", "--name-only", f"origin/{base}...HEAD"],
        capture_output=True, text=True, check=False)
    if found.returncode != 0:
        raise SystemExit(f"cannot diff against origin/{base}: "
                         f"{found.stderr.strip()}")
    touched = any(path.startswith(GOVERNED)
                  for path in found.stdout.splitlines())
    return "true" if touched else "false"


def main():
    base = os.environ.get("BASE_REF", "")
    env = {**os.environ, "SETTLING": settling(base)}
    python, against, pulled = sys.executable, f"origin/{base}", bool(base)
    # @req+ REQ-26876750@p5bO3gEKEYCb x2zlt2
    gates = (
        ("travel_alone", [python, HERE / "travel_alone.py", against], pulled),
        ("baseline_numbering", [python, HERE / "baseline_number.py", against],
         pulled),
        ("corpus_validity", ["reqctl", "validate"], True),
        ("baseline_match", ["reqctl", "baseline", "--check"], True),
        ("traceability", [python, HERE / "guards" / "citations.py"], True),
        ("taxonomy", [python, HERE / "guards" / "taxonomy.py"], True),
        ("stamp_admission", [python, HERE / "guards" / "gitleaks_stamps.py"],
         True),
    )
    for name, argv, runs in gates:
        if not runs:
            print(f"{name}: judges a pull request, and this run is none")
            continue
        print(f"::group::{name}")
        done = subprocess.run(argv, env=env, check=False)
        print("::endgroup::")
        if done.returncode != 0:
            print(f"::error::{name} refuses this change")
            return 1
    # @req- x2zlt2
    return 0


if __name__ == "__main__":
    sys.exit(main())
