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
BRACE = re.compile(r"\{([^{},]*,[^{}]*)\}")
SEQUENCE = re.compile(r"\{(?=[^{}]*\})[^{}]*\.\.")
SETTER = re.compile(r"^(export|declare|typeset|local|read(only|array)?|mapfile|getopts"
                    r"|let)$|\$\{\w+(\[[^]]*\])?:?=")
UNQUOTED_WORD = re.compile(r"[\w@%+=:,./{}-]+")
PARAMETER = re.compile(r"\$\{[^{}]*\}")
STDIN_ARGUMENTS = re.compile(r"\bxargs\b|--pathspec-f")
WRAPPERS = ("env", "command", "nohup", "sudo", "doas", "timeout", "nice", "time",
            "exec", "xargs", "stdbuf", "builtin")
REDIRECTION = re.compile(r"\d*(?:<<<|<>|>\||>>|<<|<|>)")
SHELLS = ("sh", "bash", "dash", "zsh", "ksh")
ECHO_FLAGS = re.compile(r"-[neE]+")
FIND_RUNS = ("-exec", "-execdir", "-ok", "-okdir")
READ_OPTIONS = ("-C", "--git-dir", "--work-tree", "-c")
READ_FLAGS = ("--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs")
GIT_VALUED = (*READ_OPTIONS, "--namespace", "--config-env")
READ_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_LITERAL_PATHSPECS",
            "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS")
COMMAND_CONFIG = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
CONFIG_HOMES = ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
TRUSTED_SCOPES = ("system", "global")
CORPUS_ENTRIES = (*ITEM_FOLDERS, "baselines", "baseline.yml", "baseline.yaml")
GLOB_LIMIT = 4096
CWD_LIMIT = 64
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
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*")
AMP_REDIRECT = re.compile(r"[0-9]?>&[ \t]*[0-9]*|&>>?")
SUBSHELL = re.compile(r"\$\(|`|<\(|>\(")
_WORD = r"""(?:\\.|'[^']*'|"(?:\\.|[^"\\])*"|\$\((?:[^()]|\([^()]*\))*\)|`[^`]*`|[^\s()\\'"`;&<>])"""
COMPOUND = re.compile(
    r"(?:\s*(?:(?:if|then|elif|else|while|until|do|in|time(?:\s+-p)?|coproc(?:\s+\w+(?=\s*[({]))?)"
    r"(?![^\s(])|[!{](?!\S)|(?:for|select)\s+\w+|(?:for\s*)?\(\((?:[^()]|\([^()]*\))*\)\)"
    rf"|case\s+{_WORD}+\s+in(?!\S)|(?:function\s+)?[^\s()]+\s*\(\s*\)|function\s+\S+"
    rf"|\(?\s*{_WORD}*(?:\s*\|\s*{_WORD}*)*\s*\)))*")
CASE = re.compile(rf"(?<![^\s;&|(])(?:case(?=\s+{_WORD}+[\s;]+in(?![^\s;&|)]))|esac(?![^\s;&|)]))")
QUOTED_TO = {"'": re.compile("[^']*'"), "$'": re.compile(r"(?:\\.|[^\\'])*'", re.S)}
DQUOTED = re.compile(r'(?:\\.|[^"\\])*"', re.S)
TICKED = re.compile(r"(?:\\.|[^\\`])*`", re.S)
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
    "The requirements guard could not read {what}, so it cannot judge this "
    "tool call.\n"
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

UNKNOWN_GIT = (
    "git {subcommand} blocked: the guard finds no git command or alias of that name, so it "
    "cannot judge what runs.\n"
    "Spell the git command in full."
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
    if keys.search(key) and not isinstance(value, bool):
        deny(UNREADABLE.format(what=f"the {key} field"))
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
    commands, pipeline, buf, held, bodies, nest, pending = [], [], [], [], [], [], []
    joins = [] if joins is None else joins
    quote = None
    lines = cmd.split("\n")
    row = 0

    def joined(segment):
        return "".join(chunk if isinstance(chunk, str) else "".join(chunk) for chunk in segment)

    def cut_segment():
        pipeline.append([*held, *buf, *bodies])
        for chunks in (held, buf, bodies):
            chunks.clear()

    def cut_command(join=";"):
        cut_segment()
        if any(joined(s).strip() for s in pipeline):
            commands.append([s for s in pipeline if joined(s).strip()])
            joins.append(join)
        pipeline.clear()

    while row < len(lines):
        line, i, closed = lines[row], 0, -1
        while i < len(line):
            char = line[i]
            if quote:
                if quote != "'" and char == "\\" and i + 1 < len(line):
                    buf.append(line[i:i + 2])
                    i += 2
                    continue
                if quote == '"' and line.startswith(("$(", "${"), i):
                    nest.append('"' + line[i + 1])
                    quote = None
                    buf.append(line[i:i + 2])
                    i += 2
                    continue
                buf.append(char)
                if char == quote[-1]:
                    quote = '"' if quote == '"`' else None
                elif quote == '"' and char == "`":
                    quote = '"`'
                i += 1
                continue
            if char in "'\"`":
                quote = opened_quote(char, buf)
                buf.append(char)
                i += 1
                continue
            if char == "\\" and i + 1 < len(line):
                buf.append(line[i:i + 2])
                i += 2
                continue
            if nest[-1:] in (["${"], ['"{']):
                if char == "}":
                    quote = '"' if nest.pop() == '"{' else None
                elif buf[-1:] == ["$"] and char in "({":
                    nest.append("$" + char)
                buf.append(char)
                i += 1
                continue
            if char == "#" and (not buf or buf[-1] in (" ", "\t", "(", ";", "&", "|", "$(")
                                or closed == i - 1):
                break
            if (char == "<" and buf[-1:] != ["<"] and nest[-1:] not in (["(("], ["$["])
                    and (heredoc := heredoc_at(line, i))):
                delimiter, _, dash, end = heredoc
                bodies.append(slot := [])
                pending.append((delimiter, dash, slot, sum(entry != "(" for entry in nest)))
                buf.append(line[i:end])
                i = end
                continue
            if char == ")" and nest[-1:] in (["("], ["(("], ["$("], ['"(']):
                closed = i if nest[-1] == "(" else closed
                quote = '"' if nest.pop() == '"(' else None
            elif char == "]" and nest[-1:] == ["$["]:
                nest.pop()
            elif char == "(":
                nest.append("$(" if buf[-1:] in (["$"], ["<"], [">"])
                            else "((" if buf[-1:] in (["("], ["$("]) else "(")
            elif char == "[" and buf[-1:] == ["$"]:
                nest.append("$[")
            elif char == ")" and not nest:
                cut_command("&&")
            if nest:
                buf.append(char)
                i += 1
                continue
            if char == "|" and line[i:i + 2] != "||":
                cut_segment()
                i += 1
                continue
            if char in ";&|":
                join = char * 2 if line[i + 1:i + 2] == char else char
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
            if pending or buf[-2:-1] == ["<"]:
                deny(UNREADABLE.format(what="a heredoc continued onto the next line"))
            buf.pop()
            row += 1
            continue
        if pending and sum(entry != "(" for entry in nest) <= min(depth for *_, depth in pending):
            for delimiter, dash, slot, _ in pending:
                end = next((at for at in range(row + 1, len(lines))
                            if (lines[at].lstrip("\t") if dash else lines[at]) == delimiter),
                           len(lines))
                slot.append("\n" + "\n".join(lines[row + 1:end + 1]))
                row = end
            pending.clear()
        if nest:
            held.append("".join(buf) + ";")
            buf.clear()
        else:
            cut_command()
        row += 1
    cut_command()
    return [[joined(s) for s in p] for p in commands]


def opened_quote(char, before):
    run = next((i for i, chunk in enumerate(reversed(before)) if chunk != "$"), len(before))
    return "$'" if char == "'" and run % 2 else char


def heredoc_at(text, at):
    found = HEREDOC.match(text, at)
    if not found:
        return None
    word, quoted, i = [], False, found.end()
    while i < len(text) and text[i] not in " \t\n;&|()<>" and text[i:i + 2] not in ("\\", "\\\n"):
        dollar = text[i] == "$" and text[i + 1:i + 2] in ("'", '"')
        char = text[i + dollar]
        if char == "\\":
            word.append(text[i + 1:i + 2])
            quoted, i = True, i + 2
            continue
        if char not in "'\"":
            if char == "`" or text.startswith(("$(", "${"), i):
                break
            word.append(char)
            i += 1
            continue
        shut = (DQUOTED if char == '"' else QUOTED_TO["$'" if dollar else "'"]).match(
            text, i + dollar + 1)
        held = shut[0][:-1] if shut else ""
        if not shut or char == "'" and dollar and "\\" in held or char == '"' and any(
                mark in held for mark in ("$(", "${", "`")):
            break
        word.append(re.sub(r'\\([$`"\\])', r"\1", held.replace("\\\n", ""))
                    if char == '"' else held)
        quoted, i = True, shut.end()
    else:
        return ("".join(word), quoted, found[1] == "-", i) if word or quoted else None
    deny(UNREADABLE.format(what="the heredoc delimiter " + text[found.end():].partition("\n")[0]))


def end_of(text, at):
    if text[at] == "`":
        found = TICKED.match(text, at + 1)
        return found.end() if found else len(text)
    opener = text[at] if text[at] == '"' else text[at + 1]
    shut, i, depth = {'"': '"', "(": ")", "{": "}"}[opener], at + 1 + (opener != '"'), 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
        elif char == "`" or text.startswith(("$(", "${"), i) or char == '"' != opener:
            i = end_of(text, i)
        elif char == "'" and opener != '"':
            run = i
            while run > at and text[run - 1] == "$":
                run -= 1
            found = QUOTED_TO["$'" if (i - run) % 2 else "'"].match(text, i + 1)
            i = found.end() if found else len(text)
        else:
            i += 1
            depth += (char == "(" == opener) - (char == shut)
            if not depth:
                return i
    return len(text)


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
            if quote == '"' and (char == "`" or cmd.startswith(("$(", "${"), i)):
                end = end_of(cmd, i)
                out.append("_" * (end - i))
                i = end
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


def groups(text, opened=()):
    found, stack, pending, starts, i, dollars, last = [], list(opened), [], [], 0, 0, ""
    while i < len(text):
        char, top, step, size = text[i], (stack or [""])[-1], 1, len(stack)
        if char == "\\":
            step = 2
        elif char == "`":
            closing = TICKED.match(text, i + 1)
            step = (closing.end() if closing else len(text)) - i
            if not starts:
                found.append(re.sub(r"\\([\\`$])", r"\1", text[i + 1:i + step - bool(closing)]))
        elif top in ('"', "<<"):
            if char == top:
                stack.pop()
            elif text.startswith(("$(", "${"), i):
                step = 2
                stack.append(text[i + 1])
        elif char == "\n" and pending:
            for delimiter, literal, dash in pending:
                end = re.compile("\n" + "\t*" * dash + re.escape(delimiter) + "$", re.M).search(text, i)
                if not literal and not starts:
                    found += groups(text[i + 1:end.start() if end else len(text)], ["<<"])
                i = end.end() if end else len(text)
            pending.clear()
            continue
        elif char == "'":
            closing = QUOTED_TO["$'" if dollars % 2 else "'"].match(text, i + 1)
            step = (closing.end() if closing else len(text)) - i
        elif char == "#" and text[i - 1:i] in ("", " ", "\t", "\n", ";", "&", "|", "("):
            end = text.find("\n", i)
            step = (end if end >= 0 else len(text)) - i
        elif char == '"':
            stack.append(char)
        elif char == ")" and top == "(" or char == "}" and top == "{":
            stack.pop()
        elif char == ")" and top == "case" and starts:
            found.append(text[starts[-1]:i])
        elif char == "(" or char == "{" and last == "$":
            stack.append(char)
        elif keyword := CASE.match(text, i):
            if keyword[0] == "case":
                stack.append("case")
            elif top == "case":
                stack.pop()
            step = 4
        elif char == "<" and last != "<" and (heredoc := heredoc_at(text, i)):
            pending.append(heredoc[:3])
            step = heredoc[3] - i
        if len(stack) > size and stack[-1] == "(":
            starts.append(i + step)
        elif len(stack) < size and top == "(":
            body = text[starts.pop():i]
            if not starts:
                found.append(body)
        dollars = dollars + 1 if char == "$" and step == 1 else 0
        last = text[i:i + step]
        i += step
    if starts:
        found.append(text[starts[0]:])
    return found


def nested(part):
    at = COMPOUND.match(masked(part)).end()
    if at:
        return [part[at:], *groups(part[:at])]
    said = heading(part)
    return [script + part[len(said):] if script in said and HEREDOC.search(masked(script)) else script
            for script in groups(part)]


def tokens_of(part):
    words, buf, quote, seen, escaped, dollars, i = [], [], None, False, False, 0, 0
    while i < len(part):
        char = part[i]
        i += 1
        if escaped:
            buf.append(char)
            escaped, dollars = False, 0
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote in (None, '"') and (char == "`" or part.startswith(("$(", "${"), i - 1)):
            end = end_of(part, i - 1)
            buf.append(part[i - 1:end])
            i = end
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
        if char in "<>" and (buf or seen) and buf[-1:] not in (["<"], [">"]) and (
                seen or not "".join(buf).isdigit()):
            words.append("".join(buf))
            buf, seen = [], False
        buf.append(char)
    return words + ["".join(buf)] if buf or seen else words


def argv(said):
    words, bare = tokens_of(said), tokens_of(masked(said))
    if len(words) != len(bare):
        return words, bare
    kept, target = [], False
    for at, word in enumerate(bare):
        if target:
            target = False
        elif REDIRECTION.match(word) and not word.startswith(("<(", ">(")):
            target = REDIRECTION.fullmatch(word) is not None
        else:
            kept.append(at)
    return [words[at] for at in kept], [bare[at] for at in kept]


def invoked(words):
    i = 0
    while i < len(words) and (os.path.basename(words[i]) in WRAPPERS or "=" in words[i]
                              or REDIRECTION.match(words[i]) or (i and (
            words[i].startswith("-") or words[i][:1].isdigit()
            or words[i - 1].startswith("-") and os.path.basename(words[i]) not in JUDGED))):
        i += 2 if REDIRECTION.fullmatch(words[i]) else 1
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
    assigned = dict(word.split("=", 1) for word in prefix if "=" in word)
    settings = {name: value for name, value in assigned.items()
                if name in READ_ENV or name.startswith(COMMAND_CONFIG)}
    where = [word for at, word in enumerate(options)
             if word.partition("=")[0] in READ_OPTIONS or word in READ_FLAGS
             or at and options[at - 1] in READ_OPTIONS]
    hidden = next((word for word in prefix if word.startswith("-") or "=" in word and (
        not word.split("=", 1)[0].isidentifier() or word.split("=", 1)[0] in CONFIG_HOMES)),
        None) or next((word for word in [*prefix, *options]
                       if "{" in word.replace("{}", "")), None) or next(
        (word for word in options if word.startswith("--config-env")), None) or next(
        (word for word in [*where, *settings.values()] if "$" in word or "`" in word), None)
    if not here or hidden:
        deny(UNREADABLE.format(what=f"which repository git reaches past {hidden}" if hidden
                               else "the folder the command runs in"))
    return here, [os.path.expanduser(word) for word in where], settings


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


@functools.cache
def refuse_destructive_push(said):
    # @req+ REQ-60587913@a-D0sKfFEs62 4aiv2n
    subcommand, rest = git_subcommand(argv(said)[0])
    if subcommand != "push":
        return
    spelled_out, leftover = itertools.tee(alt for spelled in rest for alt in bounded(spelled))
    for word in itertools.chain(rest, spelled_out):
        name = word.split("=", 1)[0]
        if ((len(name) > 2 and name.startswith("--")
             and any(flag.startswith(name) for flag in PUSH_LONG_DESTRUCTIVE))
                or short_flagged([word], "f") or short_flagged([word], "d")
                or (len(word) > 1 and word[0] in "+:")):
            deny(f"Push with {word} blocked: it rewrites or deletes remote "
                 "history. Ask the owner if that is really wanted.")
    if found := next(filter(expands, leftover), None):
        deny(UNREADABLE.format(what="the braces of " + found))
    # @req- 4aiv2n


def left():
    remaining = DEADLINE - time.monotonic()
    if remaining <= 0:
        deny(UNREADABLE.format(what="the call before its time limit"))
    return remaining


def git_reads(args, place):
    here, options, settings = place
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", here, *options, "-c", "core.fsmonitor=false",
             *args],
            capture_output=True, text=True, timeout=min(15, left()),
            env={**os.environ, **settings, "UNFILTERED": ""})
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def git_sees(args, place):
    said = git_reads(args, place)
    if said is None:
        here, options, settings = place
        deny(UNREADABLE.format(what="the repository of " + " ".join(
            [*(f"{name}={value}" for name, value in settings.items()), "git -C", here, *options])))
    return said


@functools.cache
def git_commands(kinds):
    return set(git_sees([f"--list-cmds={kinds}"], ("/", [], {})).split())


def unfiltered(place):
    listed = git_sees(["config", "--show-scope", "--name-only", "--list"], place)
    drivers = {key.rpartition(".")[0]
               for scope, _, key in (line.partition("\t") for line in listed.splitlines())
               if key.startswith("filter.") and scope not in TRUSTED_SCOPES}
    return [f"--config-env={driver}.{command}=UNFILTERED"
            for driver in sorted(drivers) for command in ("clean", "process")]


def recursion(subcommand, rest, place):
    if subcommand == "clean":
        return None
    flag = next((word for word in reversed(rest) if len(word) > 2 and any(
        full.startswith(word.split("=", 1)[0])
        for full in ("--recurse-submodules", "--no-recurse-submodules"))), None)
    if flag:
        return None if flag.startswith("--no") else flag
    said = git_reads(["config", "--type=bool", "--default", "false", "--get", "submodule.recurse"],
                     place)
    return None if said == "false\n" else "submodule.recurse"


def short_flagged(flags, letter):
    return any(word.startswith("-") and not word.startswith("--")
               and letter in word[1:] for word in flags)


def discarded(subcommand, rest, place):
    separated = "--" in rest
    after = rest[rest.index("--") + 1:] if separated else []
    before = rest[:rest.index("--")] if separated else rest
    flags, operands, valued = [], [*after], False
    for word in before:
        if not valued and word.startswith("-"):
            flags.append(next((full for full in LONG_FLAGS if len(word) > 2
                               and full.startswith(word.split("=", 1)[0])), word))
        elif not valued:
            operands.append(word)
        valued = subcommand == "clean" and not valued and word.startswith("-") and (
            not word.startswith("--") and word.find("e") == len(word) - 1
            or len(word) > 2 and "--exclude".startswith(word))
    forced = any(flag in FORCE for flag in flags) or short_flagged(flags, "f")
    if subcommand == "reset":
        return (WHOLE_TREE, False, False) if "--hard" in flags else (None, False, False)
    if subcommand == "clean":
        if not forced or any(not f.startswith("--") and "n" in f[1:].split("e", 1)[0]
                                for f in flags) or "--dry-run" in flags:
            return None, False, False
        ignored = short_flagged(flags, "x") or short_flagged(flags, "X")
        return (operands if after else WHOLE_TREE), True, ignored
    if subcommand == "restore":
        if "--staged" in flags and "--worktree" not in flags and not short_flagged(flags, "W"):
            return None, False, False
        return (operands or WHOLE_TREE), False, False
    if separated and subcommand == "checkout":
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
    git_sees(["rev-parse", "--git-dir"], place)
    written = rest
    rest = [alt for word in rest for alt in bounded(word)]
    if found := next(filter(expands, rest), None):
        deny(UNREADABLE.format(what="the braces of " + found))
    sayings = [rest, written]
    if subcommand in ("clean", "restore"):
        sayings += [[word if word.startswith("-") else "-" for word in said[:said.index("--")]]
                    + said[said.index("--"):] for said in sayings if "--" in said[:-1]]
    readings = [reading for said in dict.fromkeys(map(tuple, sayings))
                if (reading := discarded(subcommand, said, place))[0] is not None]
    if not readings:
        return
    if found := next((word for word in rest if "{}" in word), None):
        deny(UNREADABLE.format(what="the {} in " + found))
    source = recursion(subcommand, rest, place)
    if source:
        top = git_sees(["rev-parse", "--show-cdup"], place).strip() or "."
        staged = git_reads(["ls-files", "--stage", "--", top], place)
        if staged is None or any(line.startswith("160000 ") for line in staged.splitlines()):
            deny(INTO_SUBMODULES.format(source=source))
    for paths, sweeps_untracked, sweeps_ignored in readings:
        args = [*unfiltered(place), "status", "--porcelain", "--untracked-files=normal",
                "--ignore-submodules=dirty"]
        if sweeps_ignored:
            args.append("--ignored")
        if paths:
            args += ["--", *paths]
        said = git_sees(args, place)
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
    branch = git_sees(["branch", "--show-current"], place).strip()
    default = git_reads(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], place)
    if default is None:
        deny(NO_DEFAULT)
    if default.strip() == f"origin/{branch}":
        deny(ON_DEFAULT.format(branch=branch))
    # @req- zm6qoo


BARE_SWEEP = (".", "..", "/", "~", "*")


def judge_command(said, here):
    words, unquoted = argv(said)
    refuse_destructive_push(said)
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
    # @req> REQ-74982341@IIwAqzZV1bP3 cqinxo
    # @req> REQ-36282702@sK_P4PZZM9_w pojxpe
    if hidden := next((word for word in unquoted[:len(words) - len(called) + 1]
                       if not word.partition("=")[0].isidentifier() and expands(word)), None) or (
            (setter := any(map(SETTER.search, words)) or "printf" in words
             and any(alt.startswith("-v") for word in words for alt in bounded(word)))
            or plain != "git") and next((
            word for word in (words if setter else words[:len(words) - len(called)])
            if (setter or "=" in word) and any(name in alt for alt in bounded(word)
                                               for name in (*READ_ENV, "GIT_CONFIG"))), None) or (
            setter and next((word for word in unquoted if any(map(expands, bounded(word)))), None)):
        deny(UNREADABLE.format(what=f"which command or repository {hidden} leads to"))
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
            refuse_destructive_push(word)
    refuse_commit_on_default(words, here)
    refuse_discarding_work(words, here)
    for script in scripts_within(words, here):
        judge_shell(script, here)


def scripts_within(words, here):
    tool, *rest = invoked(words) or [""]
    if tool in SHELLS:
        at = next((i for i, word in enumerate(rest) if short_flagged([word], "c")), None)
        return [] if at is None else [word for word in rest[at + 1:] if not word.startswith("-")]
    if tool == "eval":
        return [" ".join(rest)]
    if tool == "find":
        return [" ".join(word if UNQUOTED_WORD.fullmatch(word) else shlex.quote(word)
                         for word in itertools.takewhile(lambda word: word not in (";", "+"),
                                                         rest[at + 1:]))
                for at, word in enumerate(rest) if word in FIND_RUNS]
    split = git_split(words)
    if not split or any(split[2] in git_commands(kinds) for kinds in ("builtins", "main,others")):
        return []
    prefix, options, subcommand, args = split
    place = located(words, here)
    value = git_sees(["config", "--default", "", "--get", f"alias.{subcommand}"], place)
    if not value.strip():
        deny(UNKNOWN_GIT.format(subcommand=subcommand))
    if value.startswith("!"):
        top = git_sees(["rev-parse", "--show-toplevel"], place)
        return [f"cd {shlex.quote(top.strip())} && "
                + " ".join([value[1:].strip(), *map(shlex.quote, args)])]
    return [shlex.join([*prefix, "git", *options, *tokens_of(value), *args])]


def braced(word, room=256):
    found = room and BRACE.search(word)
    if not found:
        yield word
        return
    for choice in (choices := found.group(1).split(",")):
        yield from braced(word[:found.start()] + choice + word[found.end():], room // len(choices))


def expands_to(pattern, path):
    wanted, held = pattern.split("/"), path.split("/")
    return pattern == path or len(wanted) == len(held) and all(
        fnmatch.fnmatchcase(name, glob.replace("[^", "[!")) for glob, name in zip(wanted, held))


def glob_alternatives(segment):
    if segment.startswith("{") and segment.endswith("}"):
        return segment[1:-1].split(",")
    return [segment]


def is_corpus_root(word):
    for value in {word, word.rpartition("=")[2]}:
        trimmed = value.rstrip("/")
        if trimmed and (trimmed.rsplit("/", 1)[-1] == CORPUS_ROOT_NAME or any(
                GLOB_CHAR.search(segment) and LITERAL_CHAR.search(segment)
                and any(fnmatch.fnmatchcase(CORPUS_ROOT_NAME, alt)
                        for alt in glob_alternatives(segment))
                for segment in trimmed.split("/"))):
            return True
    return False


def matches(pattern):
    left()
    found = ["/"]
    for segment in pattern.split("/")[1:]:
        if not GLOB_CHAR.search(segment):
            found = [os.path.join(base, segment) for base in found]
            continue
        found = [os.path.join(base, name) for base in found for name in listing(base)
                 if expands_to(segment, name)
                 and (segment.startswith(".") or not name.startswith("."))]
    return [path for path in found if os.path.lexists(path)]


@functools.cache
def listing(base):
    if listing.cache_info().currsize >= GLOB_LIMIT:
        deny(UNREADABLE.format(what=f"a glob that lists more than {GLOB_LIMIT} folders"))
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
    paths = (os.path.normpath(os.path.join(cwd, alt))
             for value in {word, word.rpartition("=")[2]}
             if value and "$" not in value and "`" not in value
             for alt in bounded(os.path.expanduser(value)))
    return any(os.path.isabs(path) and reached(path, root) for path in paths)


def expands(word):
    bare = PARAMETER.sub("", word)
    return "{" in bare and ("," in bare or ".." in bare)


def bounded(word):
    found = list(itertools.islice(braced(word), 257))
    if len(found) > 256:
        deny(UNREADABLE.format(what=f"{word}, past 256 brace alternatives"))
    return found


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
            left()
            invocation = heading(part)
            judge_command(part if any(
                len(alternatives) > 256 or any(map(STDIN_ARGUMENTS.search, alternatives))
                for word in tokens_of(invocation)
                for alternatives in [list(itertools.islice(braced(word), 257))]) else invocation,
                here)
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
    for pipeline, heres in zip(pipelines, places):
        for part, here in itertools.product(pipeline, heres):
            for script in nested(part):
                left()
                judge_shell(script, here)
    for pipeline, heres in zip(pipelines, places):
        for here in heres:
            for script, there in dict.fromkeys(fed(pipeline, here)):
                left()
                judge_shell(script, there)
    # @req- ak47k7


def reads_input(script):
    return any((called := invoked(argv(part[COMPOUND.match(masked(part)).end():])[0]))[:1]
               and called[0] in SHELLS
               and not short_flagged(itertools.takewhile("--".__ne__, called[1:]), "c")
               for pipeline in scan(script) for part in pipeline)


def fed(pipeline, here):
    for at, part in enumerate(pipeline):
        said, bodies = heading(part), []
        if reads_input(said):
            bodies.append((part[len(said):], here))
            words, bare = tokens_of(said), tokens_of(masked(said))
            for word, mask, following in zip(words, bare, [*words[1:], ""]):
                if (operator := mask.lstrip("0123456789")).startswith("<<<"):
                    yield word[len(mask) - len(operator) + 3:] or following, here
        inner = nested(said)
        if at and any(map(reads_input, [said, *inner])):
            folders = visited(inner, here)
            for source in pipeline[:at]:
                before = heading(source)
                echoed = invoked(argv(before[COMPOUND.match(masked(before)).end():])[0])
                for there in folders:
                    bodies.append((source[len(before):], there))
                    if echoed[:1] == ["echo"]:
                        yield " ".join(itertools.dropwhile(ECHO_FLAGS.fullmatch, echoed[1:])), there
        for body, there in bodies:
            for script in dict.fromkeys((body, re.sub(r"\\([\\`$])", r"\1", body))):
                yield script, there


def visited(scripts, here):
    found = {here}
    for script in scripts:
        joins = []
        found.update(*cwds(scan(script, joins), joins, here))
    return sorted(found)


def cwds(pipelines, joins, cwd):
    places, heres, start, seen = [], {cwd}, {cwd}, {cwd}
    for pipeline, before, after in zip(pipelines, [";", *joins], joins):
        certain = before not in ("&&", "||")
        start = heres if certain else start
        places.append(sorted(heres))
        heres = start if after == "&" else moved(pipeline, heres, certain, seen)
        seen |= heres
        if len(heres) > CWD_LIMIT:
            deny(UNREADABLE.format(what=f"where the command runs, past {CWD_LIMIT} folders"))
    return places


def moved(pipeline, heres, certain, seen):
    said = heading(pipeline[-1])
    at = COMPOUND.match(masked(said)).end()
    certain = certain and not at and len(pipeline) == 1
    called = invoked(argv(said[at:])[0])
    if called[:1] == ["eval"]:
        called = invoked(tokens_of(" ".join(called[1:])))
    tool, *rest = called or [""]
    folder = next((word for word in rest if word == "-" or not word.startswith(
        "-" if tool == "cd" else ("-", "+"))), "~" if tool == "cd" else None)
    if tool == "popd" or tool == "pushd" and folder is None:
        return heres | seen
    if tool not in ("cd", "pushd"):
        return heres
    target = os.path.expanduser(folder)
    there = {os.path.normpath(joined) if os.path.isabs(joined) and target != "-"
             and "$" not in target and "`" not in target else ""
             for joined in (os.path.join(here, target) for here in heres)}
    return there if certain and tool == "cd" and all(map(os.path.isdir, there)) else heres | there


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
        deny(UNREADABLE.format(what=f"the file {target}"))
    if tool == "Write":
        return before, args.get("content", "")
    after = before
    for edit in args.get("edits") if tool == "MultiEdit" else [args]:
        old, new = edit.get("old_string", ""), edit.get("new_string", "")
        if not isinstance(old, str) or not isinstance(new, str):
            deny(UNREADABLE.format(what="the new_string field" if isinstance(old, str)
                                   else "the old_string field"))
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
        deny(UNREADABLE.format(what=f"the notebook {target}"))
    if not isinstance(new, str) or not isinstance(cells, list):
        deny(UNREADABLE.format(what=f"the cells of {target}" if isinstance(new, str)
                               else "the new_source field"))
    index = re.fullmatch(r"cell-(\d+)", str(args.get("cell_id")))
    held = next((cell for cell in cells if isinstance(cell, dict)
                 and cell.get("id") == args.get("cell_id")), None)
    if held is None and index and int(index[1]) < len(cells):
        held = cells[int(index[1])]
    if mode == "insert":
        held = {}
    if not isinstance(held, dict):
        deny(UNREADABLE.format(what=f"cell {args.get('cell_id')} of {target}"))
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
        deny(UNREADABLE.format(what="the content field"))
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
        deny(UNREADABLE.format(what="the tool input, which is not an object"))
    for key in ("file_path", "notebook_path", "command"):
        if args.get(key) is not None and not isinstance(args[key], str):
            deny(UNREADABLE.format(what=f"the {key} field"))
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
        deny(UNREADABLE.format(what="the hook input, which is not JSON"))
    if not isinstance(data, dict):
        deny(UNREADABLE.format(what="the hook input, which is not a JSON object"))
    # @req- mvehq6
    # @req+ REQ-51060455@DPy54WGr0ngb 4gmqti
    try:
        decide(data)
    except Exception as error:
        deny(UNREADABLE.format(what=f"the call: judging it raised {type(error).__name__}"))
    sys.exit(0)
    # @req- 4gmqti


if __name__ == "__main__":
    # @req> REQ-38288492@4l6tMNjp19tH bhnqhd
    main()
