#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify

faults = []


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


case("run() executes in the repository root by default",
     verify.run("pwd", {}).stdout.strip(), str(verify.ROOT))

ELSEWHERE = verify.ROOT / "reqctl"
case("run() honours an explicit working directory",
     verify.run("pwd", {}, ELSEWHERE).stdout.strip(), str(ELSEWHERE))

CAVEAT = ("the working tree holds uncommitted changes, and what this touches "
          "was read from committed history only -- commit first, or pass "
          "--event workflow_dispatch to run every step")


def told(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


case("a clean tree draws no caveat, so a committed run reads as it did",
     verify.caveat(told()), "")
case("nor does any shape of whitespace git prints when nothing is modified",
     [verify.caveat(told(out=one)) for one in ("\n", "  \n", "\r\n", " ")],
     ["", "", "", ""])
case("an uncommitted change draws it, stating what this touches was read "
     "from and the flag that runs every step regardless",
     verify.caveat(told(out=" M .github/verify.py\n")), CAVEAT)

try:
    verify.caveat(told(code=128, err="fatal: index file smaller than expected\n"))
except SystemExit as stopped:
    case("a git that cannot answer stops the run, because an empty answer "
         "reads exactly like a committed tree",
         str(stopped), "cannot tell whether the working tree is committed: "
                       "fatal: index file smaller than expected")
else:
    faults.append("a git that could not answer was read as a clean tree")

try:
    verify.caveat(told(code=128))
except SystemExit as stopped:
    case("and names its exit where it said nothing at all", str(stopped),
         "cannot tell whether the working tree is committed: "
         "git status exited 128")
else:
    faults.append("a git that failed silently was read as a clean tree")

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
