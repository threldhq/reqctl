#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GATES = ROOT / ".github" / "workflows" / "corpus-gates.yml"
VENV = ROOT / ".venv" / "bin"
EXPRESSION = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
EQUALITY = re.compile(r"^([\w.]+)\s*(==|!=)\s*'([^']*)'$")
PROVISIONS = re.compile(r"\bpip install\b|install-gitleaks")
NOT_FOUND = 127
MISSING = re.compile(r"([\w./-]+): command not found")

PASS, FAIL, SKIP = "pass", "FAIL", "skip"
# @req> GUARD-63869848@V9lllz-dAIsM ykvsgh
DIRTY = ("the working tree holds uncommitted changes, and what this touches was "
         "read from committed history only -- commit first, or pass --event "
         "workflow_dispatch to run every step")


def caveat(status):
    # @req> GUARD-38013284@PVuWil-RXTeh gdabnx
    if status.returncode:
        sys.exit("cannot tell whether the working tree is committed: "
                 + (status.stderr.strip()
                    or f"git status exited {status.returncode}"))
    return DIRTY if status.stdout.strip() else ""


def loaded(path):
    try:
        text = path.read_text()
    except OSError as unreadable:
        sys.exit(f"{path.relative_to(ROOT)}: {unreadable}")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as unreadable:
        sys.exit(f"{path.relative_to(ROOT)}: {unreadable}")


def steps_of(doc):
    held = []
    for job, spec in (doc.get("jobs") or {}).items():
        for step in spec.get("steps") or []:
            if step.get("run"):
                held.append((job, step))
    return held


def resolve(text, context):
    unresolved = []

    def swap(found):
        key = found.group(1)
        if key in context:
            return context[key]
        unresolved.append(key)
        return found.group(0)

    return EXPRESSION.sub(swap, str(text)), unresolved


# @req> GUARD-17042135@vQjU7Tanb64t i5t6nn
# @req> GUARD-37227142@C2NMyItFzo8_ dfoc3s
# @req> GUARD-25040771@FKlsQswXD4d2 eom5zx
def condition_holds(expression, context):
    resolved, unresolved = resolve(expression, context)
    if unresolved:
        return None, f"condition names {', '.join(sorted(set(unresolved)))}"
    match = EQUALITY.match(resolved.strip())
    if match:
        held = context.get(match.group(1), match.group(1)) == match.group(3)
        return held if match.group(2) == "==" else not held, ""
    return None, f"condition is not a form this runner evaluates: {resolved}"


# @req> GUARD-70807721@hKTqJj264iEQ xji242
# @req> GUARD-50851969@qJd_L0QWXKby kldhgm
def environment(step, context):
    settings, unresolved = {}, []
    for key, value in (step.get("env") or {}).items():
        resolved, missing = resolve(value, context)
        settings[key] = resolved
        unresolved += missing
    return settings, unresolved


# @req> GUARD-32116873@b8Rc9YBATiqc ktyqch
# @req> GUARD-35429063@85cSzafV3AYM koamhn
def run(command, settings, cwd=ROOT):
    env = dict(os.environ)
    env["PATH"] = f"{VENV}{os.pathsep}{env.get('PATH', '')}"
    env.update(settings)
    return subprocess.run(["bash", "-e", "-c", command], cwd=cwd, env=env,
                          capture_output=True, text=True)


# @req> GUARD-22790982@C_rq6FF8Jpo2 bhdeig
# @req> GUARD-30060482@DgZdAWv14AwM w62x7s
# @req> GUARD-83667494@M9oACj7Jx7N- dj3zxa
# @req> GUARD-70807721@hKTqJj264iEQ lli7h5
# @req> GUARD-63780217@XDEsTlbWUWib nxiqug
def touched_outputs(doc, context):
    for _, step in steps_of(doc):
        if step.get("id") != "touched":
            continue
        with tempfile.NamedTemporaryFile("w+", delete=False) as sink:
            record = sink.name
        settings, unresolved = environment(step, context)
        if unresolved:
            return {}, f"cannot resolve {', '.join(sorted(set(unresolved)))}"
        settings["GITHUB_OUTPUT"] = record
        settings["GITHUB_EVENT_NAME"] = context["github.event_name"]
        done = run(step["run"], settings)
        found = {}
        for line in Path(record).read_text().splitlines():
            key, _, value = line.partition("=")
            if key:
                found[f"steps.touched.outputs.{key.strip()}"] = value.strip()
        os.unlink(record)
        if done.returncode != 0:
            return found, done.stderr.strip().splitlines()[-1:] or ["failed"]
        return found, ""
    return {}, "no step with id 'touched'"


# @req> GUARD-20035007@EUUCqO_GisrK ujjzel
def report(state, name, note):
    tail = f"  ({note})" if note else ""
    print(f"  {state:<4}  {name}{tail}")


# @req> GUARD-10822746@5q3_dsWRmBCD ptxves
# @req> GUARD-11120217@4KaCRrOB_6-L ew6je4
# @req> GUARD-13736079@VPQ2CgYQfHvS bkpdjy
# @req> GUARD-17042135@vQjU7Tanb64t chava2
# @req> GUARD-37227142@C2NMyItFzo8_ qta3if
# @req> GUARD-25040771@FKlsQswXD4d2 uub6fm
# @req> GUARD-50851969@qJd_L0QWXKby p5jgij
# @req> GUARD-69135696@SiwUNCQBSY6Y k7h2k2
# @req> GUARD-43143362@loXh8wpGI7bY x6req7
# @req> GUARD-82603422@G-oWXFmFwF5y uelz7u
# @req> GUARD-61050843@spBS97MzI2uA rhq23g
# @req> GUARD-99256924@_UL344Vx8fwB 6reuag
# @req> GUARD-99517521@WVqMoWW75tr_ mcmyxk
# @req> GUARD-96835839@8aAJKGCsRpfI ihtrik
# @req> GUARD-51812681@d0J0sbapRL01 3gfiyl
# @req> GUARD-31362751@_U8NAPJBxtsf nqlfvv
# @req> GUARD-15686102@QkQ-CEAbWBgS v3mvrz
def main(argv=None):
    parsed = argparse.ArgumentParser()
    parsed.add_argument("--base", default="main", metavar="REF")
    parsed.add_argument("--event", default="pull_request", metavar="NAME")
    args = parsed.parse_args(argv)

    doc, gates = loaded(WORKFLOW), loaded(GATES)
    context = {
        "github.base_ref": args.base,
        "github.event_name": args.event,
        "inputs.reqctl": "",
    }
    found, trouble = touched_outputs(doc, context)
    if trouble:
        sys.exit(f"cannot compute what this change touches: {trouble}")
    context.update(found)

    counts = {PASS: 0, FAIL: 0, SKIP: 0}
    failures = []
    print(f"{WORKFLOW.relative_to(ROOT)} and {GATES.relative_to(ROOT)}: "
          f"base={args.base} event={args.event}")
    changed = {key.rsplit(".", 1)[-1] for key, value in found.items()
               if value == "true"}
    print(f"this tree touches: {', '.join(sorted(changed)) or 'nothing'}")
    # @req+ GUARD-63869848@V9lllz-dAIsM 5xmujr
    uncommitted = caveat(run("git status --porcelain", {}))
    print(f"{uncommitted}\n" if uncommitted else "")
    # @req- 5xmujr

    for job, step in steps_of(doc) + steps_of(gates):
        name = step.get("name") or step.get("id") or "unnamed"
        if step.get("id") == "touched":
            counts[PASS] += 1
            report(PASS, name, "ran first, to decide what CI would run")
            continue
        if step.get("if") is not None:
            holds, why = condition_holds(step["if"], context)
            if holds is None:
                counts[SKIP] += 1
                report(SKIP, name, why)
                continue
            if not holds:
                counts[SKIP] += 1
                report(SKIP, name, "CI would not run this step for this tree")
                continue
        settings, unresolved = environment(step, context)
        if unresolved:
            counts[SKIP] += 1
            report(SKIP, name,
                   f"env names {', '.join(sorted(set(unresolved)))}")
            continue
        if PROVISIONS.search(step["run"]):
            counts[SKIP] += 1
            report(SKIP, name, "provisions the environment")
            continue
        settings.setdefault("GITHUB_EVENT_NAME", context["github.event_name"])
        # @req+ GUARD-29439031@Yrqmt10udLze e2sjnw
        where = step.get("working-directory")
        done = run(step["run"], settings, ROOT / where if where else ROOT)
        # @req- e2sjnw
        if done.returncode == NOT_FOUND:
            counts[SKIP] += 1
            absent = MISSING.search(done.stderr or "")
            report(SKIP, name, f"not installed here: {absent.group(1)}"
                   if absent else "a command it runs is not installed here")
            continue
        if done.returncode != 0:
            counts[FAIL] += 1
            report(FAIL, name, f"exit {done.returncode}")
            failures.append((name, done))
            continue
        counts[PASS] += 1
        report(PASS, name, "")

    for name, done in failures:
        print(f"\n=== {name} ===")
        body = (done.stdout or "") + (done.stderr or "")
        for line in body.strip().splitlines()[-25:]:
            print(f"  {line}")

    print(f"\n{counts[PASS]} passed, {counts[FAIL]} failed, "
          f"{counts[SKIP]} skipped")
    if counts[PASS] + counts[FAIL] < 2:
        print("a run that executed nothing has not verified anything")
        return 1
    return 1 if counts[FAIL] else 0


# @req> GUARD-10822746@5q3_dsWRmBCD erdmt6
if __name__ == "__main__":
    sys.exit(main())
