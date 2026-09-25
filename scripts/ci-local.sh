#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: scripts/ci-local.sh [--base REF] [--self-test]

Runs every step of the check job in .github/workflows/ci.yml, in the order the
workflow states them, and reports pass or fail for each. The list is read from
the workflow itself, so it cannot drift from what CI runs. Exits non-zero if
any step failed.

  --base REF    the branch the change is measured against (default: main)
  --self-test   check this runner against workflows written for it

One step is not run here. reqportal's Playwright suite installs a browser with
apt, which a local checkout must not do; Chromium is already installed. Run it
separately whenever anything under reqportal/ changes:

  cd reqportal && npm ci && npm test
USAGE
}

mode=run
base=main
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || { usage >&2; exit 2; }; base="$2"; shift 2 ;;
    --self-test) mode=self-test; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python=python3
if [ -x "$root/.venv/bin/python" ]; then
  python="$root/.venv/bin/python"
  PATH="$root/.venv/bin:$PATH"
  export PATH
fi

exec "$python" - "$mode" "$base" <<'RUNNER'
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/ci.yml")
JOB = "check"
SEPARATE = "Portal tests"
EXPRESSION = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
COMPARISON = re.compile(r"^([\w.-]+)\s*==\s*'([^']*)'$")
EVENT = "pull_request"


def steps_of(workflow):
    try:
        held = yaml.safe_load(workflow.read_text())
    except (OSError, yaml.YAMLError) as broken:
        raise SystemExit(f"cannot read {workflow}: {broken}")
    try:
        found = held["jobs"][JOB]["steps"]
    except (KeyError, TypeError):
        found = None
    if not isinstance(found, list) or not found:
        raise SystemExit(f"{workflow}: no {JOB} job with steps to run")
    return found


def resolve(text, known, where):
    def taken(found):
        wanted = found.group(1)
        if wanted not in known:
            raise SystemExit(f"{where}: cannot resolve {found.group(0)} -- "
                             "teach this runner the expression")
        return known[wanted]
    return EXPRESSION.sub(taken, str(text))


def holds(condition, known, where):
    found = COMPARISON.match(resolve(condition, known, where).strip())
    if found is None:
        raise SystemExit(f"{where}: reads the condition {condition!r}, which "
                         "is not <context> == 'value' -- teach this runner "
                         "the shape")
    left = found.group(1)
    if left not in known:
        raise SystemExit(f"{where}: the condition reads {left}, which no step "
                         "has produced")
    return known[left] == found.group(2)


def outputs_of(path, step_id, known):
    for line in path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep:
            known[f"steps.{step_id}.outputs.{name.strip()}"] = value.strip()


def main(base, workflow):
    room = tempfile.mkdtemp(prefix="ci-local-")
    known = {"github.event_name": EVENT, "github.base_ref": base}
    passed, failed, skipped = [], [], []

    for at, step in enumerate(steps_of(workflow), 1):
        name = step.get("name") or step.get("uses") or f"step {at}"
        where = f"{workflow}: {name}"
        script = step.get("run")
        why = None
        if script is None:
            why = "an action, not a shell step"
        elif "if" in step and not holds(step["if"], known, where):
            why = f"{step['if']} is false"
        elif name == SEPARATE:
            why = ("it installs a browser with apt; run it separately: "
                   "cd reqportal && npm ci && npm test")
        if why is not None:
            skipped.append((name, why))
            print(f"skip  {name}  ({why})")
            continue

        written = Path(room) / f"output-{at}"
        written.touch()
        held = dict(os.environ)
        held.update(GITHUB_OUTPUT=str(written), RUNNER_TEMP=room,
                    GITHUB_EVENT_NAME=EVENT)
        for key, value in (step.get("env") or {}).items():
            held[str(key)] = resolve(value, known, where)

        started = time.monotonic()
        done = subprocess.run(
            ["bash", "-euo", "pipefail", "-c",
             resolve(script, known, where)],
            cwd=Path.cwd() / str(step.get("working-directory") or "."),
            env=held, check=False)
        spent = time.monotonic() - started
        if step.get("id"):
            outputs_of(written, str(step["id"]), known)
        if done.returncode:
            failed.append((name, done.returncode))
            print(f"FAIL  {name}  ({spent:.1f}s, exit {done.returncode})")
        else:
            passed.append(name)
            print(f"ok    {name}  ({spent:.1f}s)")

    print(f"\n{len(passed)} passed, {len(failed)} failed, "
          f"{len(skipped)} skipped")
    for name, why in skipped:
        print(f"  skipped  {name}: {why}")
    for name, code in failed:
        print(f"  FAILED   {name}: exit {code}")
    return 1 if failed else 0


def written(steps):
    return {str(WORKFLOW): yaml.safe_dump({"jobs": {JOB: {"steps": steps}}},
                                          sort_keys=False)}


def driven(files, base="main"):
    buffer = io.StringIO()
    home = Path.cwd()
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        os.chdir(root)
        try:
            with contextlib.redirect_stdout(buffer):
                code = main(base, root / WORKFLOW)
        except SystemExit as refusal:
            code = str(refusal)
        finally:
            os.chdir(home)
    return code, buffer.getvalue().splitlines() + [str(code)]


def met(part, said):
    if isinstance(part, tuple):
        at, text = part
        return at < len(said) and text in said[at]
    if part.startswith("!"):
        return not any(part[1:] in one for one in said)
    return any(part in one for one in said)


def self_test():
    cases = [
        ("the steps run in the order the workflow states them",
         written([{"name": "first", "run": "true"},
                  {"name": "second", "run": "true"}]),
         "main", [(0, "ok    first"), (1, "ok    second"),
                  "2 passed, 0 failed, 0 skipped"]),
        ("a step that is an action is named as skipped, not run",
         written([{"uses": "actions/checkout@v4"}]),
         "main", [(0, "skip  actions/checkout@v4  (an action, not a shell "
                      "step)")]),
        ("a step whose condition is false is skipped",
         written([{"name": "held", "run": "true",
                   "if": "github.event_name == 'push'"}]),
         "main", [(0, "skip  held  (github.event_name == 'push' is false)"),
                  "0 passed, 0 failed, 1 skipped",
                  "  skipped  held: github.event_name == 'push' is false"]),
        ("a step whose condition is true runs",
         written([{"name": "held", "run": "true",
                   "if": "github.event_name == 'pull_request'"}]),
         "main", ["ok    held", "1 passed, 0 failed, 0 skipped"]),
        ("an output a step wrote settles the condition of a later one",
         written([{"name": "touch", "id": "touched",
                   "run": 'echo "held=true" >> "$GITHUB_OUTPUT"'},
                  {"name": "gated", "run": "true",
                   "if": "steps.touched.outputs.held == 'true'"}]),
         "main", ["ok    gated", "2 passed, 0 failed, 0 skipped"]),
        ("the branch the change is measured against reaches the step reading it",
         written([{"name": "held", "run": '[ "$BASE" = trunk ]',
                   "env": {"BASE": "${{ github.base_ref }}"}}]),
         "trunk", ["ok    held", "1 passed, 0 failed"]),
        ("a step runs in the directory the workflow states",
         {**written([{"name": "held", "working-directory": "sub",
                      "run": '[ "$(basename "$PWD")" = sub ]'}]),
          "sub/keep": ""},
         "main", ["ok    held", "1 passed, 0 failed"]),
        ("a failing step is named and the run fails with it",
         written([{"name": "held", "run": "false"}]),
         "main", ["FAIL  held", "exit 1", "0 passed, 1 failed",
                  "FAILED   held: exit 1"]),
        ("an expression the runner cannot read stops it",
         written([{"name": "held", "run": "echo ${{ github.sha }}"}]),
         "main", ["cannot resolve ${{ github.sha }} -- teach this runner the "
                  "expression", "!ok    held"]),
        ("a condition shape the runner cannot read stops it",
         written([{"name": "held", "run": "true", "if": "always()"}]),
         "main", ["reads the condition 'always()', which is not <context> "
                  "== 'value' -- teach this runner the shape", "!ok    held"]),
        ("a condition naming an output no step produced stops the runner",
         written([{"name": "held", "run": "true",
                   "if": "steps.ghost.outputs.held == 'true'"}]),
         "main", ["the condition reads steps.ghost.outputs.held, which no "
                  "step has produced", "!ok    held"]),
        ("the Playwright suite is named as separate, not run",
         written([{"name": SEPARATE, "run": "false"}]),
         "main", [(0, "skip  Portal tests  (it installs a browser with apt; "
                      "run it separately: cd reqportal && npm ci && npm "
                      "test)"), "!FAIL"]),
        ("a workflow naming no check job stops the runner",
         {str(WORKFLOW): yaml.safe_dump({"jobs": {"other": {"steps": []}}})},
         "main", ["no check job with steps to run"]),
        ("a workflow that is not YAML stops the runner",
         {str(WORKFLOW): "jobs: [\n"},
         "main", ["cannot read"]),
    ]
    failed = 0
    for label, files, base, expected in cases:
        code, said = driven(files, base)
        wanted = all(met(part, said) for part in expected)
        print(f"{'ok  ' if wanted else 'FAIL'}  {label}")
        failed += 0 if wanted else 1
    print(f"{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if sys.argv[1] == "self-test":
    sys.exit(self_test())
sys.exit(main(sys.argv[2], WORKFLOW))
RUNNER
