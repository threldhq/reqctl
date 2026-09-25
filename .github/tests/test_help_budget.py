#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import help_budget

faults = []


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def surveyed(text):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "sample.py"
        spot.write_text(text)
        counted, refused = help_budget.survey([str(spot)])
        return counted, [why for _, _, why in refused]


DIRECT = '''
import argparse
parsed = argparse.ArgumentParser()
parsed.add_argument("--one", help="the first thing")
'''

case("a direct help string is counted", surveyed(DIRECT), (1, []))
case("a description is counted too",
     surveyed('import argparse\n'
              'p = argparse.ArgumentParser(description="what this does")\n'),
     (1, []))
case("an f-string help is counted",
     surveyed('import argparse\nCAP = 4\n'
              'p = argparse.ArgumentParser()\n'
              'p.add_argument("--cap", help=f"items (default {CAP})")\n'),
     (1, []))
case("a bare parser with no help costs nothing",
     surveyed('import argparse\n'
              'p = argparse.ArgumentParser()\n'
              'p.add_argument("--one", required=True, metavar="FILE")\n'),
     (0, []))

ROUTED = '''
import argparse


def _command(sub, name, said):
    return sub.add_parser(name, help=said, description=said)


parsed = argparse.ArgumentParser()
sub = parsed.add_subparsers()
_command(sub, "new", "mint an item")
_command(sub, "list", "one line per item")
'''

case("help text routed positionally through a helper is counted, or a "
     "rename hides it from the budget", surveyed(ROUTED), (2, []))

case("a helper given text it cannot read is refused, never skipped",
     surveyed(ROUTED.replace('_command(sub, "new", "mint an item")',
                             '_command(sub, "new", SAID)')),
     (1, ["_command() is given help text this guard cannot read"]))

case("help= built by an expression is refused",
     surveyed('import argparse\n'
              'p = argparse.ArgumentParser()\n'
              'p.add_argument("--one", help="a" + "b")\n'),
     (0, ["help= is built by an expression this guard cannot read"]))

case("help= given an unresolvable name is refused",
     surveyed('import argparse\nSAID = "x"\n'
              'p = argparse.ArgumentParser()\n'
              'p.add_argument("--one", help=SAID)\n'),
     (0, ["help= is given a name this guard cannot resolve to its text"]))

case("a forwarder's own help=name is not double-counted at its definition",
     surveyed(ROUTED)[0], 2)

case("an epilog is counted too",
     surveyed('import argparse\n'
              'p = argparse.ArgumentParser(epilog="a closing paragraph")\n'),
     (1, []))

COLLIDING = '''
import argparse


def build(said):
    argparse.ArgumentParser().add_argument("--x", help=said)


def other():
    said = compute_dynamic_text()
    argparse.ArgumentParser().add_argument("--y", help=said)
'''

case("a name that forwards in one function does not exempt a same-named "
     "local variable in another",
     surveyed(COLLIDING),
     (0, ["help= is given a name this guard cannot resolve to its text"]))


def refused(write):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "sample.py"
        write(spot)
        try:
            help_budget.survey([str(spot)])
        except SystemExit as clean:
            return str(clean).startswith("cannot read")
        return False


case("a file that will not parse is refused cleanly",
     refused(lambda p: p.write_text("def broken(:\n")), True)
case("an undecodable byte is refused cleanly",
     refused(lambda p: p.write_bytes(b'help="\xff\xfe"\n')), True)


def scanned_in(build):
    with tempfile.TemporaryDirectory() as room:
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        build(Path(room))
        held = os.getcwd()
        os.chdir(room)
        try:
            return help_budget.scanned()
        finally:
            os.chdir(held)


def staged(room):
    (room / "kept.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=room, check=True)


case("python is scanned", scanned_in(staged), ["kept.py"])
case("the corpus is left to reqctl",
     scanned_in(lambda room: (staged(room),
                              (room / "requirements").mkdir(),
                              (room / "requirements" / "gen.py")
                              .write_text("x = 1\n"),
                              subprocess.run(["git", "add", "-A"], cwd=room,
                                             check=True))),
     ["kept.py"])


def budget(ceiling):
    with contextlib.redirect_stdout(io.StringIO()):
        return help_budget.main(ceiling)


counted, refusals = help_budget.survey(help_budget.scanned())
case("the repository refuses nothing today", [why for _, _, why in refusals], [])
case("the budget refuses a count above it", budget(counted - 1), 1)
case("the budget refuses a count below it", budget(counted + 1), 1)
case("the budget passes only the count itself", budget(counted), 0)
case("every help string left is reqctl's, the one CLI a session discovers",
     {path for path in help_budget.scanned()
      if help_budget.survey([path])[0]},
     {"reqctl/reqctl/cli.py"})


def unlisted():
    with tempfile.TemporaryDirectory() as room:
        held = os.getcwd()
        os.chdir(room)
        try:
            help_budget.scanned()
        except SystemExit as broken:
            return str(broken)
        finally:
            os.chdir(held)
    return ""


case("a tree git cannot list is refused, not walked as empty",
     "cannot list files" in unlisted(), True)


def refusing_run(build, ceiling):
    with tempfile.TemporaryDirectory() as room:
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        build(Path(room))
        held = os.getcwd()
        os.chdir(room)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = help_budget.main(ceiling)
            return code, out.getvalue()
        finally:
            os.chdir(held)


def unresolvable(room):
    (room / "bad.py").write_text(
        'import argparse\nSAID = "x"\n'
        'p = argparse.ArgumentParser()\n'
        'p.add_argument("--one", help=SAID)\n')
    subprocess.run(["git", "add", "-A"], cwd=room, check=True)


code, output = refusing_run(unresolvable, 0)
case("main() reports a real fault via ::error and refuses", code, 1)
case("main()'s output names the fault",
     "help= is given a name this guard cannot resolve to its text" in output,
     True)

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
