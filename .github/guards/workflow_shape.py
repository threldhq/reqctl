#!/usr/bin/env python3
import configparser
import re
import shlex
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

import yaml
from packaging.utils import canonicalize_name

WORKFLOWS = Path(".github/workflows")
GUARDS = Path(".github/guards")
PINNED = re.compile(r"@[0-9a-f]{40}$")
PIP = re.compile(r"\bpipx?[\d.]*$")
UV = re.compile(r"\buv$")
EDITABLE = re.compile(r"--editable(=.*)?|-[qvUI]*e.*")
REQUIREMENT = re.compile(r"--requirement(=.*)?|-[qvUI]*r.*")
CONTINUED = re.compile(r"\\\n[ \t]*")
READ_ONLY = {"contents": "read"}
TAGS = "release-tag.yml"
PUSHED = {"push": {"branches": ["main"]}}
SECRET = re.compile(r"\bsecrets\b", re.IGNORECASE)
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
ENTRY = re.compile(r"(-e\s*|--editable(?:\s+|=))?([^\s-].*)")
COMMENT = re.compile(r"(^|\s+)#.*$")
SPECIFIER = re.compile(r"([A-Za-z0-9][\w.-]*)\s*(?:\[[\w,.\s-]*\])?\s*(?:(?:===|[<>=!~]=?)[^;]*)?(?:;.*)?")
ARCHIVES = (".whl", ".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tar.xz",
            ".txz", ".tar", ".tlz", ".tar.lz", ".tar.lzma")
REMOTE = re.compile(r"^[a-z][a-z0-9+.-]*:|@", re.IGNORECASE)
NAMED = re.compile(r"[A-Za-z0-9][\w.-]*")
INSTALLERS = Path(".github")
PACKAGE = DEV_INPUTS.parent.name
CHECKOUTS = (".reqctl", "$RUNNER_TEMP/reqctl")
LOCKS = {DEV_LOCK, *(Path(root, DEV_LOCK.with_name(RUNTIME)) for root in ("", *CHECKOUTS))}
SCRIPT = re.compile(GATE.pattern
                    + r"|\.github/(?:corpus_gates|travel_alone|baseline_number)\.py")
RUNS = re.compile(r"(?<![^\s;&|(){}!`'\"/])reqctl[\"']?[ \t]+(?:-\S+[ \t]+)*[a-z]"
                  r"|-m[ \t]*reqctl\b")
SCRIPTED = re.compile(r"(?:^|/)(?:" + SCRIPT.pattern + r")$")
ASSIGNED = re.compile(r"\w+=.*")
PYTHON = re.compile(r"python[\d.]*")
PUNCTUATION = re.compile(r"[;&|()<>]+")
REDIRECTION = re.compile(r"[<>]{1,3}&?|&>{1,2}")
FAILING = re.compile(r"\b(?:failure|cancelled)\b", re.I)
SUBSTITUTED = re.compile(r"`|\$\(")
READABLE = {"bash", "sh"}
STOPPING = re.compile(r"[-+][euxvo]+|pipefail|errexit|nounset|xtrace"
                      r"|--noprofile|--norc")
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
    return bool(SCRIPT.search(run) or RUNS.search(run) or tools.search(run)
                or str(step.get("uses") or "").startswith("."))


def commanded(words, tools):
    while words and ASSIGNED.fullmatch(words[0]):
        words = words[1:]
    if not words:
        return False
    name, rest = Path(words[0]).name, words[1:]
    if PYTHON.fullmatch(name):
        named = next((word for word in rest if not word.startswith("-")), "")
        return rest[:2] == ["-m", PACKAGE] or bool(SCRIPTED.search(named))
    return (name == PACKAGE or bool(tools.fullmatch(name))
            or bool(SCRIPTED.search(words[0])))


def alone(run, tools):
    text = CONTINUED.sub(" ", run).strip()
    if "\n" in text or SUBSTITUTED.search(text):
        return False
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.commenters = ""
    try:
        words = list(lexer)
    except ValueError:
        return False
    return commanded(words, tools) and not any(
        PUNCTUATION.fullmatch(word) and not REDIRECTION.fullmatch(word)
        for word in words)


def readable(shell):
    words = str(shell or "bash").split()
    if words[-1:] == ["{0}"]:
        words = words[:-1]
    return (bool(words) and words[0] in READABLE
            and all(STOPPING.fullmatch(word) for word in words[1:]))


def shell_of(node, inherited):
    defaults = node.get("defaults")
    run = defaults.get("run") if isinstance(defaults, dict) else None
    return run.get("shell", inherited) if isinstance(run, dict) else inherited


def skips(condition):
    if condition is None or condition is True:
        return False
    text = str(condition).strip()
    return FAILING.search(text) or not (CONTEXT.search(text)
                                        or ALWAYS.fullmatch(text))


def swallowed(name, job, steps, where, shell, tools):
    # @req+ GUARD-84344643@C0RxmQgbeF_W sfx7sh
    gating = [step for step in steps if gated(step, tools)]
    found = []
    if gating and job.get("continue-on-error"):
        found.append(f"{where}: job {name} runs a gate and continues on error "
                     "-- remove continue-on-error")
    if gating and skips(job.get("if")):
        found.append(f"{where}: job {name} runs a gate under a condition that "
                     "skips it while the run passes -- remove the condition")
    for step in gating:
        named = step.get("name")
        if "run" in step:
            if not alone(str(step["run"] or ""), tools):
                found.append(f"{where}: step {named!r} runs a gate together "
                             "with another command -- give the gate a step of "
                             "its own that runs the gate and its arguments "
                             "alone")
            stepped = step.get("shell", shell)
            if not readable(stepped):
                found.append(f"{where}: step {named!r} runs a gate under shell "
                             f"{stepped!r}, which the build cannot read -- run "
                             "it under bash or sh")
        if skips(step.get("if")):
            found.append(f"{where}: step {named!r} runs a gate under a "
                         "condition that skips it while the run passes -- "
                         "remove the condition")
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
    for segment in re.split(r"[;|\n]|&&",
                            CONTINUED.sub(" ", re.sub(r"[\"']", "", text))):
        words, reaches, end, start = segment.split(), False, None, len(found)
        for at in reversed(range(len(words))):
            if reaches and (PIP.search(words[at]) or words[at] == "tool"
                            and at and UV.search(words[at - 1])):
                found.insert(start, " ".join(words[at:end]))
                end = at
            reaches = words[at] == "install" or reaches and (
                words[at].startswith("-") or words[at - 1].startswith("-"))
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


def names_of(word, editable=False):
    if REMOTE.search(word):
        return None
    bare = re.sub(r"\[[^\]]+\]$", "", word.partition(";")[0].strip()).strip()
    if bare.lower().endswith(".whl"):
        name = Path(bare).name.partition("-")[0]
        return {canonicalize_name(name)} if "-" in bare and NAMED.fullmatch(name) else None
    if bare.lower().endswith(ARCHIVES):
        return None
    if editable or "/" in bare or bare.startswith((".", "~")):
        name = project_name(bare)
        return {canonicalize_name(name)} if name else None
    found = SPECIFIER.fullmatch(word)
    return {canonicalize_name(found[1])} if found else None


def project_name(base):
    try:
        folder = Path(next((base.removeprefix(f"{root}/") for root in CHECKOUTS
                            if base.startswith(f"{root}/")), base)).expanduser()
        pyproject = folder / "pyproject.toml"
        project = tomllib.loads(pyproject.read_text()).get("project") if pyproject.is_file() else None
        if isinstance(project, dict):
            name, dynamic = project.get("name"), project.get("dynamic", [])
            return name if isinstance(name, str) and NAMED.fullmatch(name) and isinstance(
                dynamic, list) and "name" not in dynamic else None
        config = configparser.ConfigParser(interpolation=None)
        config.read_string((folder / "setup.cfg").read_text())
        name = config.get("metadata", "name", fallback=None)
    except (OSError, ValueError, RecursionError, RuntimeError, configparser.Error):
        return None
    return name if name and NAMED.fullmatch(name) else None



def requirement_lines(held):
    joined, pending = [], []
    for line in held.splitlines():
        if not line.endswith("\\") or COMMENT.match(line):
            joined.append("".join(pending) + (" " + line if COMMENT.match(line) else line))
            pending = []
        else:
            pending.append(line.strip("\\"))
    return [COMMENT.sub("", line).strip() for line in joined + ["".join(pending)] * bool(pending)]

def sources(text, where, dev):
    found = []
    for install in pip_installs(text):
        for word, editable in [(word, False) for word in install.positional] + [
                (word, True) for word in install.editable]:
            names = names_of(word, editable)
            if names is None:
                found.append(f"{where}: installs {word}, a URL or a folder whose package name its "
                             "pyproject.toml or setup.cfg does not state -- install it from a "
                             "lockfile, or from a local folder that states its name")
            elif names & dev:
                found.append(f"{where}: installs {word} by name, and "
                             f"{DEV_LOCK} holds it -- install it with "
                             f"-r {DEV_LOCK}")
        pending, seen = [Path(file) for file in install.files], set()
        while pending:
            file = pending.pop()
            # @req> GUARD-24264620@IECSQ_EeiXfC 5zpm7c
            if file in seen or file in LOCKS:
                continue
            seen.add(file)
            held, fault = held_by(file)
            pending += [file.parent / nested for nested in NESTED.findall(held)]
            lines = requirement_lines(held)
            named = [names_of(entry[2], bool(entry[1])) for line in lines if (entry := ENTRY.fullmatch(line))]
            if fault:
                found.append(f"{where}: {fault}")
            elif None in named:
                found.append(f"{where}: {file} installs a URL or a folder whose package name "
                             "its pyproject.toml or setup.cfg does not state -- name the "
                             "package and pin it in a lockfile")
            elif shared := set().union(*named) & dev:
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


# @req> GUARD-52037270@OztX8T4vOmsH z3qmtw
# @req> GUARD-24264620@IECSQ_EeiXfC c2mpcx
# @req> GUARD-12128145@mFuOqNbkyV1o 6xrg3i
# @req> GUARD-84344643@C0RxmQgbeF_W yklz3x
# @req> GUARD-20209566@zkKPlDbnzFuA iyj7q3
# @req> GUARD-20154572@z2_hbXJO9sHn 6lheox
# @req> REQ-74823322@YWZT0Srw2y2d q2omdp
# @req> REQ-81795630@6p2bA0ZHqY-j higkti
# @req> GUARD-37835776@0Spg60Mwp26J pezyya
# @req> GUARD-85664071@zrnITtEG0Lqc e5ld6l
# @req> GUARD-40603760@BjP6UvmNcOQT t7wupp
# @req> GUARD-26421773@SDQf4TqpYtSB t33smj
# @req> GUARD-72877772@JfdZ18LPQLEi t6sycv
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


# @req> GUARD-52037270@OztX8T4vOmsH azlptq
# @req> GUARD-24264620@IECSQ_EeiXfC p5qlkx
# @req> GUARD-12128145@mFuOqNbkyV1o 2oldcn
# @req> GUARD-84344643@C0RxmQgbeF_W cackjz
# @req> GUARD-20209566@zkKPlDbnzFuA qanxgx
# @req> GUARD-20154572@z2_hbXJO9sHn 33y44j
# @req> REQ-74823322@YWZT0Srw2y2d j2aed6
# @req> REQ-81795630@6p2bA0ZHqY-j 6efdzk
# @req> GUARD-37835776@0Spg60Mwp26J j3mi7a
# @req> GUARD-85664071@zrnITtEG0Lqc tmmpe7
# @req> GUARD-40603760@BjP6UvmNcOQT 7xc6r6
# @req> GUARD-26421773@SDQf4TqpYtSB na6x2c
# @req> GUARD-72877772@JfdZ18LPQLEi sgih6j
if __name__ == "__main__":
    sys.exit(main())
