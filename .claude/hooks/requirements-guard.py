#!/usr/bin/env python3

import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ITEM_FOLDERS = {"reqs": "REQ", "guards": "GUARD", "params": "PARAM",
                "terms": "TERM", "data": "DATA"}
_ITEMS = "|".join(ITEM_FOLDERS)
_UIDS = "|".join(ITEM_FOLDERS.values())
_CORPUS = f"{_ITEMS}|baselines"
_BASELINE_FILE = r"requirements/baseline\.ya?ml"

ITEM = re.compile(rf"requirements/({_ITEMS})/({_UIDS})-\d{{8}}\.ya?ml$")
BASELINE = re.compile(rf"requirements/baselines/|{_BASELINE_FILE}")
CORPUS_DIR = re.compile(
    rf"requirements/({_CORPUS})(?![\w.-])"
    rf"|{_BASELINE_FILE}"
    r"|requirements/[^/\s]*[*?{\[]"
    r"|\bcd\s+requirements\b"
)
CORPUS_ROOT_NAME = "requirements"
REDIRECT = re.compile(rf">>?\s*\S*(requirements/({_CORPUS})|{_BASELINE_FILE})")
REDUNDANT = re.compile(r"/(?:\./)+|//+")
PARENT = re.compile(r"(^|/)(?!\.\./)[^/]+/\.\./")
PATH_KEY = re.compile(
    r"(^|_|[a-z])(path|paths|pathname|file|files|filename|filenames|dest"
    r"|destination|dir|directory|target|output|src|dst|source|to|uri)$", re.I)
COMMAND_KEY = re.compile(r"(^|_|[a-z])(command|cmd|script|shell)$", re.I)
GLOB_KEY = re.compile(r"(^|_|[a-z])pattern$", re.I)
READ_VERBS = ("cat", "head", "tail", "less", "more", "nl", "wc", "ls", "stat",
              "file", "grep", "rg", "diff", "cut", "jq", "reqctl", "echo", "printf",
              "cmp", "sha1sum", "sha256sum", "sha512sum", "md5sum", "cksum", "du",
              "tree", "realpath", "basename", "dirname", "column", "test")
NAME_ONLY = ("ls", "stat", "file", "reqctl", "echo", "printf", "du", "tree",
             "realpath", "basename", "dirname", "test")
READ = re.compile(rf"^\s*({'|'.join(READ_VERBS)})\b")
CONTENT_READ = re.compile(
    rf"^\s*({'|'.join(v for v in READ_VERBS if v not in NAME_ONLY)})\b")
SINK = re.compile(
    r"^\s*(sort|uniq|awk|sed|tr|tac|rev|xxd|od|paste|fold|fmt)\b"
)
SINK_WRITES = re.compile(r"(?:^|\s)-(?:i|o|w)\b|--in-place|--output|>")
GIT_READ = re.compile(
    r"^\s*git(\s+(-[cC]\s+\S+|-[Pp]|--no-pager|--paginate))*"
    r"\s+(log|show|diff|status|blame|ls-files|add|commit)\b"
)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
AMP_REDIRECT = re.compile(r"\d*>&\s*\d*|&>>?")
SUBSHELL = re.compile(r"\$\(|`|<\(|>\(")
OUTPUT_FLAG = re.compile(r"--output\b|--in-place\b")
PUSH_SHORT_FORCE = re.compile(r"^-[a-zA-Z]*f[a-zA-Z]*$")
ESCAPE = re.compile(r"\\(?=[A-Za-z0-9/])")
QUOTED_REDIRECT = re.compile(r"""(>>?\s*)(['"])([^'"]*)\2""")
GLOB_CHAR = re.compile(r"[*?\[\]{}]")
LITERAL_CHAR = re.compile(r"[^*?\[\]{}]")

CITATION = re.compile(r"@req[+>-]")
UNQUOTED = str.maketrans("", "", "'\"\\")
CITATION_LINE = re.compile(r"^\s*(?:#+|<!--)\s*@req[+>-](?:\s|$)")

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
    f"forms blocked.\n{USE_REQCTL}"
)

DIRECT_READ = (
    "Direct read of the requirements corpus blocked.\n"
    "Read it through reqctl instead: `reqctl context UID`, `reqctl export`."
)

BLIND_GIT = (
    "The guard could not read the repository, so it cannot judge this call.\n"
    "Denying rather than allowing, as with any call it cannot read. Tell the "
    "owner if this repeats."
)

ON_MAIN = (
    "Commit on main blocked.\n"
    "  git checkout -b claude/<name>\n"
    "main is what the owner merges into, never what an agent commits to."
)

DISCARDS_WORK = (
    "This discards uncommitted work:\n"
    "{listing}\n"
    "Commit it first, then run the command -- or ask the owner."
)

HAND_CITATION = (
    "A statement citation is written only by reqctl.\n"
    "  reqctl tag PATH --from N --to M --req UID | reqctl repin ID | reqctl untag ID"
)

WHOLE_TREE: list[str] = []
FORCE = ("-f", "--force", "--discard-changes")
RESTORES = ("checkout", "restore", "reset", "clean", "switch")
UNTRACKED = ("??", "!!")
UNTRACKED_ONLY = ("??",)


def named_paths(value, keys=PATH_KEY, key=""):
    if isinstance(value, str):
        return [value] if keys.search(key) else []
    if isinstance(value, dict):
        return [found for k, v in value.items() for found in named_paths(v, keys, k)]
    if isinstance(value, list):
        return [found for v in value for found in named_paths(v, keys, key)]
    if keys.search(key):
        deny(UNREADABLE)
    return []


def flatten(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = REDUNDANT.sub("/", text)
        text = PARENT.sub(r"\1", text)
    return text


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def scan(cmd: str) -> list[list[str]]:
    commands, pipeline, buf = [], [], []
    quote = None
    lines = cmd.split("\n")
    row = 0

    def cut_segment():
        pipeline.append("".join(buf))
        buf.clear()

    def cut_command():
        cut_segment()
        commands.append(list(pipeline))
        pipeline.clear()

    while row < len(lines):
        line, i = lines[row], 0
        while i < len(line):
            char = line[i]
            if quote:
                if quote == '"' and char == "\\" and i + 1 < len(line):
                    buf.append(line[i:i + 2])
                    i += 2
                    continue
                buf.append(char)
                quote = None if char == quote else quote
                i += 1
                continue
            if char in "'\"":
                quote = char
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
                cut_command()
                i += 2 if line[i:i + 2] in (";;", "&&", "||") else 1
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
        opened = HEREDOC.search("".join(buf))
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
    return [[s for s in p if s.strip()] for p in commands
            if any(s.strip() for s in p)]


def masked(cmd):
    out, quote = [], None
    i = 0
    while i < len(cmd):
        char = cmd[i]
        if quote:
            if quote == '"' and char == "\\" and i + 1 < len(cmd):
                out.append("  ")
                i += 2
                continue
            out.append(" " if char != quote else char)
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
            out.append(char)
        else:
            out.append(char)
        i += 1
    return "".join(out)


def tokens_of(part):
    words, buf, quote, seen = [], [], None, False
    for char in part + " ":
        if quote:
            if char == quote:
                quote = None
            else:
                buf.append(char)
            continue
        if char in "'\"":
            quote = char
            seen = True
            continue
        if char.isspace():
            if buf or seen:
                words.append("".join(buf))
                buf, seen = [], False
            continue
        buf.append(char)
    return words


def git_subcommand(words):
    i = 0
    while i < len(words) and (words[i] in ("env", "command") or "=" in words[i]):
        i += 1
    if i >= len(words) or words[i] != "git":
        return None, []
    i += 1
    while i < len(words):
        word = words[i]
        if word in ("-c", "-C", "--work-tree", "--git-dir"):
            i += 2
            continue
        if word.startswith("-"):
            i += 1
            continue
        return word, words[i + 1:]
    return None, []


def refuse_destructive_push(words):
    subcommand, rest = git_subcommand(words)
    if subcommand != "push":
        return
    for word in rest:
        if (word in ("--force", "--force-if-includes", "--mirror", "--delete", "-d")
                or word.startswith("--force-with-lease")
                or PUSH_SHORT_FORCE.match(word)
                or (len(word) > 1 and word[0] in "+:")):
            deny(f"Push with {word} blocked: it rewrites or deletes remote "
                 "history. Ask the owner if that is really wanted.")


def git_reads(args):
    root = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    try:
        done = subprocess.run(["git", "-C", root, *args],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def short_flagged(flags, letter):
    return any(word.startswith("-") and not word.startswith("--")
               and letter in word[1:] for word in flags)


def discarded(words):
    subcommand, rest = git_subcommand(words)
    if subcommand not in RESTORES:
        return None, False, False
    separated = "--" in rest
    after = rest[rest.index("--") + 1:] if separated else []
    flags = [word for word in rest if word.startswith("-")]
    operands = [word for word in rest if not word.startswith("-")]
    forced = any(flag in FORCE for flag in flags) or short_flagged(flags, "f")
    if subcommand == "reset":
        return (WHOLE_TREE, False, False) if "--hard" in flags else (None, False, False)
    if subcommand == "clean":
        if not forced:
            return None, False, False
        ignored = short_flagged(flags, "x") or short_flagged(flags, "X")
        return (after or operands or WHOLE_TREE), True, ignored
    if subcommand == "restore":
        if "--staged" in flags and "--worktree" not in flags:
            return None, False, False
        return (after or operands or WHOLE_TREE), False, False
    if separated:
        return after, False, False
    if forced or "." in operands:
        return WHOLE_TREE, False, False
    return None, False, False


def refuse_discarding_work(words):
    paths, sweeps_untracked, sweeps_ignored = discarded(words)
    if paths is None:
        return
    args = ["status", "--porcelain"]
    if sweeps_ignored:
        args.append("--ignored")
    if paths:
        args += ["--", *paths]
    said = git_reads(args)
    if said is None:
        deny(BLIND_GIT)
    swept = UNTRACKED if sweeps_ignored else UNTRACKED_ONLY
    at_risk = [f"  {line}" for line in said.splitlines() if line.strip()
               and (line[:2] in swept) == sweeps_untracked]
    if at_risk:
        deny(DISCARDS_WORK.format(listing="\n".join(at_risk)))


def refuse_commit_on_main(words):
    subcommand, _ = git_subcommand(words)
    if subcommand != "commit":
        return
    branch = git_reads(["branch", "--show-current"])
    if branch is None:
        deny(BLIND_GIT)
    if branch.strip() == "main":
        deny(ON_MAIN)


BARE_SWEEP = (".", "..", "/", "~", "*")


def judge_command(words):
    refuse_destructive_push(words)
    subcommand, _ = git_subcommand(words)
    if subcommand in ("apply", "am"):
        deny(f"git {subcommand} blocked: the paths it writes live inside the "
             "patch, where this guard cannot see them. Use the editing tools, "
             "and reqctl for the corpus.")
    plain = next((w for w in words if "=" not in w), None)
    if plain == "patch":
        deny("patch(1) blocked: the paths it writes live inside the diff, "
             "where this guard cannot see them. Use the editing tools, and "
             "reqctl for the corpus.")
    if plain == "rm" and any(w.startswith("-") and "r" in w.lower()
                             for w in words):
        project = os.environ.get("CLAUDE_PROJECT_DIR", "").rstrip("/")
        resolved = {w: os.path.normpath(os.path.join(project, w))
                    for w in words} if project else {}
        swept = next(
            (w for w in words if os.path.normpath(w) in BARE_SWEEP
             or w.startswith("$")
             or (project and resolved[w] == project)
             or (project and project.startswith(resolved[w] + "/"))),
            None)
        if swept:
            deny(f"rm -r of '{swept}' blocked: it sweeps the requirements "
                 "corpus along with everything else. Name the paths to delete.")
    for word in words:
        if "git" in word and "push" in word and word not in ("git", "push"):
            refuse_destructive_push(tokens_of(word))
    refuse_commit_on_main(words)
    refuse_discarding_work(words)


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


def names_corpus(part):
    if CORPUS_DIR.search(part):
        return True
    operands = tokens_of(part.split("\n", 1)[0])
    return any(CORPUS_DIR.search(word) or is_corpus_root(word)
               for word in operands)


def judge_shell(raw):
    cmd = flatten(ESCAPE.sub("", raw))
    if REDIRECT.search(masked(QUOTED_REDIRECT.sub(r"\1\3", cmd))):
        deny(NOT_A_KNOWN_READ)
    for pipeline in scan(AMP_REDIRECT.sub(" ", cmd)):
        for part in pipeline:
            judge_command(tokens_of(part))
            invocation = part.split("\n", 1)[0]
            if CONTENT_READ.search(invocation) and CORPUS_DIR.search(invocation):
                deny(DIRECT_READ)
        naming = [part for part in pipeline if names_corpus(part)]
        if not naming:
            continue
        whole = " ".join(pipeline)
        if SUBSHELL.search(whole) or OUTPUT_FLAG.search(whole):
            deny(NOT_A_KNOWN_READ)
        for part in pipeline:
            if READ.search(part) or GIT_READ.search(part):
                continue
            if (part not in naming and SINK.search(part)
                    and not SINK_WRITES.search(part)):
                continue
            deny(NOT_A_KNOWN_READ)


def citations(text):
    return Counter(line.strip() for line in text.splitlines()
                   if CITATION_LINE.match(line))


def edited(tool, args):
    target = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".", args.get("file_path") or "")
    try:
        before = target.read_text() if target.is_file() else ""
    except (OSError, UnicodeError):
        deny(UNREADABLE)
    if tool == "Write":
        return before, args.get("content", "")
    after = before
    for edit in args.get("edits") if tool == "MultiEdit" else [args]:
        old, new = edit.get("old_string", ""), edit.get("new_string", "")
        if not isinstance(old, str) or not isinstance(new, str):
            deny(UNREADABLE)
        after = after.replace(old, new, -1 if edit.get("replace_all") else 1)
    return before, after


# @req> GUARD-27415973@LyBZRXU1yogK amplla
def judge_citation_edit(tool, args):
    if tool not in ("Edit", "MultiEdit", "Write"):
        return
    before, after = edited(tool, args)
    if not isinstance(after, str):
        deny(UNREADABLE)
    if citations(before) != citations(after):
        deny(HAND_CITATION)


# @req> GUARD-27415973@LyBZRXU1yogK hs7agh
def judge_citation_shell(raw):
    for pipeline in scan(AMP_REDIRECT.sub(" ", flatten(ESCAPE.sub("", raw)))):
        if not any(CITATION.search(part.translate(UNQUOTED)) for part in pipeline):
            continue
        if SUBSHELL.search(" ".join(pipeline)) or OUTPUT_FLAG.search(" ".join(pipeline)):
            deny(HAND_CITATION)
        for part in pipeline:
            invocation = masked(part.split("\n", 1)[0])
            if ">" in invocation:
                deny(HAND_CITATION)
            if READ.search(part) or GIT_READ.search(part):
                continue
            if SINK.search(part) and not SINK_WRITES.search(invocation):
                continue
            deny(HAND_CITATION)


def decide(data: dict) -> None:
    tool = str(data.get("tool_name") or "")
    args = data.get("tool_input")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        deny(UNREADABLE)
    for key in ("file_path", "notebook_path", "command"):
        if args.get(key) is not None and not isinstance(args[key], str):
            deny(UNREADABLE)

    if tool not in ("Bash", "Read", "Grep", "Glob"):
        for value in named_paths(args):
            named = flatten(value.replace("\\", "/"))
            if ITEM.search(named):
                deny(f"Direct write of a requirement item blocked.\n{USE_REQCTL}")
            if BASELINE.search(named):
                deny(
                    "Baselines are generated, never written directly. Use "
                    "`reqctl baseline --generate`; approval is the owner's, on "
                    "a pull request."
                )
            if CORPUS_DIR.search(named):
                deny(f"Direct write into the requirements corpus blocked.\n{USE_REQCTL}")

    if tool in ("Read", "Grep", "Glob"):
        values = named_paths(args)
        if tool == "Glob":
            values = values + named_paths(args, GLOB_KEY)
        for value in values:
            named = flatten(value.replace("\\", "/"))
            if CORPUS_DIR.search(named):
                deny(DIRECT_READ)

    judge_citation_edit(tool, args)
    for value in named_paths(args, COMMAND_KEY):
        judge_shell(value)
        judge_citation_shell(value)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        deny(UNREADABLE)
    if not isinstance(data, dict):
        deny(UNREADABLE)
    try:
        decide(data)
    except Exception:
        deny(UNREADABLE)
    sys.exit(0)


if __name__ == "__main__":
    main()
