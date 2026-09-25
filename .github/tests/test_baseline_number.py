#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import baseline_number

BASELINE = baseline_number.DERIVED
CODE = "reqctl/reqctl/corpus.py"


def _git(cwd, *args):
    done = subprocess.run(
        ["git", "-c", "gc.auto=0", "-c", "user.email=t@t",
         "-c", "user.name=t", *args],
        cwd=cwd, capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def ran(base_files, head_files, deleted=()):
    with tempfile.TemporaryDirectory() as room:
        for path, text in base_files.items():
            spot = Path(room) / path
            spot.parent.mkdir(parents=True, exist_ok=True)
            spot.write_text(text)
        _git(room, "init", "-q", "-b", "main")
        _git(room, "add", "-A")
        _git(room, "commit", "-qm", "base")
        base = _git(room, "rev-parse", "HEAD").strip()
        for path in deleted:
            (Path(room) / path).unlink()
        for path, text in head_files.items():
            spot = Path(room) / path
            spot.parent.mkdir(parents=True, exist_ok=True)
            spot.write_text(text)
        _git(room, "add", "-A")
        _git(room, "commit", "-qm", "head", "--allow-empty")
        held = os.getcwd()
        os.chdir(room)
        try:
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = baseline_number.main(base)
            return code, said.getvalue()
        finally:
            os.chdir(held)


def cut(number, items):
    return (f"baseline: {number}\ncommit: {'a' * 40}\nitems:\n"
            + "".join(f"  {uid}: {'s' * 12}\n" for uid in items)
            + f"supersedes: {number - 1}\n")


faults = []


def case(name, base_files, head_files, refused, words=(), deleted=()):
    code, output = ran(base_files, head_files, deleted)
    if bool(code) != refused:
        faults.append(f"{name}: expected {'refused' if refused else 'allowed'}"
                      f", got exit {code} and {output!r}")
        return
    for word in words:
        if word not in output:
            faults.append(f"{name}: the message states no {word!r}: {output!r}")


case("a pull request leaving the baseline alone",
     {BASELINE: cut(99, ["GUARD-00000001"]), CODE: "a = 1\n"},
     {CODE: "a = 2\n"},
     refused=False)

case("a baseline cut past the one on the base",
     {BASELINE: cut(99, ["GUARD-00000001"])},
     {BASELINE: cut(100, ["GUARD-00000001", "GUARD-00000002"])},
     refused=False)

case("a baseline cut at the number the base already states",
     {BASELINE: cut(99, ["GUARD-00000001"])},
     {BASELINE: cut(99, ["GUARD-00000001", "GUARD-00000002"])},
     refused=True,
     words=["baseline 99", "merge", "reqctl baseline --generate"])

case("a baseline behind the one on the base",
     {BASELINE: cut(100, ["GUARD-00000001"])},
     {BASELINE: cut(98, ["GUARD-00000002"])},
     refused=True,
     words=["states 100"])

case("a baseline naming no number",
     {BASELINE: cut(99, ["GUARD-00000001"])},
     {BASELINE: "baseline: ninety-nine\nitems: {}\n"},
     refused=True,
     words=["names its number as a whole number", "--check"])

case("a base holding no baseline yet",
     {CODE: "a = 1\n"},
     {BASELINE: cut(1, ["GUARD-00000001"])},
     refused=False)

case("a pull request the base has no baseline to compare against",
     {BASELINE: cut(99, ["GUARD-00000001"]), CODE: "a = 1\n"},
     {CODE: "a = 2\n"},
     refused=False,
     deleted=[BASELINE])

def against(base):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / BASELINE
        spot.parent.mkdir(parents=True, exist_ok=True)
        spot.write_text(cut(99, ["GUARD-00000001"]))
        _git(room, "init", "-q", "-b", "main")
        _git(room, "add", "-A")
        _git(room, "commit", "-qm", "base")
        held = os.getcwd()
        os.chdir(room)
        try:
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                return baseline_number.main(base), said.getvalue()
        finally:
            os.chdir(held)


code, output = against("origin/never-fetched")
if code != 1:
    faults.append("a base ref naming no commit passed the gate, which is a "
                  f"gate that allows where it cannot read: exit {code}")
elif "names no commit here" not in output or "fetch it" not in output:
    faults.append(f"the message states neither the fault nor the remedy: "
                  f"{output!r}")

code, output = ran({BASELINE: cut(99, ["GUARD-00000001"])},
                   {BASELINE: cut(99, ["GUARD-00000002"])})
if "::error::" not in output:
    faults.append(f"a refusal CI cannot annotate: {output!r}")

if baseline_number.cli(["baseline_number.py"]) != 2:
    faults.append("cli() accepted a call naming no base ref")

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("baseline number guard self-test: 0 fault(s)")
sys.exit(0)
