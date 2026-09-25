#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import references

faults = []


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def why(found):
    return [reason for _, _, reason in found]


KNOWN = {"reqctl/reqctl/cli.py", ".github/workflows/ci.yml",
         ".claude/skills/s/synthesis/plan.py", "CLAUDE.md"}
HOLDER = ".claude/skills/s/SKILL.md"

case("a repo-rooted path that resolves passes",
     references.paths_named("see `.github/workflows/ci.yml`", HOLDER, KNOWN), [])
case("a path beside its own file resolves",
     references.paths_named("run `synthesis/plan.py`", HOLDER, KNOWN), [])
case("a path that resolves nowhere is a fault",
     why(references.paths_named("run `synthesis/gone.py`", HOLDER, KNOWN)),
     ["synthesis/gone.py names no file this repository tracks"])
case("a path under the skill's own directory resolves",
     references.paths_named("run `${CLAUDE_SKILL_DIR}/synthesis/plan.py`",
                            HOLDER, KNOWN), [])
case("the skill's directory means nothing outside a skill",
     why(references.paths_named("run `${CLAUDE_SKILL_DIR}/synthesis/plan.py`",
                                ".claude/skills/s/notes.md", KNOWN)),
     ["/synthesis/plan.py names no file this repository tracks"])
case("a repo-rooted path that moved is a fault",
     why(references.paths_named("see `.github/guards/moved.py`", HOLDER, KNOWN)),
     [".github/guards/moved.py names no file this repository tracks"])
case("a bare name is a runtime artifact, not a repo path",
     references.paths_named("you write `words.md` and `run.yaml`", HOLDER, KNOWN), [])
case("a placeholder is not a path",
     references.paths_named("`proposals/NN.md` and `prompts/<job>.md`", HOLDER, KNOWN), [])
case("a placeholder that would otherwise fail is still skipped",
     references.paths_named("`shards/FILE.md`", HOLDER, KNOWN), [])
case("a leading ./ resolves",
     references.paths_named("`./reqctl/reqctl/cli.py`", HOLDER, KNOWN), [])
case("a path inside a url is not a repository reference",
     references.paths_named(
         "see https://github.com/psf/requests/blob/main/setup.py here",
         HOLDER, KNOWN), [])

DEFINED = {"--words", "--found", "--cap"}

case("a flag some parser defines passes",
     references.flags_named("pass `--words` to it", HOLDER, DEFINED), [])
case("a flag no parser defines is a fault",
     why(references.flags_named("pass `--gone` to it", HOLDER, DEFINED)),
     ["--gone is named here but no parser in this repository defines it"])
case("an unbackticked flag is prose, not a claim",
     references.flags_named("pass --gone to it", HOLDER, DEFINED), [])


def faulted(source, defined):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "sample.py"
        spot.write_text(source)
        return why(references.flags_in_faults(str(spot), defined))


case("a fault naming a live flag passes",
     faulted('raise ReqctlError("--words is required")', DEFINED), [])
case("a fault naming a flag no parser defines is caught",
     faulted('raise ReqctlError("--gone is required")', DEFINED),
     ["this fault names --gone, which no parser defines"])
case("an f-string fault is read too",
     faulted('kind = "x"\nraise ReqctlError(f"--gone does not apply to a {kind}")',
             DEFINED),
     ["this fault names --gone, which no parser defines"])
case("a fault naming no flag has nothing to check",
     faulted('raise ReqctlError("the corpus refused this")', DEFINED), [])
case("a call that is not ReqctlError is not read",
     faulted('raise ValueError("--gone")', DEFINED), [])


def harvested(source):
    with tempfile.TemporaryDirectory() as room:
        held = os.getcwd()
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        (Path(room) / "sample.py").write_text(source)
        subprocess.run(["git", "add", "-A"], cwd=room, check=True)
        os.chdir(room)
        try:
            return references.flags_defined()
        finally:
            os.chdir(held)


case("flags are harvested from add_argument",
     harvested('import argparse\n'
               'p = argparse.ArgumentParser()\n'
               'p.add_argument("--one")\n'
               'p.add_argument("--two", required=True)\n'),
     {"--one", "--two"})
case("a positional is not a flag",
     harvested('import argparse\n'
               'p = argparse.ArgumentParser()\n'
               'p.add_argument("source")\n'), set())


def listed_in(build):
    with tempfile.TemporaryDirectory() as room:
        held = os.getcwd()
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        build(Path(room))
        subprocess.run(["git", "add", "-A"], cwd=room, check=True)
        os.chdir(room)
        try:
            return references.listed(), references.tracked()
        finally:
            os.chdir(held)


def corpus(room):
    (room / "kept.md").write_text("x\n")
    (room / "requirements").mkdir()
    (room / "requirements" / "REQ-1.yml").write_text("x: 1\n")


scanned, known = listed_in(corpus)
case("the corpus is not scanned", scanned, ["kept.md"])
case("but the corpus is still somewhere a reference may resolve to",
     known, ["kept.md", "requirements/REQ-1.yml"])

case("this repository resolves every name it states", references.survey(), [])


def unreadable(write):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "sample.md"
        write(spot)
        try:
            references.read(str(spot))
        except SystemExit as clean:
            return str(clean)
        return ""


case("an undecodable byte is refused cleanly, not crashed on",
     unreadable(lambda p: p.write_bytes(b"see \xff\xfe broken bytes\n"))
     .startswith("cannot read"), True)


def unparseable():
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "broken.py"
        spot.write_text("def broken(:\n")
        try:
            references.parsed(str(spot))
        except SystemExit as clean:
            return str(clean)
        return ""


case("a file that will not parse is refused cleanly, not crashed on",
     unparseable().startswith("cannot read"), True)


def unlisted():
    with tempfile.TemporaryDirectory() as room:
        held = os.getcwd()
        os.chdir(room)
        try:
            references.tracked()
        except SystemExit as broken:
            return str(broken)
        finally:
            os.chdir(held)
    return ""


case("a tree git cannot list is refused, not walked as empty",
     "cannot list files" in unlisted(), True)


def surveyed_repo(build):
    with tempfile.TemporaryDirectory() as room:
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        build(Path(room))
        subprocess.run(["git", "add", "-A"], cwd=room, check=True)
        held = os.getcwd()
        os.chdir(room)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = references.main()
            return code, out.getvalue()
        finally:
            os.chdir(held)


def broken_reference(room):
    (room / "NOTES.md").write_text("see `missing/gone.py` for details\n")


code, output = surveyed_repo(broken_reference)
case("main() reports a real fault via ::error and refuses", code, 1)
case("main()'s output names the fault",
     "missing/gone.py names no file this repository tracks" in output, True)

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
