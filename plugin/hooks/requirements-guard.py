#!/usr/bin/env python3

import fnmatch
import functools
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ITEM_FOLDERS = {"reqs": "REQ", "guards": "GUARD", "params": "PARAM",
                "terms": "TERM", "data": "DATA"}
_ITEMS = "|".join(ITEM_FOLDERS)
_UIDS = "|".join(ITEM_FOLDERS.values())
_CORPUS = f"{_ITEMS}|baselines"
_ROOT = r"(?<![\w.-])requirements"
_BASELINE_FILE = rf"{_ROOT}/baseline\.ya?ml"

ITEM = re.compile(rf"{_ROOT}/({_ITEMS})/({_UIDS})-\d{{8}}\.ya?ml$")
BASELINE = re.compile(rf"{_ROOT}/baselines/|{_BASELINE_FILE}")
CORPUS_DIR = re.compile(
    rf"{_ROOT}/({_CORPUS})(?![\w.-])"
    rf"|{_BASELINE_FILE}"
    rf"|{_ROOT}" r"/[^/\s]*[*?{\[]"
    r"|\bcd\s+requirements(?![\w.-])"
)
CORPUS_ROOT_NAME = "requirements"
REDIRECT = re.compile(rf">>?&?\s*[^\s>]*({_ROOT}/({_CORPUS})|{_BASELINE_FILE})")
REDIRECT_TARGET = re.compile(r">>?&?[ \t]*([^\s<>;&|()]+)")
REDUNDANT = re.compile(r"/(?:\./)+|//+")
PARENT = re.compile(r"(^|/)(?!\.\./)[^/\s]+/\.\./")
PATH_KEY = re.compile(
    r"(^|_|[a-z])(path|paths|pathname|file|files|filename|filenames|dest"
    r"|destination|dir|directory|folder|folders|target|output|src|dst|source"
    r"|to|uri)$", re.I)
PATH_SHAPE = re.compile(r"[^\s'\"`$();|<>]+")
COMMAND_KEY = re.compile(r"(^|_|[a-z])(command|cmd|script|shell)$", re.I)
GLOB_KEY = re.compile(r"(^|_|[a-z])pattern$", re.I)
GREP_GLOB_KEY = re.compile(r"^glob$")
BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")
SEQUENCE = re.compile(r"\{[^{}]*\.\.[^{}]*\}")
WRAPPERS = ("env", "command", "nohup", "sudo", "doas", "timeout", "nice", "time",
            "exec", "xargs", "stdbuf")
SHELLS = ("sh", "bash", "dash", "zsh", "ksh")
FIND_RUNS = ("-exec", "-execdir", "-ok", "-okdir")
REPO_OPTIONS = ("-C", "--git-dir", "--work-tree")
GIT_VALUED = ("-c", *REPO_OPTIONS, "--namespace", "--config-env")
REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE")
CONFIG_HOMES = ("HOME", "XDG_CONFIG_HOME")
TRUSTED_SCOPES = ("system", "global")
CORPUS_ENTRIES = (*ITEM_FOLDERS, "baselines", "baseline.yml", "baseline.yaml")
GLOB_LIMIT = 4096
DEADLINE = time.monotonic() + 30
JUDGED = ("git", "rm", "patch", "find", "eval", *SHELLS)
LONG_FLAGS = ("--force", "--hard", "--discard-changes", "--dry-run", "--staged",
              "--worktree")
NO_COMMIT = {"merge": ("--ff-only", "--no-commit", "--squash", "--abort", "--quit"),
             "cherry-pick": ("-n", "--no-commit", "--abort", "--quit", "--skip"),
             "revert": ("-n", "--no-commit", "--abort", "--quit", "--skip")}
READ_VERBS = ("cat", "head", "tail", "less", "more", "nl", "wc", "ls", "stat",
              "file", "grep", "rg", "diff", "cut", "jq", "reqctl", "echo", "printf",
              "cmp", "sha1sum", "sha256sum", "sha512sum", "md5sum", "cksum", "du",
              "tree", "realpath", "basename", "dirname", "column", "test")
NAME_ONLY = ("ls", "stat", "file", "reqctl", "echo", "printf", "du", "tree",
             "realpath", "basename", "dirname", "test")
READ = re.compile(rf"^\s*({'|'.join(READ_VERBS)})(?=\s|$)")
CONTENT_READ = re.compile(
    rf"^\s*({'|'.join(v for v in READ_VERBS if v not in NAME_ONLY)})(?=\s|$)")
SINK = re.compile(
    r"^\s*(sort|uniq|awk|sed|tr|tac|rev|xxd|od|paste|fold|fmt)(?=\s|$)"
)
SINK_WRITES = re.compile(r"(?:^|\s)-(?:i|o|w)\b|--in-place|--output|>")
LISTS_FILES = ("--files0-from", "--files-from", "--fromfile")
AWK_RUNS = re.compile(r"getline|system|[|@]")
AWK_PROGRAM_FILE = ("-f", "-E", "-i", "-l", "--f", "--e", "--i", "--l")
SED_QUIET = re.compile(r"-[nErusz]+|--(?:quiet|silent|regexp-extended|posix|null-data"
                       r"|unbuffered|separate)")
_SED_ADDRESS = r"(?:\d+|\$|/(?:\\.|[^/\\\n])*/I?)"
SED_SCRIPT = re.compile(
    rf"(?:\s*(?:{_SED_ADDRESS}(?:,{_SED_ADDRESS})?!?\s*)?"
    r"(?:s(?P<d>[^\\\n\w\s])(?:\\.|(?!(?P=d))[^\\\n])*(?P=d)"
    r"(?:\\.|(?!(?P=d))[^\\\n])*(?P=d)[gpIiMm0-9]*|[pdqP=])\s*(?:;|$))+")
# @req+ REQ-38099593@_nWaC_p_1ziz 2x3zhi
SEARCHES = ("grep", "egrep", "fgrep", "rg", "ag")
RUNS_PROGRAM = ("--open-files-in-pager", "--pre", "--pager", "--hostname-bin")
OPENS_PAGER = re.compile(r"-[0-9A-Za-z]*O")
QUIET_REDIRECT = re.compile(
    r"[0-9]?>(?:&[ \t]*(?:[12]|-)|>?[ \t]*/dev/null)(?=[ \t\n|&;()<>]|$)")
WRITES_NOTHING = tuple(verb for verb in READ_VERBS
                       if verb not in ("less", "more", "file", "tree")) + (
    "tr", "tac", "rev", "od", "paste", "fold", "fmt", "cd")
SORT_WRITES = re.compile(r"-[A-Za-z]*o|--o|--co")
OPENER = "@req"
SPLITS = "$`{}"
INPUT_LIMIT = 20_000
# @req- 2x3zhi
# @req> git_read_forms@5d0_Etfuv7Lx r2wro4
GIT_READ = re.compile(
    r"^\s*git([ \t]+(-C[ \t]+[\w./~-]+|-[Pp]|--no-pager|--paginate))*"
    r"[ \t]+(?:(?P<read>log|show|diff|status|blame|ls-files)|add|commit)(?=[ \t\n]|$)"
)
HEREDOC = re.compile(r"(?<![<\\])(?:\\\\)*<<(?!<)-?\s*(['\"]?)(\w+)\1")
AMP_REDIRECT = re.compile(r"[0-9]?>&[ \t]*[0-9]*|&>>?")
SUBSHELL = re.compile(r"\$\(|`|<\(|>\(")
OUTPUT_FLAG = re.compile(r"--output\b|--in-place\b")
PUSH_LONG_DESTRUCTIVE = ("--force", "--force-with-lease", "--force-if-includes",
                         "--mirror", "--delete", "--prune")
GLUED_OPTION = re.compile(r"^-+[A-Za-z0-9]*?(?=requirements)")
ESCAPE = re.compile(r"\\(?=[A-Za-z0-9/])")
QUOTED_REDIRECT = re.compile(r"""(>>?\s*)(['"])([^'"]*)\2""")
GLOB_CHAR = re.compile(r"[*?\[\]{}]")
LITERAL_CHAR = re.compile(r"[^*?\[\]{}]")

UNQUOTED = str.maketrans("", "", "'\"\\")
CITATION_LINE = re.compile(r"^\s*(?:(?:#+|<!--|//)\s*)?@req[+>-](?:\s|$)")

# @req+ REQ-51296881@8h-e1bOYkZtT etn3fq
# @req+ REQ-67599992@TMfnHY-C4hOv jzjikg
UNREADABLE = (
    "The requirements guard could not read this tool call, so it cannot judge "
    "it.\n"
    "Denying rather than allowing: an unreadable call is the one case where the "
    "guard knows it is blind, and a blind guard that waves the call through is "
    "no guard. Tell the owner if this repeats."
)

USE_REQCTL = (
    "Requirements are reached through reqctl, never by editing files.\n"
    "  reqctl new requirement | reqctl context UID\n"
    "  reqctl validate | reqctl trace\n"
    "Approval and baselining are the owner's, on a pull request."
)

NOT_A_KNOWN_READ = (
    "Shell command reaching the requirements corpus outside the known-safe "
    "forms blocked: {target}\n" + USE_REQCTL
)

DIRECT_READ = (
    "Direct read of the requirements corpus blocked: {target}\n"
    "Read it through reqctl instead: `reqctl context UID`, `reqctl export`."
)

BLIND_GIT = (
    "The guard could not read the repository, so it cannot judge this call.\n"
    "Denying rather than allowing, as with any call it cannot read. Tell the "
    "owner if this repeats."
)

ON_DEFAULT = (
    "Commit on the default branch {branch} blocked.\n"
    "  git checkout -b claude/<name>\n"
    "{branch} is what the owner merges into, never what an agent commits to."
)

NO_DEFAULT = (
    "Commit blocked: origin names no default branch, so the guard cannot tell "
    "whether this commit lands on it.\n"
    "  git remote set-head origin --auto"
)

DISCARDS_WORK = (
    "This discards uncommitted work:\n"
    "{listing}\n"
    "Commit it first, then run the command -- or ask the owner."
)

INTO_SUBMODULES = (
    "Discard into submodules through {source} blocked: the guard does not read inside "
    "submodules.\n"
    "Add --no-recurse-submodules, then run the command in each submodule with git -C."
)

HAND_CITATION = (
    "A statement citation is written only by reqctl.\n"
    "  reqctl tag PATH --from N --to M --req UID | reqctl repin ID | reqctl untag ID"
)

NOT_A_READ = (
    "{tool} in a command naming a statement citation blocked: such a command may "
    "only read.\n"
    "Search with grep, rg or git grep, piped only to reads such as head, cut, sort, "
    f"uniq or wc.\n{HAND_CITATION}"
)

LONG_INPUT = (
    "{key} of {length} characters blocked: the guard reads a path or command of at "
    f"most {INPUT_LIMIT} characters.\n"
    "Write a longer script to a file with the Write tool and run the file, or name "
    "the path without redundant segments."
)

UNREAD_COMMAND = (
    "{found} in a command naming a statement citation blocked: the guard reads "
    "such a command only on one line, with no backslash, $ or backtick outside "
    "single quotes and no unquoted brace, parenthesis or <.\n"
    "Put its pattern and options in single quotes, on one line, and name files "
    "as operands."
)

INEXACT = (
    "old_string is not in the file exactly as written, and the file or new_string holds "
    "a statement citation.\n"
    "Give old_string exactly as the file holds it, quotes and escapes included."
)
# @req- etn3fq
# @req- jzjikg

WHOLE_TREE: list[str] = []
FORCE = ("-f", "--force", "--discard-changes")
RESTORES = ("checkout", "restore", "reset", "clean", "switch")
UNTRACKED = ("??", "!!")
UNTRACKED_ONLY = ("??",)


def named_paths(value, keys=PATH_KEY, key=""):
    if isinstance(value, str):
        # @req> REQ-38099593@_nWaC_p_1ziz okrfi5
        if keys.search(key) and len(value) > INPUT_LIMIT:
            deny(LONG_INPUT.format(key=key, length=len(value)))
        return [value] if keys.search(key) else []
    if isinstance(value, dict):
        return [found for k, v in value.items() for found in named_paths(v, keys, k)]
    if isinstance(value, list):
        return [found for v in value for found in named_paths(v, keys, key)]
    # @req> REQ-18701923@7CvKXOjSI6Kb pbu5yx
    if keys.search(key):
        deny(UNREADABLE)
    return []


def bare_paths(value):
    if isinstance(value, str):
        return [value] if len(value) <= INPUT_LIMIT and PATH_SHAPE.fullmatch(value) else []
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return [found for v in items for found in bare_paths(v)]


def flatten(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = REDUNDANT.sub("/", text)
        text = PARENT.sub(r"\1", text)
    return text


def deny(reason: str) -> None:
    # @req> REQ-60211288@pREpt1tBYPFJ tvcxjf
    decision = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    ).encode()
    # @req+ REQ-51060455@DPy54WGr0ngb kfua34
    try:
        while decision:
            decision = decision[os.write(1, decision):]
    except OSError:
        pass
    sys.exit(0)
    # @req- kfua34


def scan(cmd: str, joins=None) -> list[list[str]]:
    commands, pipeline, buf = [], [], []
    joins = [] if joins is None else joins
    quote = None
    lines = cmd.split("\n")
    row = 0

    def cut_segment():
        pipeline.append("".join(buf))
        buf.clear()

    def cut_command(join=";"):
        cut_segment()
        if any(s.strip() for s in pipeline):
            commands.append([s for s in pipeline if s.strip()])
            joins.append(join)
        pipeline.clear()

    while row < len(lines):
        line, i = lines[row], 0
        while i < len(line):
            char = line[i]
            if quote:
                if quote in ('"', "$'") and char == "\\" and i + 1 < len(line):
                    buf.append(line[i:i + 2])
                    i += 2
                    continue
                buf.append(char)
                quote = None if char == quote[-1] else quote
                i += 1
                continue
            if char in "'\"":
                quote = opened_quote(char, buf)
                buf.append(char)
                i += 1
                continue
            if char == "\\" and i + 1 < len(line):
                buf.append(line[i:i + 2])
                i += 2
                continue
            if char == "#" and (not buf or buf[-1] in " \t("):
                break
            if char == "|" and line[i:i + 2] != "||":
                cut_segment()
                i += 1
                continue
            if line[i:i + 2] in (";;", "&&", "||") or char in ";&":
                join = line[i:i + 2] if line[i:i + 2] in (";;", "&&", "||") else char
                cut_command(join)
                i += len(join)
                continue
            buf.append(char)
            i += 1
        if quote:
            buf.append("\n")
            row += 1
            continue
        if buf and buf[-1] == "\\":
            buf.pop()
            row += 1
            continue
        joined = "".join(buf)
        opened = next((found for found in HEREDOC.finditer(joined)
                       if masked(joined)[joined.index("<", found.start())] == "<"), None)
        if opened:
            body, row = [], row + 1
            while row < len(lines) and lines[row].strip() != opened.group(2):
                body.append(lines[row])
                row += 1
            buf.append("\n" + "\n".join(body))
        cut_command()
        row += 1
    if buf or pipeline:
        cut_command()
    return commands


def opened_quote(char, before):
    run = next((i for i, chunk in enumerate(reversed(before)) if chunk != "$"), len(before))
    return "$'" if char == "'" and run % 2 else char


@functools.cache
def masked(cmd):
    out, quote = [], None
    i = 0
    while i < len(cmd):
        char = cmd[i]
        if quote:
            if quote in ('"', "$'") and char == "\\" and i + 1 < len(cmd):
                out.append("__")
                i += 2
                continue
            out.append("_" if char != quote[-1] else char)
            quote = None if char == quote[-1] else quote
        elif char == "\\" and i + 1 < len(cmd):
            out.append(cmd[i:i + 2])
            i += 2
            continue
        elif char in "'\"":
            quote = opened_quote(char, out)
            out.append(char)
        else:
            out.append(char)
        i += 1
    return "".join(out)


def heading(part):
    cut = masked(part).find("\n")
    return part if cut < 0 else part[:cut]


def tokens_of(part):
    words, buf, quote, seen, escaped, dollars = [], [], None, False, False, 0
    for char in part:
        if escaped:
            buf.append(char)
            escaped, dollars = False, 0
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote[-1]:
                quote = None
            else:
                buf.append(char)
            continue
        if char in "'\"":
            quote = opened_quote(char, ["$"] * dollars)
            del buf[len(buf) - len(quote) + 1:]
            seen, dollars = True, 0
            continue
        dollars = dollars + 1 if char == "$" else 0
        if char.isspace():
            if buf or seen:
                words.append("".join(buf))
                buf, seen = [], False
            continue
        buf.append(char)
    return words + ["".join(buf)] if buf or seen else words


def invoked(words):
    i = 0
    while i < len(words) and (os.path.basename(words[i]) in WRAPPERS or "=" in words[i] or (i and (
            words[i].startswith("-") or words[i][:1].isdigit()
            or words[i - 1].startswith("-") and os.path.basename(words[i]) not in JUDGED))):
        i += 1
    if i and i < len(words) and os.path.basename(words[i]) not in JUDGED:
        i = next((j for j in range(i, len(words)) if os.path.basename(words[j]) in ("git", "rm")), i)
    return [os.path.basename(words[i]), *words[i + 1:]] if i < len(words) else []


def git_split(words):
    called = invoked(words)
    if not called or called[0] != "git":
        return None
    i = 1
    while i < len(called) and called[i].startswith("-"):
        i += 2 if called[i] in GIT_VALUED else 1
    if i >= len(called):
        return None
    return words[:len(words) - len(called)], called[1:i], called[i], called[i + 1:]


def git_subcommand(words):
    split = git_split(words)
    return (split[2], split[3]) if split else (None, [])


def located(words, here):
    prefix, options = git_split(words)[:2]
    settings = {name: value for name, assigned, value in (word.partition("=") for word in prefix)
                if assigned and (name in (*REPO_ENV, *CONFIG_HOMES) or name.startswith("GIT_CONFIG"))}
    where = [word for at, word in enumerate(options)
             if word.partition("=")[0] in REPO_OPTIONS
             or at and options[at - 1] in REPO_OPTIONS]
    if not here or any("$" in word or "`" in word
                       for word in [*where, *settings.values()]):
        return None
    return here, [os.path.expanduser(word) for word in options], settings


# @req> REQ-38099593@_nWaC_p_1ziz bc4mmq
def searched(part):
    words = tokens_of(part.split("\n", 1)[0])
    tool, rest = (("git grep", words[2:]) if words[:2] == ["git", "grep"]
                  else (words[0], words[1:]) if words[:1] and words[0] in SEARCHES
                  else (None, []))
    for word in rest:
        name = word.split("=", 1)[0]
        short = OPENS_PAGER.match(word)
        if short or (len(name) > 2 and any(flag.startswith(name) for flag in RUNS_PROGRAM)):
            return tool, short.group() if short else name
    return tool, None


# @req> REQ-38099593@_nWaC_p_1ziz dek4pk
def unreadable(part):
    quote = None
    for char in part:
        if char in "'\"" and quote in (None, char):
            quote = None if quote else char
        elif (char in "\\$`" and quote != "'") or (char in "{<()" and not quote):
            return f"'{char}'"
    return "a line break" if "\n" in part else None


# @req> REQ-38099593@_nWaC_p_1ziz j6ubo7
def only_reads(words):
    tool, rest = (words[0], words[1:]) if words else ("", [])
    if tool == "sort":
        return not any(SORT_WRITES.match(word) for word in rest)
    if tool == "uniq":
        return ("--" not in rest and not GLOB_CHAR.search(" ".join(rest))
                and sum(word == "-" or not word.startswith("-") for word in rest) < 2)
    return tool in WRITES_NOTHING


def lists_files(words):
    return (any(len(name) > 2 and any(flag.startswith(name) for flag in LISTS_FILES)
                for name in (word.split("=", 1)[0] for word in words if word.startswith("--")))
            or words[:1] == ["file"] and short_flagged(words[1:], "f"))


def sink_runs(words):
    tool, *rest = words or [""]
    if tool == "awk":
        return any(word.startswith(AWK_PROGRAM_FILE) or (
            not word.startswith("-") and AWK_RUNS.search(word)) for word in rest)
    if tool != "sed":
        return False
    scripts, args = [], iter(rest)
    for word in args:
        if word in ("-e", "--expression"):
            scripts.extend(itertools.islice(args, 1))
        elif word.startswith("--expression="):
            scripts.append(word.partition("=")[2])
        elif word.startswith("-") and not SED_QUIET.fullmatch(word):
            return True
        elif not word.startswith("-") and not scripts:
            scripts.append(word)
    return not scripts or not all(SED_SCRIPT.fullmatch(script) for script in scripts)


# @req> REQ-38099593@_nWaC_p_1ziz 4h5lnn
def names_citation(cmd):
    reach = [{"split"}] + [set() for _ in OPENER]
    for char in cmd.replace("\\\n", "").translate(UNQUOTED):
        step = [set() for _ in reach]
        for matched, gaps in enumerate(reach):
            for gap in gaps:
                step[matched].add("split" if char in SPLITS else "plain" if gap == "empty" else gap)
                if gap == "plain":
                    continue
                if matched == len(OPENER):
                    if char in "+>-":
                        return True
                elif char == OPENER[matched]:
                    step[matched + 1].add("empty")
        reach = step
    return False


def refuse_destructive_push(words):
    # @req+ REQ-60587913@a-D0sKfFEs62 4aiv2n
    subcommand, rest = git_subcommand(words)
    if subcommand != "push":
        return
    for word in rest:
        name = word.split("=", 1)[0]
        if ((len(name) > 2 and name.startswith("--")
             and any(flag.startswith(name) for flag in PUSH_LONG_DESTRUCTIVE))
                or short_flagged([word], "f") or short_flagged([word], "d")
                or (len(word) > 1 and word[0] in "+:")):
            deny(f"Push with {word} blocked: it rewrites or deletes remote "
                 "history. Ask the owner if that is really wanted.")
    # @req- 4aiv2n


def left():
    remaining = DEADLINE - time.monotonic()
    if remaining <= 0:
        deny(UNREADABLE)
    return remaining


def git_reads(args, place):
    if place is None:
        return None
    here, where, settings = place
    try:
        done = subprocess.run(
            ["git", "-C", here, *where, "-c", "core.fsmonitor=false", *args],
            capture_output=True, text=True, timeout=min(15, left()),
            env={**os.environ, **settings})
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


@functools.cache
def builtins():
    listed = git_reads(["--list-cmds=builtins,main,others"], ("/", [], {}))
    if listed is None:
        deny(BLIND_GIT)
    return set(listed.split())


def unfiltered(place):
    listed = git_reads(["config", "--show-scope", "--name-only", "--list"], place)
    if listed is None:
        deny(BLIND_GIT)
    trusted = () if place[2].keys() - set(REPO_ENV) else TRUSTED_SCOPES
    drivers = {key.rpartition(".")[0]
               for scope, _, key in (line.partition("\t") for line in listed.splitlines())
               if key.startswith("filter.") and scope not in trusted}
    return [f"--config-env={driver}.{command}=UNFILTERED"
            for driver in sorted(drivers) for command in ("clean", "process")]


def recursion(subcommand, rest, place):
    if subcommand == "clean":
        return None
    flag = next((word for word in reversed(rest) if word.startswith(("--rec", "--no-rec"))), None)
    if flag:
        return flag if flag.startswith("--rec") else None
    said = git_reads(["config", "--type=bool", "--default", "false", "--get", "submodule.recurse"],
                     place)
    return None if said == "false\n" else "submodule.recurse"


def short_flagged(flags, letter):
    return any(word.startswith("-") and not word.startswith("--")
               and letter in word[1:] for word in flags)


def discarded(words, place):
    subcommand, rest = git_subcommand(words)
    separated = "--" in rest
    after = rest[rest.index("--") + 1:] if separated else []
    before = rest[:rest.index("--")] if separated else rest
    flags, valued = [], False
    for word in before:
        if not valued and word.startswith("-"):
            flags.append(next((full for full in LONG_FLAGS if len(word) > 3
                               and full.startswith(word.split("=", 1)[0])), word))
        valued = not valued and word.startswith("-") and (
            not word.startswith("--") and word.find("e") == len(word) - 1
            or len(word) > 3 and "--exclude".startswith(word))
    operands = [word for word in rest if not word.startswith("-")]
    forced = any(flag in FORCE for flag in flags) or short_flagged(flags, "f")
    if subcommand == "reset":
        return (WHOLE_TREE, False, False) if "--hard" in flags else (None, False, False)
    if subcommand == "clean":
        if not forced or any(not f.startswith("--") and "n" in f[1:].split("e", 1)[0]
                                for f in flags) or "--dry-run" in flags:
            return None, False, False
        ignored = short_flagged(flags, "x") or short_flagged(flags, "X")
        return (after or WHOLE_TREE), True, ignored
    if subcommand == "restore":
        if "--staged" in flags and "--worktree" not in flags:
            return None, False, False
        return (after or operands or WHOLE_TREE), False, False
    if separated:
        return after, False, False
    if forced or "." in operands:
        return WHOLE_TREE, False, False
    if subcommand == "checkout" and operands:
        tree = git_reads(["rev-parse", "--verify", "--quiet", f"{operands[0]}^{{commit}}"],
                         place)
        return (operands[1:] if tree is not None else operands) or None, False, False
    return None, False, False


def refuse_discarding_work(words, here):
    # @req+ REQ-36282702@sK_P4PZZM9_w uivqls
    subcommand, rest = git_subcommand(words)
    if subcommand not in RESTORES:
        return
    place = located(words, here)
    if git_reads(["rev-parse", "--git-dir"], place) is None:
        deny(BLIND_GIT)
    paths, sweeps_untracked, sweeps_ignored = discarded(words, place)
    if paths is None:
        return
    source = recursion(subcommand, rest, place)
    if source:
        staged = git_reads(["ls-files", "--stage"], place)
        if staged is None or any(line.startswith("160000 ") for line in staged.splitlines()):
            deny(INTO_SUBMODULES.format(source=source))
    args = [*unfiltered(place), "status", "--porcelain", "--ignore-submodules=dirty"]
    if sweeps_ignored:
        args.append("--ignored")
    if paths:
        args += ["--", *paths]
    said = git_reads(args, (*place[:2], {**place[2], "UNFILTERED": ""}))
    if said is None:
        deny(BLIND_GIT)
    swept = UNTRACKED if sweeps_ignored else UNTRACKED_ONLY
    at_risk = [f"  {line}" for line in said.splitlines() if line.strip()
               and (line[:2] in swept) == sweeps_untracked]
    if at_risk:
        deny(DISCARDS_WORK.format(listing="\n".join(at_risk)))
    # @req- uivqls


def refuse_commit_on_default(words, here):
    # @req+ REQ-74982341@IIwAqzZV1bP3 zm6qoo
    subcommand, rest = git_subcommand(words)
    if subcommand != "commit" and (subcommand not in NO_COMMIT or next(
            (w for w in reversed(rest) if w in NO_COMMIT[subcommand]
             or w in ("--commit", "--no-squash", "--ff", "--no-ff")), None)
            in NO_COMMIT[subcommand]):
        return
    place = located(words, here)
    branch = git_reads(["branch", "--show-current"], place)
    if branch is None:
        deny(BLIND_GIT)
    default = git_reads(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], place)
    if default is None:
        deny(NO_DEFAULT)
    branch = branch.strip()
    if default.strip() == f"origin/{branch}":
        deny(ON_DEFAULT.format(branch=branch))
    # @req- zm6qoo


BARE_SWEEP = (".", "..", "/", "~", "*")


def judge_command(words, here):
    refuse_destructive_push(words)
    # @req+ REQ-70178381@2GE_TPwGTZKU dbuwzq
    subcommand, _ = git_subcommand(words)
    if subcommand in ("apply", "am"):
        deny(f"git {subcommand} blocked: the paths it writes live inside the "
             "patch, where this guard cannot see them. Use the editing tools, "
             "and reqctl for the corpus.")
    called = invoked(words)
    operands = called[1:]
    plain = called[0] if called else None
    if plain == "patch":
        deny("patch(1) blocked: the paths it writes live inside the diff, "
             "where this guard cannot see them. Use the editing tools, and "
             "reqctl for the corpus.")
    # @req- dbuwzq
    # @req> REQ-21901290@fc_rdI5ms5IC 2vz6iw
    # @req> REQ-22704490@0I1yKEFWt0tX 6cxbfo
    if plain == "rm" and any(
            (len(w) > 2 and "--recursive".startswith(w))
            or (w.startswith("-") and not w.startswith("--") and "r" in w.lower())
            for w in operands):
        project = os.environ.get("CLAUDE_PROJECT_DIR", "").rstrip("/")
        above = [project, *map(str, Path(project).parents)] if project else []
        alternatives = {w: list(itertools.islice(braced(os.path.expanduser(w)), 257))
                        for w in operands}
        swept = next(
            (w for w in operands if os.path.normpath(w) in BARE_SWEEP
             or "$" in w or "`" in w or w.startswith(("~+", "~-"))
             or len(alternatives[w]) > 256 or SEQUENCE.search(w)
             or any("{" in alt and "," in alt for alt in alternatives[w])
             or any(expands_to(os.path.normpath(os.path.join(here, alt)), path)
                    for alt in alternatives[w] for path in above)
             or GLOB_CHAR.search(w) and reaches_corpus(w, here, True)),
            None)
        if swept:
            deny(f"rm -r of '{swept}' blocked: it sweeps the requirements "
                 "corpus along with everything else. Name the paths to delete.")
    for word in words:
        if "git" in word and "push" in word and word not in ("git", "push"):
            refuse_destructive_push(tokens_of(word))
    refuse_commit_on_default(words, here)
    refuse_discarding_work(words, here)
    for script in scripts_within(words, here):
        judge_shell(script, here)


def scripts_within(words, here):
    tool, *rest = invoked(words) or [""]
    if tool in SHELLS:
        at = next((i for i, word in enumerate(rest) if short_flagged([word], "c")), None)
        return [] if at is None else next(
            ([word] for word in rest[at + 1:] if not word.startswith("-")), [])
    if tool == "eval":
        return [" ".join(rest)]
    if tool == "find":
        return [shlex.join(itertools.takewhile(lambda word: word not in (";", "+"), rest[at + 1:]))
                for at, word in enumerate(rest) if word in FIND_RUNS]
    split = git_split(words)
    place = located(words, here) if split else None
    if place is None or split[2] in builtins():
        return []
    prefix, options, subcommand, args = split
    value = git_reads(["config", "--default", "", "--get", f"alias.{subcommand}"], place)
    if value is None:
        deny(BLIND_GIT)
    if value.startswith("!"):
        top = git_reads(["rev-parse", "--show-toplevel"], place)
        if top is None:
            deny(BLIND_GIT)
        return [f"cd {shlex.quote(top.strip())} && "
                + " ".join([value[1:].strip(), *map(shlex.quote, args)])]
    return [shlex.join([*prefix, "git", *options, *tokens_of(value), *args])] if value.strip() else []


def braced(word):
    found = BRACE.search(word)
    if not found:
        yield word
        return
    for choice in found.group(1).split(","):
        yield from braced(word[:found.start()] + choice + word[found.end():])


def expands_to(pattern, path):
    wanted, held = pattern.split("/"), path.split("/")
    return pattern == path or len(wanted) == len(held) and all(
        fnmatch.fnmatchcase(name, glob.replace("[^", "[!")) for glob, name in zip(wanted, held))


def glob_alternatives(segment):
    if segment.startswith("{") and segment.endswith("}"):
        return segment[1:-1].split(",")
    return [segment]


def is_corpus_root(word):
    _, _, value = word.rpartition("=")
    trimmed = value.rstrip("/")
    if not trimmed:
        return False
    if trimmed.rsplit("/", 1)[-1] == CORPUS_ROOT_NAME:
        return True
    return any(
        GLOB_CHAR.search(segment) and LITERAL_CHAR.search(segment)
        and any(fnmatch.fnmatchcase(CORPUS_ROOT_NAME, alt)
                for alt in glob_alternatives(segment))
        for segment in trimmed.split("/"))


def matches(pattern):
    left()
    found = ["/"]
    for segment in pattern.split("/")[1:]:
        if not GLOB_CHAR.search(segment):
            found = [os.path.join(base, segment) for base in found]
            continue
        found = [os.path.join(base, name) for base in found for name in listing(base)
                 if fnmatch.fnmatchcase(name, segment.replace("[^", "[!"))
                 and (segment.startswith(".") or not name.startswith("."))]
    return [path for path in found if os.path.lexists(path)]


@functools.cache
def listing(base):
    if listing.cache_info().currsize >= GLOB_LIMIT:
        deny(UNREADABLE)
    try:
        return os.listdir(base)
    except OSError:
        return []


def reached(path, root):
    parts = path.split("/")
    for at, segment in enumerate(parts):
        rest = parts[at + 1:]
        if bool(rest) == root or not expands_to(segment, CORPUS_ROOT_NAME):
            continue
        if rest and not any(expands_to(rest[0], entry) for entry in CORPUS_ENTRIES):
            continue
        tail = "/".join(rest)
        if any(os.path.isdir(found) and (not GLOB_CHAR.search(tail) or matches(f"{found}/{tail}"))
               for found in matches("/".join([*parts[:at], CORPUS_ROOT_NAME]))):
            return True
    return False


@functools.lru_cache(maxsize=4096)
def reaches_corpus(word, cwd, root=False):
    value = word.rpartition("=")[2]
    if not value or "$" in value or "`" in value:
        return False
    paths = (os.path.normpath(os.path.join(cwd, alt))
             for alt in itertools.islice(braced(os.path.expanduser(value)), 257))
    return any(os.path.isabs(path) and reached(path, root) for path in paths)


def names_corpus(part, cwd):
    if CORPUS_DIR.search(part):
        return True
    operands = [GLUED_OPTION.sub("", word) for word in tokens_of(heading(part))]
    return any(CORPUS_DIR.search(word) or is_corpus_root(word)
               or reaches_corpus(word, cwd) for word in operands)


def judge_shell(raw, cwd):
    # @req+ REQ-22704490@0I1yKEFWt0tX ak47k7
    cmd = flatten(ESCAPE.sub("", raw))
    joins = []
    pipelines = scan(AMP_REDIRECT.sub(" ", cmd), joins)
    places = cwds(pipelines, joins, cwd)
    unquoted = QUOTED_REDIRECT.sub(r"\1\3", cmd)
    redirect = REDIRECT.search(masked(unquoted)) or next(
        (found for found in REDIRECT_TARGET.finditer(masked(unquoted))
         if any(CORPUS_DIR.search(word) or reaches_corpus(word, here)
                for word in tokens_of(unquoted[found.start(1):found.end(1)])
                for here in {cwd}.union(*places))), None)
    if redirect:
        deny(NOT_A_KNOWN_READ.format(target=unquoted[redirect.start():redirect.end()]))
    written = scan(AMP_REDIRECT.sub(" ", ESCAPE.sub("", raw)))
    running = next((heading(part).strip() for pipeline in written for part in pipeline
                    for words in [tokens_of(heading(part))]
                    if lists_files(words) or sink_runs(words)), None)
    if list(map(len, written)) != list(map(len, pipelines)):
        running = running or heading(raw).strip()
    for pipeline, heres in zip(pipelines, places):
        for part, here in itertools.product(pipeline, heres):
            judge_command(tokens_of(part), here)
            invocation = heading(part)
            # @req> REQ-54260750@MTrWbA9_HZWY 37auve
            if CONTENT_READ.search(invocation) and names_corpus(invocation, here):
                deny(DIRECT_READ.format(target=invocation.strip()))
        naming = [part for part in pipeline if any(names_corpus(part, here) for here in heres)]
        if not naming:
            continue
        whole = " ".join(pipeline)
        flag = SUBSHELL.search(whole) or OUTPUT_FLAG.search(whole)
        if flag:
            deny(NOT_A_KNOWN_READ.format(target=flag.group()))
        # @req> REQ-54260750@MTrWbA9_HZWY qrdgnw
        if running:
            deny(NOT_A_KNOWN_READ.format(target=running))
        for part in pipeline:
            if READ.search(part) or GIT_READ.search(part):
                continue
            if (part not in naming and SINK.search(part)
                    and not SINK_WRITES.search(part)):
                continue
            deny(NOT_A_KNOWN_READ.format(target=heading(part).strip()))
    # @req- ak47k7


def cwds(pipelines, joins, cwd):
    places, heres, start = [], {cwd}, {cwd}
    for pipeline, before, after in zip(pipelines, [";", *joins], joins):
        certain = before not in ("&&", "||")
        start = heres if certain else start
        places.append(tuple(sorted(heres)))
        heres = moved(pipeline, heres, certain)
        heres = start if after == "&" else heres
    return places


def moved(pipeline, heres, certain):
    called = invoked(tokens_of(heading(pipeline[0]))) if len(pipeline) == 1 else []
    if called[:1] != ["cd"]:
        return heres
    target = os.path.expanduser(next(
        (word for word in called[1:] if word == "-" or not word.startswith("-")), "~"))
    there = {os.path.normpath(os.path.join(here, target))
             if os.path.isabs(os.path.join(here, target)) and target != "-"
             and "$" not in target and "`" not in target else "" for here in heres}
    return there if certain else heres | there


def citations(text):
    if "\0" in text:
        return Counter()
    return Counter(line.strip() for line in text.split("\n")
                   if CITATION_LINE.match(line))


def edited(tool, args, cwd):
    target = Path(cwd, os.path.expanduser(args.get("file_path") or ""))
    try:
        before = target.read_bytes().decode().replace("\r\n", "\n") if target.is_file() else ""
    except (OSError, UnicodeError):
        deny(UNREADABLE)
    if tool == "Write":
        return before, args.get("content", "")
    after = before
    for edit in args.get("edits") if tool == "MultiEdit" else [args]:
        old, new = edit.get("old_string", ""), edit.get("new_string", "")
        if not isinstance(old, str) or not isinstance(new, str):
            deny(UNREADABLE)
        if old and old not in after and any(
                CITATION_LINE.match(line) for text in (after, new) for line in text.split("\n")):
            deny(INEXACT)
        if not new and not old.endswith("\n") and old + "\n" in after:
            old += "\n"
        after = after.replace(old, new, -1 if edit.get("replace_all") else 1)
    return before, after


def notebook_edited(args, cwd):
    target = Path(cwd, os.path.expanduser(args.get("notebook_path") or ""))
    mode, new = args.get("edit_mode") or "replace", args.get("new_source", "")
    try:
        cells = json.loads(target.read_bytes()).get("cells") if target.is_file() else []
    except (OSError, ValueError, AttributeError):
        deny(UNREADABLE)
    if not isinstance(new, str) or not isinstance(cells, list):
        deny(UNREADABLE)
    index = re.fullmatch(r"cell-(\d+)", str(args.get("cell_id")))
    held = next((cell for cell in cells if isinstance(cell, dict)
                 and cell.get("id") == args.get("cell_id")), None)
    if held is None and index and int(index[1]) < len(cells):
        held = cells[int(index[1])]
    if mode == "insert":
        held = {}
    if not isinstance(held, dict):
        deny(UNREADABLE)
    source = held.get("source", "")
    before = "".join(map(str, source)) if isinstance(source, list) else str(source)
    return before, "" if mode == "delete" else new


# @req> REQ-38099593@_nWaC_p_1ziz 3yvytz
def judge_citation_edit(tool, args, cwd):
    if tool == "NotebookEdit":
        before, after = notebook_edited(args, cwd)
    elif tool in ("Edit", "MultiEdit", "Write"):
        before, after = edited(tool, args, cwd)
    else:
        return
    if not isinstance(after, str):
        deny(UNREADABLE)
    if citations(before) != citations(after):
        deny(f"{HAND_CITATION}\nIn {args.get('file_path') or args.get('notebook_path')}.")


# @req> REQ-38099593@_nWaC_p_1ziz cebvfg
def judge_citation_shell(raw):
    cmd = ESCAPE.sub("", raw)
    if not names_citation(cmd):
        return
    for part in (part for pipeline in scan(QUIET_REDIRECT.sub(" ", cmd))
                 for part in pipeline):
        found = unreadable(part)
        if found:
            deny(UNREAD_COMMAND.format(found=found))
        if ">" in masked(part) or OUTPUT_FLAG.search(part.translate(UNQUOTED)):
            deny(f"{HAND_CITATION}\nIn {part.strip()}")
        tool, flag = searched(part)
        if flag:
            deny(f"{tool} {flag} in a command naming a statement citation "
                 f"blocked: such a command may only read.\nSearch without {flag}.")
        words = tokens_of(part)
        git = GIT_READ.search(part)
        if tool or (git and git["read"]) or only_reads(words):
            continue
        deny(NOT_A_READ.format(tool=words[0]))


def decide(data: dict) -> None:
    tool = str(data.get("tool_name") or "")
    args = data.get("tool_input")
    # @req+ REQ-18701923@7CvKXOjSI6Kb hyuozw
    if args is None:
        args = {}
    if not isinstance(args, dict):
        deny(UNREADABLE)
    for key in ("file_path", "notebook_path", "command"):
        if args.get(key) is not None and not isinstance(args[key], str):
            deny(UNREADABLE)
    # @req- hyuozw
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    cwd = os.path.abspath(cwd)

    # @req> REQ-22704490@0I1yKEFWt0tX qfasw3
    if tool not in ("Bash", "Read", "Grep", "Glob"):
        for value in named_paths(args) + bare_paths(args):
            named = flatten(value.replace("\\", "/"))
            if ITEM.search(named):
                deny(f"Direct write of a requirement item blocked: {value}\n{USE_REQCTL}")
            if BASELINE.search(named):
                deny(
                    f"Baselines are generated, never written directly: {value}\n"
                    "Use `reqctl baseline --generate`; approval is the owner's, "
                    "on a pull request."
                )
            if CORPUS_DIR.search(named) or reaches_corpus(named, cwd):
                deny(f"Direct write into the requirements corpus blocked: {value}\n"
                     f"{USE_REQCTL}")

    # @req> REQ-54260750@MTrWbA9_HZWY xkcay3
    if tool in ("Read", "Grep", "Glob"):
        paths = named_paths(args)
        values = paths + named_paths(args, GLOB_KEY if tool == "Glob" else GREP_GLOB_KEY)
        for value in values:
            named = flatten(value.replace("\\", "/"))
            if (CORPUS_DIR.search(named) or is_corpus_root(named)
                    or value in paths and reaches_corpus(named, cwd)):
                deny(DIRECT_READ.format(target=value))

    judge_citation_edit(tool, args, cwd)
    for value in named_paths(args, COMMAND_KEY):
        judge_shell(value, cwd)
        judge_citation_shell(value)


def main() -> None:
    # @req+ REQ-18701923@7CvKXOjSI6Kb mvehq6
    try:
        data = json.load(sys.stdin)
    except Exception:
        deny(UNREADABLE)
    if not isinstance(data, dict):
        deny(UNREADABLE)
    # @req- mvehq6
    # @req+ REQ-51060455@DPy54WGr0ngb 4gmqti
    try:
        decide(data)
    except Exception:
        deny(UNREADABLE)
    sys.exit(0)
    # @req- 4gmqti


if __name__ == "__main__":
    # @req> REQ-38288492@4l6tMNjp19tH bhnqhd
    main()
