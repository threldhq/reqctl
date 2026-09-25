#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import travel_alone

ITEM = """status: approved
text: The product shall archive a record.
assessed:
  PARAM-00000001.5: {pin}
"""
SCHEMA = "title: {title}\ntype: object\n"


def _git(cwd, *args):
    done = subprocess.run(
        ["git", "-c", "gc.auto=0", "-c", "user.email=t@t",
         "-c", "user.name=t", *args],
        cwd=cwd, capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def classify(base_files, head_files, deleted=()):
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
        _git(room, "commit", "-qm", "head")
        held = os.getcwd()
        os.chdir(room)
        try:
            return travel_alone.classify(base)
        finally:
            os.chdir(held)


REQ = "requirements/reqs/REQ-00000001.yml"
BASELINE = travel_alone.DERIVED
CODE = "reqctl/reqctl/corpus.py"
STAMPS = "items:\n  REQ-00000001: {stamp}\n"
CITING = ("# @req" "+ REQ-00000001@{stamp} abcdef\nheld = 0\n"
          "# @req" "- abcdef\n")
SINGLE = "# @req" "> REQ-00000001@{stamp} abcdef\nheld = 0\n"
WAS = "a" * 12
NOW = "b" * 12
faults = []


def case(name, base_files, head_files, refused, deleted=()):
    content, other, _ = classify(base_files, head_files, deleted)
    blocked = bool(content and other)
    if blocked != refused:
        faults.append(f"{name}: expected {'refused' if refused else 'allowed'}, "
                      f"got content={content} other={other}")


case("code alone",
     {CODE: "a = 1\n"}, {CODE: "a = 2\n"}, refused=False)

case("a requirement alone",
     {REQ: ITEM.format(pin="aaa")},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete")},
     refused=False)

case("a requirement beside code",
     {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete"), CODE: "a = 2\n"},
     refused=True)

case("pins beside code",
     {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
     {REQ: ITEM.format(pin="bbb"), CODE: "a = 2\n"},
     refused=False)

case("pins and a statement beside code",
     {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
     {REQ: ITEM.format(pin="bbb").replace("archive", "delete"), CODE: "a = 2\n"},
     refused=True)

case("a requirement added beside code",
     {CODE: "a = 1\n"},
     {REQ: ITEM.format(pin="aaa"), CODE: "a = 2\n"},
     refused=True)

case("a requirement deleted beside code",
     {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
     {CODE: "a = 2\n"}, deleted=[REQ],
     refused=True)

case("a requirement that will not parse, beside code",
     {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
     {REQ: "text: [unclosed\n", CODE: "a = 2\n"},
     refused=True)

case("a requirement that will not parse on either side, beside code",
     {REQ: "text: [unclosed\n", CODE: "a = 1\n"},
     {REQ: "text: [still unclosed\n", CODE: "a = 2\n"},
     refused=True)

case("a schema beside code",
     {"requirements/schemas/x.schema.yaml": SCHEMA.format(title="A"),
      CODE: "a = 1\n"},
     {"requirements/schemas/x.schema.yaml": SCHEMA.format(title="B"),
      CODE: "a = 2\n"},
     refused=True)

case("the baseline beside the code that cut it",
     {BASELINE: STAMPS.format(stamp="aaa"), CODE: "a = 1\n"},
     {BASELINE: STAMPS.format(stamp="bbb"), CODE: "a = 2\n"},
     refused=False)

case("a re-pin beside the statement that moved it",
     {REQ: ITEM.format(pin="aaa"), CODE: CITING.format(stamp=WAS)},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete"),
      CODE: CITING.format(stamp=NOW)},
     refused=False)

case("a re-pin of a one-comment citation beside the statement that moved it",
     {REQ: ITEM.format(pin="aaa"), CODE: SINGLE.format(stamp=WAS)},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete"),
      CODE: SINGLE.format(stamp=NOW)},
     refused=False)

case("a re-pin and a code change beside the statement",
     {REQ: ITEM.format(pin="aaa"), CODE: CITING.format(stamp=WAS)},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete"),
      CODE: CITING.format(stamp=NOW) + "held = 1\n"},
     refused=True)

case("a citation added beside the statement",
     {REQ: ITEM.format(pin="aaa"), CODE: CITING.format(stamp=WAS)},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete"),
      CODE: CITING.format(stamp=WAS) + CITING.format(stamp=NOW)},
     refused=True)

case("a statement beside the baseline and code",
     {REQ: ITEM.format(pin="aaa"), BASELINE: STAMPS.format(stamp="aaa"),
      CODE: "a = 1\n"},
     {REQ: ITEM.format(pin="aaa").replace("archive", "delete"),
      BASELINE: STAMPS.format(stamp="bbb"), CODE: "a = 2\n"},
     refused=True)


def usage():
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        code = travel_alone.cli(["travel_alone.py"])
    return code, out.getvalue().strip()


code, message = usage()
if (code, message) != (2, "usage: travel_alone.py BASE_REF"):
    faults.append(f"no argument: expected (2, 'usage: travel_alone.py "
                  f"BASE_REF'), got {(code, message)}")


def run_main(base_files, head_files, deleted=()):
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
        _git(room, "commit", "-qm", "head")
        held = os.getcwd()
        os.chdir(room)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = travel_alone.main(base)
            return code, out.getvalue()
        finally:
            os.chdir(held)


code, output = run_main(
    {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
    {REQ: ITEM.format(pin="aaa").replace("archive", "delete"), CODE: "a = 2\n"})
if code != 1:
    faults.append(f"main() refusing a requirement beside code: expected 1, "
                  f"got {code}")
if "split the requirement change out" not in output:
    faults.append("main()'s refusal does not name the split: "
                  f"{output!r}")

code, output = run_main({CODE: "a = 1\n"}, {CODE: "a = 2\n"})
if (code, output) != (0, ""):
    faults.append(f"main() passing code alone: expected (0, ''), "
                  f"got {(code, output)}")

TRAVELS = "pins only, travelling with what moved them"

code, output = run_main(
    {REQ: ITEM.format(pin="aaa"), CODE: "a = 1\n"},
    {REQ: ITEM.format(pin="bbb"), CODE: "a = 2\n"})
if (code, f"{TRAVELS}: {REQ}" in output) != (0, True):
    faults.append(f"main() naming the pins that travel: got {(code, output)!r}")

code, output = run_main(
    {REQ: ITEM.format(pin="aaa"), CODE: CITING.format(stamp=WAS)},
    {REQ: ITEM.format(pin="aaa").replace("archive", "delete"),
     CODE: CITING.format(stamp=NOW)})
if (code, f"{TRAVELS}: {CODE}" in output) != (0, True):
    faults.append(f"main() naming the re-pin that travels: got {(code, output)!r}")

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
