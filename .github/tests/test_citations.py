#!/usr/bin/env python3
import contextlib
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import citations

faults = []

STALE = {"uid": "REQ-84927103", "path": "app/index.tsx",
         "pinned": "AAAAAAAAAAAA", "held": "BBBBBBBBBBBB"}


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def held(problems, stale, settling):
    return citations.faults({"problems": problems, "stale": stale}, settling)


case("a clean tree passes either way", held([], [], False) + held([], [], True),
     [])
case("a stale pin is a fault while the corpus stands still",
     len(held([], [STALE], False)), 1)
case("the fault names the requirement, the file and both stamps",
     held([], [STALE], False),
     ["REQ-84927103: app/index.tsx pinned @AAAAAAAAAAAA, now @BBBBBBBBBBBB"])
case("a stale pin passes while the corpus is settling",
     held([], [STALE], True), [])
case("a problem is a fault while the corpus is settling",
     held(["REQ-1: cited by src/a.py but is draft, not approved"], [STALE],
          True),
     ["REQ-1: cited by src/a.py but is draft, not approved"])
case("problems and stale pins are both named",
     len(held(["REQ-1: broken"], [STALE], False)), 2)


def refused(call):
    try:
        call()
    except SystemExit as clean:
        return str(clean)
    return ""


case("a trace missing problems or stale is refused cleanly, not crashed on",
     refused(lambda: citations.faults({"error": "corpus is invalid"}, False))
     .startswith("cannot read trace"), True)
case("the refusal names what reqctl reported",
     "corpus is invalid" in
     refused(lambda: citations.faults({"error": "corpus is invalid"}, False)),
     True)


def without_reqctl():
    held_path = os.environ.get("PATH", "")
    os.environ["PATH"] = "/nonexistent-empty-bin-dir"
    try:
        return refused(citations.traced)
    finally:
        os.environ["PATH"] = held_path


case("a missing reqctl binary is refused cleanly, not crashed on",
     without_reqctl().startswith("cannot run reqctl"), True)


def ran(data, settling):
    original = citations.traced
    citations.traced = lambda: data
    held_env = os.environ.get(citations.SETTLING)
    os.environ[citations.SETTLING] = "true" if settling else "false"
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = citations.main()
        return code, out.getvalue()
    finally:
        citations.traced = original
        if held_env is None:
            os.environ.pop(citations.SETTLING, None)
        else:
            os.environ[citations.SETTLING] = held_env


code, output = ran({"problems": [], "stale": []}, False)
case("main() passes a clean trace", code, 0)
case("main() prints nothing when clean", output, "")

code, output = ran({"problems": ["REQ-1: cited by src/a.py but is draft"],
                    "stale": []}, False)
case("main() refuses a real problem", code, 1)
case("main()'s output names it",
     output, "::error::REQ-1: cited by src/a.py but is draft\n")

case("a stale pin left for later is reported while the corpus is settling",
     held([], [STALE], True) + citations.deferred(
         {"problems": [], "stale": [STALE]}, True),
     ["REQ-84927103: app/index.tsx pinned @AAAAAAAAAAAA, now @BBBBBBBBBBBB"])
case("nothing is left for later while the corpus stands still",
     citations.deferred({"problems": [], "stale": [STALE]}, False), [])

code, output = ran({"problems": [], "stale": [STALE]}, True)
case("main() passes a stale pin while the corpus is settling", code, 0)
case("main() says the pin is owed and where it may be paid",
     output,
     "::notice::REQ-84927103: app/index.tsx pinned @AAAAAAAAAAAA, "
     "now @BBBBBBBBBBBB -- re-pin it here, or in the pull request "
     "that carries the code\n")

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
