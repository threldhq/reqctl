#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from typing import NamedTuple

import yaml
from packaging.utils import canonicalize_name

WORKFLOWS = Path(".github/workflows")
GUARDS = Path(".github/guards")
PINNED = re.compile(r"@[0-9a-f]{40}$")
PIP = re.compile(r"\bpip[\d.]*\s(?:&(?!&)|[^;&|\n])*")
EDITABLE = re.compile(r"--editable(=.*)?|-[qvUI]*e.*")
REQUIREMENT = re.compile(r"--requirement(=.*)?|-[qvUI]*r.*")
CONTINUED = re.compile(r"\\\n[ \t]*")
READ_ONLY = {"contents": "read"}
TAGS = "release-tag.yml"
PUSHED = {"push": {"branches": ["main"]}}
SECRET = re.compile(r"\bsecrets\b")
WIELDS = {"corpus-write.yml", "corpus-view.yml"}
GATE = re.compile(r"\.github/guards/([\w-]+)\.py")
REQCTL = re.compile(r"(?m)^\s*reqctl\s+([\w-]+)|-m\s+reqctl\s+([\w-]+)")
IMPORTS = re.compile(r"(?m)^\s*(?:from reqctl import|import reqctl)\b"
                     r"|[\"']reqctl[\"']")
ACCEPTS = re.compile(r"(?m)^\s*reqctl\s+validate\b")
VALIDATES = "reqctl validate"
UNTRUSTED = "pull_request"
JOBS = 1
CHECK = (WORKFLOWS / "ci.yml").as_posix()
RUNTIME = "requirements-lock.txt"
COSMETIC = {"-q", "--quiet", "--disable-pip-version-check"}
LONG = {"--requirement": "r", "--editable": "e"}
CLUSTER = re.compile(r"-([qvUI]*)([re])(.*)")
REDIRECT = re.compile(r"\d*[<>&].*")
DEV_INPUTS = Path("reqctl/requirements-dev.in")
DEV_LOCK = DEV_INPUTS.with_name("requirements-dev-lock.txt")
HOOK = Path(".claude/hooks/session-start.sh")
LISTED = re.compile(r"(?m)^\s*([A-Za-z0-9][\w.-]*)")
NESTED = re.compile(r"(?m)^\s*(?:-r\s*|--requirement(?:\s+|=))(\S+)")
ENTRY = re.compile(r"(?m)^\s*(?:(?:-e|--editable)(?:\s+|=))?([^\s#-]\S*)")
ARCHIVES = (".whl", ".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tar.xz",
            ".txz", ".tar")
VERSIONED = re.compile(r"(.+?)-\d")
EGG = re.compile(r"[#&]egg=([^&]+)")
NAMED = re.compile(r"[A-Za-z0-9][\w.-]*")
INSTALLERS = Path(".github")
PACKAGE = DEV_INPUTS.parent.name
SCRIPT = re.compile(GATE.pattern
                    + r"|\.github/(?:corpus_gates|travel_alone|baseline_number)\.py")
RUNS = re.compile(r"(?<![\w.-])reqctl\s+[\w-]|-m\s*reqctl\b")
FAILS = re.compile(r"\bexit\s+[1-9]|\bsys\.exit\(")
SWALLOWED = re.compile(r"\|\|\s*(?:true|:)(?![\w-])")
UNSTOPPED = re.compile(r"\bset\s+(?:\+\w*e|\+o\s+errexit)")
SHELLS = {"bash", "sh", "dash", "ksh", "zsh"}
STOPS = re.compile(r"-\w*e\w*")
RESUMES = re.compile(r"\+\w*e\w*")
CONTEXT = re.compile(r"[A-Za-z_][\w-]*\s*[.(\[]")
ALWAYS = re.compile(r"\$\{\{\s*true\s*\}\}|true", re.I)


class Install(NamedTuple):
    files: list
    editable: list
    positional: list
    flags: set


def triggers(held):
    fired = held.get(True, held.get("on")) or {}
    if isinstance(fired, str):
        return {fired}
    return set(fired) if isinstance(fired, (dict, list)) else set()


def corpus_gates(folder=GUARDS):
    held = set()
    for path in sorted(folder.glob("*.py")):
        # @req+ GUARD-83168738@zhoOQpGgBd9R raavax
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError) as broken:
            raise SystemExit(
                f"{path.as_posix()}: cannot read: {broken}") from broken
        # @req- raavax
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
    # @req+ GUARD-12128145@mFuOqNbkyV1o 3a5aqb
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
    # @req- 3a5aqb


def checkers(inputs=DEV_INPUTS, folder=INSTALLERS):
    # @req+ GUARD-83168738@zhoOQpGgBd9R 5rq7uk
    try:
        lines = inputs.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as broken:
        raise SystemExit(
            f"{inputs.as_posix()}: cannot read: {broken}") from broken
    # @req- 5rq7uk
    names = [re.sub(r"-py$", "", re.split(r"[\[=<>~!;\s]", line.strip(), maxsplit=1)[0])
             for line in lines if "==" in line]
    names += [path.stem.removeprefix("install-")
              for path in folder.glob("install-*.sh")]
    spelled = ["[-_]".join(map(re.escape, re.split(r"[-_]", name)))
               for name in names]
    return re.compile(r"(?<![\w-])(?:" + "|".join(spelled) + r")(?![\w-])")


def gated(step, tools):
    run = str(step.get("run") or "")
    return bool(SCRIPT.search(run) or RUNS.search(run) or IMPORTS.search(run)
                or FAILS.search(run) or tools.search(run)
                or str(step.get("uses") or "").startswith("."))


def shell_of(node, inherited):
    defaults = node.get("defaults")
    run = defaults.get("run") if isinstance(defaults, dict) else None
    return run.get("shell", inherited) if isinstance(run, dict) else inherited


def always_false(condition):
    if condition is None or condition is True:
        return False
    text = str(condition).strip()
    return not CONTEXT.search(text) and not ALWAYS.fullmatch(text)


def unstopped(shell):
    words = re.sub(r"[\"']", "", str(shell or "")).split()
    if "{0}" not in words:
        return False
    words = words[:words.index("{0}")]
    if words and Path(words[0]).name == "env":
        words = words[1:]
    if not words or Path(words[0]).name not in SHELLS:
        return False
    stops = False
    for word, after in zip(words[1:], words[2:] + [""]):
        if STOPS.fullmatch(word) or (word == "-o" and after == "errexit"):
            stops = True
        elif RESUMES.fullmatch(word) or (word == "+o" and after == "errexit"):
            stops = False
    return not stops


def swallowed(name, job, steps, where, shell, tools):
    gating = [step for step in steps if gated(step, tools)]
    found = []
    # @req+ GUARD-84344643@GlwsRru4lu4P sfx7sh
    if gating and job.get("continue-on-error"):
        found.append(f"{where}: job {name} runs a gate and continues on error "
                     "-- remove continue-on-error")
    if gating and always_false(job.get("if")):
        found.append(f"{where}: job {name} runs a gate under a constant "
                     "condition other than true -- remove the condition")
    for step in gating:
        run = CONTINUED.sub(" ", str(step.get("run") or ""))
        named = step.get("name")
        if SWALLOWED.search(run):
            found.append(f"{where}: step {named!r} runs a gate and discards its "
                         "failure with || true or || : -- remove it")
        if UNSTOPPED.search(run) or unstopped(step.get("shell", shell)):
            found.append(f"{where}: step {named!r} runs a gate in a shell that "
                         "does not stop on a failing command -- remove set +e, "
                         "or give the shell -e")
        if always_false(step.get("if")):
            found.append(f"{where}: step {named!r} runs a gate under a "
                         "constant condition other than true -- remove the "
                         "condition")
    # @req- sfx7sh
    return found


def faults(text, where, gates=None, tools=None):
    # @req+ GUARD-83168738@zhoOQpGgBd9R bwk6ho
    try:
        held = yaml.safe_load(text)
    except (yaml.YAMLError, ValueError) as broken:
        return [f"{where}: is not YAML: {broken}"]
    # @req- bwk6ho
    if not isinstance(held, dict):
        return [f"{where}: is not a mapping"]
    found = []
    who = Path(where).name
    # @req> REQ-74823322@YWZT0Srw2y2d fbf7lm
    if SECRET.search(text) and who not in WIELDS:
        found.append(f"{where}: reaches the secrets context")
    # @req> REQ-81795630@6p2bA0ZHqY-j 6nwnpn
    if who in WIELDS:
        for fired in sorted(name for name in triggers(held)
                            if str(name).startswith(UNTRUSTED)):
            found.append(f"{where}: wields a secret and fires on {fired}")
    # @req+ GUARD-20209566@zkKPlDbnzFuA wqoe4t
    events = held.get(True, held.get("on"))
    if who == TAGS and events != PUSHED:
        found.append(f"{where}: is triggered by {events!r}, not by {PUSHED!r} "
                     "alone")
    # @req- wqoe4t
    gates = corpus_gates() if gates is None else gates
    tools = checkers() if tools is None else tools
    jobs = held.get("jobs") or {}
    if not isinstance(jobs, dict):
        return [*found, f"{where}: jobs is not a mapping"]
    # @req> GUARD-37835776@0Spg60Mwp26J ayey6b
    if len(jobs) != JOBS:
        found.append(f"{where}: has {len(jobs)} jobs, not {JOBS}")
    # @req> GUARD-52037270@OztX8T4vOmsH ls2q44
    if held.get("permissions") != READ_ONLY:
        found.append(f"{where}: permissions is {held.get('permissions')!r}, "
                     f"not {READ_ONLY!r}")
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        # @req+ GUARD-52037270@OztX8T4vOmsH w4sjw2
        allowed = {"contents": "write"} if who == TAGS else READ_ONLY
        taken = job.get("permissions", READ_ONLY)
        if taken != allowed:
            found.append(f"{where}: job {name} takes {taken!r}, not "
                         f"{allowed!r}")
        # @req- w4sjw2
        steps = [step for step in job.get("steps") or [] if isinstance(step, dict)]
        # @req> GUARD-85664071@zrnITtEG0Lqc yekzpu
        for uses in [job.get("uses")] + [step.get("uses") for step in steps]:
            if uses and not PINNED.search(str(uses)):
                found.append(f"{where}: {uses} is not pinned to a commit")
        # @req> GUARD-40603760@BjP6UvmNcOQT yrydmh
        for step in steps:
            if step.get("continue-on-error"):
                found.append(
                    f"{where}: step {step.get('name')!r} continues on error, "
                    "so a failed gate leaves the job green")
        found += swallowed(name, job, steps, where,
                           shell_of(job, shell_of(held, None)), tools)
        found += settled(steps, where, gates)
    return found + installs(text, where)


def pip_lines(text):
    found = []
    for line in PIP.findall(CONTINUED.sub(" ", re.sub(r"[\"']", "", text))):
        words = line.split()[1:]
        if "install" in words and all(
                word.startswith("-") or before.startswith("-")
                for before, word in zip([""] + words,
                                        words[:words.index("install")])):
            found.append(line)
    return found


def installs(text, where):
    found = []
    for line in pip_lines(text):
        held = " ".join(line.split())
        words, kept = held.split(), held.split(" #", 1)[0].split()
        # @req> GUARD-26421773@SDQf4TqpYtSB kt5es3
        if (any(REQUIREMENT.fullmatch(word) for word in words)
                and "--require-hashes" not in kept):
            found.append(f"{where}: `{held}` installs from a lockfile without "
                         "--require-hashes")
        # @req> GUARD-72877772@JfdZ18LPQLEi bbo2z6
        if (any(EDITABLE.fullmatch(word) for word in words)
                and "--no-build-isolation" not in kept):
            found.append(f"{where}: `{held}` builds an editable install without "
                         "--no-build-isolation")
    return found


def pip_installs(text):
    held = []
    for line in pip_lines(text):
        words = line.split(" #", 1)[0].split()
        words = [part for word in words[words.index("install") + 1:]
                 for part in (word.split("=", 1) if word.startswith("--")
                              else [word])]
        install = Install([], [], [], set())
        while words:
            word = words.pop(0)
            cluster = CLUSTER.fullmatch(word)
            if word in LONG or cluster:
                kind, value = ((LONG[word], "") if word in LONG
                               else (cluster[2], cluster[3]))
                if cluster:
                    install.flags.update({f"-{letter}" for letter in cluster[1]}
                                         - COSMETIC)
                value = value or (words.pop(0) if words else "")
                (install.files if kind == "r" else install.editable).append(value)
            elif REDIRECT.fullmatch(word):
                continue
            elif not word.startswith("-"):
                install.positional.append(word)
            elif word not in COSMETIC:
                install.flags.add(word)
        held.append(install)
    return held


def installs_reqctl(install):
    return any(Path(word).name.startswith(PACKAGE)
               for word in install.editable + install.positional)


def installs_lock(install):
    return any(Path(word).name == RUNTIME for word in install.files)


def signature(install):
    return install.flags, bool(install.editable), install.positional


def flagged(install):
    return f"with {' '.join(sorted(install.flags)) or 'no flags'}"


def shaped(install):
    return ("as an editable package" if install.editable
            else f"from {' '.join(install.positional)}")


def reference(text):
    held = pip_installs(text)
    return (next((one for one in held if installs_lock(one)), None),
            next((one for one in held if installs_reqctl(one)), None))


def parity(text, where, lock, own):
    held = pip_installs(text)
    first = next((at for at, one in enumerate(held) if installs_reqctl(one)),
                 None)
    if first is None:
        return []
    # @req+ GUARD-20154572@z2_hbXJO9sHn nfv4rg
    found = [] if any(map(installs_lock, held[:first])) else [
        f"{where}: installs reqctl before {RUNTIME} -- install that lockfile "
        f"first, as {CHECK} does"]
    found += [f"{where}: installs {RUNTIME} {flagged(one)}, not "
              f"{flagged(lock)} as {CHECK} does"
              for one in held if installs_lock(one) and one.flags != lock.flags]
    found += [f"{where}: installs reqctl {shaped(one)} {flagged(one)}, not "
              f"{shaped(own)} {flagged(own)} as {CHECK} does"
              for one in held
              if installs_reqctl(one) and signature(one) != signature(own)]
    # @req- nfv4rg
    return found


def held_by(path):
    # @req+ GUARD-83168738@zhoOQpGgBd9R st7nb6
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as broken:
        return "", f"{path.as_posix()}: cannot read: {broken}"
    # @req- st7nb6
    return text, None


def names_of(word):
    base = re.sub(r"(?<=\.git)@.*", "", re.split(r"[#?]", word)[0])
    tail = re.split(r"[@\[]", Path(base).name)[0]
    stem = VERSIONED.match(tail) if tail.lower().endswith(ARCHIVES) else None
    egg, first = EGG.search(word), NAMED.match(word)
    return {canonicalize_name(name) for name in
            (stem[1] if stem else tail.removesuffix(".git"),
             egg and egg[1], first and first[0])
            if name}


def sources(text, where, dev):
    found = []
    for install in pip_installs(text):
        for word in install.positional + install.editable:
            if names_of(word) & dev:
                found.append(f"{where}: installs {word} by name, and "
                             f"{DEV_LOCK} holds it -- install it with "
                             f"-r {DEV_LOCK}")
        pending, seen = [Path(file) for file in install.files], set()
        while pending:
            file = pending.pop()
            if file in seen or (file.parent.name == PACKAGE
                                and file.name in (DEV_LOCK.name, RUNTIME)):
                continue
            seen.add(file)
            held, fault = held_by(file)
            pending += [file.parent / nested for nested in NESTED.findall(held)]
            if fault:
                found.append(f"{where}: {fault}")
            elif shared := set().union(*map(names_of, ENTRY.findall(held))) & dev:
                found.append(f"{where}: installs {', '.join(sorted(shared))} "
                             f"from {file}, and {DEV_LOCK} holds them -- install "
                             f"them from {DEV_LOCK} or {PACKAGE}/{RUNTIME}")
    return found


def runs_of(text):
    try:
        held = yaml.safe_load(text)
    except (yaml.YAMLError, ValueError):
        return ""
    jobs = held.get("jobs") if isinstance(held, dict) else None
    return "\n".join(str(step.get("run") or "")
                     for job in (jobs.values() if isinstance(jobs, dict) else [])
                     if isinstance(job, dict)
                     for step in job.get("steps") or []
                     if isinstance(step, dict))


def main():
    paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    found = [] if paths else [f"{WORKFLOWS}: holds no workflow"]
    gates = corpus_gates()
    if not gates:
        found.append(f"{GUARDS}: holds no gate that reaches reqctl, so the "
                     "ordering check holds nothing -- run this from the "
                     "repository root")
    tools, texts = checkers(), {}
    for path in paths:
        # @req+ GUARD-83168738@zhoOQpGgBd9R xqino3
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError) as broken:
            found.append(f"{path.as_posix()}: cannot read: {broken}")
            continue
        # @req- xqino3
        found += faults(text, path.as_posix(), gates, tools)
        texts[path.as_posix()] = runs_of(text)
    lock, own = reference(texts.get(CHECK, ""))
    if lock is None or own is None:
        found.append(f"{CHECK}: installs no reqctl from {RUNTIME}, "
                     "so no workflow has an install to match -- run this from "
                     "the repository root")
    else:
        for where, text in texts.items():
            found += parity(text, where, lock, own)
    # @req+ GUARD-24264620@IECSQ_EeiXfC ytkt47
    held, fault = held_by(DEV_LOCK)
    dev = {canonicalize_name(name) for name in LISTED.findall(held)}
    if not dev:
        found.append(fault or f"{DEV_LOCK}: holds no locked package, so no "
                     "install has a source to check -- run this from the "
                     "repository root")
    # @req+ GUARD-83168738@zhoOQpGgBd9R qp7dag
    try:
        texts[HOOK.as_posix()] = HOOK.read_text()
    except (OSError, UnicodeDecodeError) as broken:
        found.append(f"{HOOK.as_posix()}: cannot read: {broken}")
    # @req- qp7dag
    for where, text in texts.items():
        found += sources(text, where, dev)
    # @req- ytkt47
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
