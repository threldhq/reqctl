#!/usr/bin/env python3
import re
import sys
from pathlib import Path

import yaml

WORKFLOWS = Path(".github/workflows")
GUARDS = Path(".github/guards")
PINNED = re.compile(r"@[0-9a-f]{40}$")
PIP = re.compile(r"(?m)^.*?(pip install\b.*)$")
CONTINUED = re.compile(r"\\\n[ \t]*")
READ_ONLY = {"contents": "read"}
SECRET = re.compile(r"\bsecrets\b")
WIELDS = {"corpus-write.yml", "corpus-view.yml"}
GATE = re.compile(r"\.github/guards/([\w-]+)\.py")
REQCTL = re.compile(r"(?m)^\s*reqctl\s+([\w-]+)|-m\s+reqctl\s+([\w-]+)")
IMPORTS = re.compile(r"(?m)^\s*(?:from reqctl import|import reqctl)\b"
                     r"|[\"']reqctl[\"']")
ACCEPTS = re.compile(r"(?m)^\s*reqctl\s+validate\b")
VALIDATES = "reqctl validate"
UNTRUSTED = {"pull_request", "pull_request_target"}
JOBS = 1


def triggers(held):
    fired = held.get(True, held.get("on")) or {}
    if isinstance(fired, str):
        return {fired}
    return set(fired) if isinstance(fired, (dict, list)) else set()


def corpus_gates(folder=GUARDS):
    held = set()
    for path in sorted(folder.glob("*.py")):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            held.add(path.stem)
            continue
        if IMPORTS.search(text):
            held.add(path.stem)
    return held


def reaches(step, gates):
    run = str(step.get("run") or "")
    named = {held for pair in REQCTL.findall(run) for held in pair if held}
    return bool(set(GATE.findall(run)) & gates
                or named
                or IMPORTS.search(run)
                or str(step.get("uses") or "").startswith("."))


def settled(steps, where, gates):
    at = next((index for index, step in enumerate(steps)
               if ACCEPTS.search(str(step.get("run") or ""))), None)
    if at is None:
        return [f"{where}: step {step.get('name')!r} runs a gate over a corpus "
                f"no step accepts -- run {VALIDATES!r} before it"
                for step in steps
                if set(GATE.findall(str(step.get("run") or ""))) & gates]
    return [f"{where}: step {step.get('name')!r} reads the corpus before "
            f"{VALIDATES!r} -- move it after, so no gate judges a corpus "
            "reqctl has not accepted"
            for step in steps[:at] if reaches(step, gates)]


def faults(text, where, gates=None):
    try:
        held = yaml.safe_load(text)
    except yaml.YAMLError as broken:
        return [f"{where}: is not YAML: {broken}"]
    if not isinstance(held, dict):
        return [f"{where}: is not a mapping"]
    found = []
    who = Path(where).name
    if SECRET.search(text) and who not in WIELDS:
        found.append(f"{where}: reaches the secrets context")
    if who in WIELDS:
        for fired in sorted(UNTRUSTED & triggers(held)):
            found.append(f"{where}: wields a secret and fires on {fired}")
    gates = corpus_gates() if gates is None else gates
    jobs = held.get("jobs") or {}
    if not isinstance(jobs, dict):
        return [*found, f"{where}: jobs is not a mapping"]
    if len(jobs) != JOBS:
        found.append(f"{where}: has {len(jobs)} jobs, not {JOBS}")
    if held.get("permissions") != READ_ONLY:
        found.append(f"{where}: permissions is {held.get('permissions')!r}, "
                     f"not {READ_ONLY!r}")
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if "permissions" in job and job["permissions"] != READ_ONLY:
            found.append(f"{where}: job {name} takes {job['permissions']!r}, "
                         f"widening the workflow's {READ_ONLY!r}")
        steps = [step for step in job.get("steps") or [] if isinstance(step, dict)]
        for uses in [job.get("uses")] + [step.get("uses") for step in steps]:
            if uses and not PINNED.search(str(uses)):
                found.append(f"{where}: {uses} is not pinned to a commit")
        for step in steps:
            if step.get("continue-on-error"):
                found.append(
                    f"{where}: step {step.get('name')!r} continues on error, "
                    "so a failed gate leaves the job green")
        found += settled(steps, where, gates)
    return found + installs(text, where)


def installs(text, where):
    found = []
    for line in PIP.findall(CONTINUED.sub(" ", text)):
        held = " ".join(line.split())
        spaced = f" {held} "
        if " -r " in spaced and "--require-hashes" not in spaced:
            found.append(f"{where}: `{held}` installs from a lockfile without "
                         "--require-hashes")
        if " -e " in spaced and "--no-build-isolation" not in spaced:
            found.append(f"{where}: `{held}` builds an editable install without "
                         "--no-build-isolation")
    return found


def main():
    paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    found = [] if paths else [f"{WORKFLOWS}: holds no workflow"]
    gates = corpus_gates()
    if not gates:
        found.append(f"{GUARDS}: holds no gate that reaches reqctl, so the "
                     "ordering check holds nothing -- run this from the "
                     "repository root")
    for path in paths:
        try:
            text = path.read_text()
        except OSError as broken:
            found.append(f"{path.as_posix()}: cannot read: {broken}")
            continue
        found += faults(text, path.as_posix(), gates)
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
