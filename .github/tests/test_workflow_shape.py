#!/usr/bin/env python3
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import workflow_shape

faults = []
SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"

SOUND = f"""
permissions:
  contents: read
jobs:
  check:
    steps:
      - uses: actions/checkout@{SHA}
      - run: pytest
"""


def case(name, text, wanted, where="w.yml", gates=None):
    found = workflow_shape.faults(text, where, gates)
    hit = any(wanted in fault for fault in found)
    if hit != bool(wanted):
        faults.append(f"{name}: expected {wanted!r}, got {found}")


case("a sound workflow passes", SOUND, "")

case("a tag is refused", SOUND.replace(f"@{SHA}", "@v7.0.1"), "not pinned to a commit")
case("a branch is refused", SOUND.replace(f"@{SHA}", "@main"), "not pinned to a commit")
case("a short sha is refused", SOUND.replace(SHA, SHA[:12]), "not pinned to a commit")

case("a second job is refused",
     SOUND + "  publish:\n    steps:\n      - run: true\n", "not 1")
case("no job is refused", SOUND.replace("jobs:", "unrelated:"), "0 jobs")

case("write permission is refused",
     SOUND.replace("contents: read", "contents: write"),
     "not {'contents': 'read'}")
case("absent permission is refused",
     SOUND.replace("permissions:\n  contents: read\n", ""),
     "not {'contents': 'read'}")

case("a file that is not a mapping is refused", "- a\n- b\n", "is not a mapping")
case("a file that is not YAML is refused", "jobs: [unclosed\n", "is not YAML")
case("jobs that is not a mapping is refused",
     "permissions:\n  contents: read\njobs: [a, b]\n", "jobs is not a mapping")

case("a job calling a reusable workflow on a branch is refused",
     SOUND.replace(f"      - uses: actions/checkout@{SHA}\n      - run: pytest\n",
                   "      - run: pytest\n").replace(
         "  check:\n", "  check:\n    uses: o/e/.github/workflows/r.yml@main\n"),
     "not pinned to a commit")
case("a job widening the workflow's permission is refused",
     SOUND.replace("  check:\n",
                   "  check:\n    permissions:\n      contents: write\n"),
     "widening the workflow")

WIELDING = SOUND.replace("      - run: pytest\n",
                         "      - run: gh pr create\n"
                         "        env:\n"
                         "          GH_TOKEN: ${{ secrets.CORPUS_WRITE_TOKEN }}\n")

case("a workflow reaching for a secret is refused", WIELDING,
     "reaches the secrets context")
case("the allowlisted workflow may wield one", WIELDING, "", "corpus-write.yml")
case("an allowlisted workflow still reads only",
     WIELDING.replace("contents: read", "contents: write"),
     "not {'contents': 'read'}", "corpus-write.yml")
case("an allowlisted workflow fired by a pull request is refused",
     "on:\n  pull_request:\n" + WIELDING, "fires on pull_request",
     "corpus-write.yml")
case("an allowlisted workflow dispatched by hand passes",
     "on:\n  workflow_dispatch:\n" + WIELDING, "", "corpus-write.yml")
case("a trigger list is read too",
     "on: [push, pull_request_target]\n" + WIELDING, "fires on pull_request_target",
     "corpus-write.yml")

for spelling in ("${{ secrets['CORPUS_WRITE_TOKEN'] }}",
                 '${{ secrets["CORPUS_WRITE_TOKEN"] }}',
                 "${{ toJSON(secrets) }}",
                 "${{ secrets }}"):
    case(f"a secret spelled {spelling} is still seen",
         WIELDING.replace("${{ secrets.CORPUS_WRITE_TOKEN }}", spelling),
         "reaches the secrets context")

case("a secret finding survives a malformed jobs key",
     "permissions:\n  contents: read\njobs: [a, b]\n"
     "steps: ${{ secrets.X }}\n", "reaches the secrets context")

case("an `on` that is neither list nor mapping does not crash",
     "on: true\n" + WIELDING, "", "corpus-write.yml")

if workflow_shape.triggers({True: {"workflow_dispatch": None}}) != {"workflow_dispatch"}:
    faults.append("triggers: YAML reads a bare `on:` as True and it was missed")

HASHED = "      - run: pip install --require-hashes -r lock.txt\n"
EDITABLE = "      - run: pip install -e reqctl --no-deps --no-build-isolation\n"

case("a hashed lockfile install passes", SOUND + HASHED, "")
case("an editable install outside build isolation passes", SOUND + EDITABLE, "")
case("a lockfile install without --require-hashes is refused",
     SOUND + HASHED.replace("--require-hashes ", ""), "--require-hashes")
case("an editable install with build isolation is refused",
     SOUND + EDITABLE.replace(" --no-build-isolation", ""),
     "--no-build-isolation")
case("an editable install is not asked for --require-hashes",
     SOUND + EDITABLE, "")
case("a plain install is asked for neither",
     SOUND + "      - run: pip install --upgrade pip\n", "")
case("both faults are named at once",
     SOUND + "      - run: pip install -e . -r lock.txt\n", "--require-hashes")
case("both faults are named at once, the second too",
     SOUND + "      - run: pip install -e . -r lock.txt\n", "--no-build-isolation")

CONTINUED = ("      - run: |\n"
             "          pip install \\\n"
             "            -r lock.txt\n")

case("a lockfile install split across a continued line is still asked "
     "for --require-hashes", SOUND + CONTINUED, "--require-hashes")
case("a hashed install split across a continued line passes",
     SOUND + CONTINUED.replace("-r lock.txt", "--require-hashes -r lock.txt"),
     "")

with tempfile.TemporaryDirectory() as room:
    outside = os.getcwd()
    os.chdir(room)
    try:
        (Path(room) / ".github" / "workflows").mkdir(parents=True)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = workflow_shape.main()
    finally:
        os.chdir(outside)
if not (code and "holds no workflow" in out.getvalue()):
    faults.append(f"a directory holding no workflow is refused: {out.getvalue()!r}")

GATES = {"taxonomy"}
VALIDATE = "      - name: Corpus is valid\n        run: reqctl validate\n"
RENAMED = "      - name: The merged corpus holds\n        run: reqctl validate\n"
GATE = "      - name: Taxonomy\n        run: python .github/guards/taxonomy.py\n"
PLAIN = "      - name: Help budget\n        run: python .github/guards/help_budget.py\n"
BASELINE = "      - name: Baseline\n        run: reqctl baseline --check\n"
MODULE = "      - name: Trace\n        run: python -m reqctl trace\n"
INLINE = ("      - name: Inline\n        run: |\n          python3 - <<'X'\n"
          "          import reqctl\n          X\n")
LOCAL = "      - name: Composite\n        uses: ./.github/actions/gate\n"


def ordering(name, body, wanted):
    case(name, SOUND + body, wanted, gates=GATES)


ordering("a gate after validate passes", VALIDATE + GATE, "")
ordering("a gate before validate is refused, so none judges a corpus reqctl "
         "has not accepted", GATE + VALIDATE, "reads the corpus before")
ordering("a gate that does not read the corpus is unconstrained",
         PLAIN + VALIDATE, "")
ordering("a reqctl command other than validate is refused before it",
         BASELINE + VALIDATE, "reads the corpus before")
ordering("reqctl reached as a module is refused before it",
         MODULE + VALIDATE, "reads the corpus before")
ordering("a step importing reqctl in its own body is refused before it",
         INLINE + VALIDATE, "reads the corpus before")
ordering("a local composite action is refused before it, since what it runs "
         "cannot be read here", LOCAL + VALIDATE, "reads the corpus before")
ordering("validate does not flag itself", VALIDATE + VALIDATE, "")
ordering("the acceptor is the command, not the step's name, so renaming it "
         "does not retire the check", GATE + RENAMED, "reads the corpus before")
ordering("a gate with no step accepting the corpus is refused", GATE,
         "no step accepts")
ordering("a corpus read that runs no gate needs no acceptance, as a view does",
         BASELINE, "")
ordering("continue-on-error is refused, since a failed gate would leave the "
         "job green",
         VALIDATE + GATE.rstrip("\n") + "\n        continue-on-error: true\n",
         "continues on error")

DERIVED = workflow_shape.corpus_gates()
for stem in ("taxonomy", "guard_binding", "citations", "comment_budget"):
    if stem not in DERIVED:
        faults.append(f"corpus_gates omits {stem}, which reaches reqctl")
for stem in ("help_budget", "workflow_shape"):
    if stem in DERIVED:
        faults.append(f"corpus_gates names {stem}, which does not reach reqctl")
unreadable = Path(tempfile.mkdtemp())
(unreadable / "broken.py").write_bytes(b"\xff\xfe not utf-8\n")
if "broken" not in workflow_shape.corpus_gates(unreadable):
    faults.append("corpus_gates reads a guard it cannot decode as reaching "
                  "nothing, so an unreadable gate escapes the ordering check")
if workflow_shape.corpus_gates(Path(tempfile.mkdtemp())) != set():
    faults.append("corpus_gates invents a gate where the folder holds none")

with tempfile.TemporaryDirectory() as room:
    outside = os.getcwd()
    os.chdir(room)
    try:
        made = Path(room) / ".github" / "workflows"
        made.mkdir(parents=True)
        (made / "w.yml").write_text(SOUND)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = workflow_shape.main()
    finally:
        os.chdir(outside)
if not (code and "holds no gate that reaches reqctl" in out.getvalue()):
    faults.append("a tree whose guards cannot be found is accepted, so the "
                  f"ordering check holds nothing and says nothing: {out.getvalue()!r}")

held = workflow_shape.faults(Path(".github/workflows/ci.yml").read_text(), "ci.yml")
if held:
    faults.append(f"this repository's own workflow: {held}")

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
