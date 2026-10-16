#!/usr/bin/env python3

import fnmatch
import functools
import hashlib
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
from urllib.parse import unquote, urlsplit

ITEM_FOLDERS = {"reqs": "REQ", "guards": "GUARD", "params": "PARAM",
                "terms": "TERM", "data": "DATA"}
_ITEMS = "|".join(ITEM_FOLDERS)
_UIDS = "|".join(ITEM_FOLDERS.values())
_CORPUS = f"{_ITEMS}|baselines"
_ROOT = r"(?<![\w.-])requirements"
_BASELINE_FILE = rf"{_ROOT}/baseline\.ya?ml"

ITEM = re.compile(rf"{_ROOT}/({_ITEMS})/({_UIDS})-\d{{8}}\.ya?ml$")
BASELINE = re.compile(rf"{_ROOT}/baselines/|{_BASELINE_FILE}")
# @req> REQ-22704490@u7IClIQOfStA yn3jbh
CORPUS_DIR = re.compile(
    rf"{_ROOT}/({_CORPUS})(?![\w.-])"
    rf"|{_BASELINE_FILE}"
    rf"|{_ROOT}" r"/[^/\s]*[*?{\[$`]"
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
FILE_URL = re.compile(r"file:[/\\]+\S*", re.I)
READS_NO_URL = ("Read", "Grep", "Glob", "Write", "Edit", "MultiEdit", "NotebookEdit")
COMMAND_KEY = re.compile(r"(^|_|[a-z])(command|cmd|script|shell)$", re.I)
GLOB_KEY = re.compile(r"(^|_|[a-z])pattern$", re.I)
GREP_GLOB_KEY = re.compile(r"^glob$")
BRACE = re.compile(r"\{([^{},]*,[^{}]*)\}")
SEQUENCE = re.compile(r"\{(?=[^{}]*\})[^{}]*\.\.")
SETTER = re.compile(r"^(export|declare|typeset|local|read(only|array)?|mapfile|getopts"
                    r"|let)$|\$\{\w+(\[[^]]*\])?:?=")
UNQUOTED_WORD = re.compile(r"[\w@%+=:,./{}-]+")
PARAMETER = re.compile(r"\$\{[^{}]*\}")
EXPANSION = re.compile(r"\$(?:\{[^{}]*\}|\((?:[^()]|\([^()]*\))*\)|\w+|[@*#?$!-])|`[^`]*`")
ANSI_C = re.compile(r"\\.|(\$*)('_*')")
ANSI_ESCAPE = re.compile(
    r"\\(?:([0-7]{1,3})|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8}))|\\.")
STDIN_ARGUMENTS = re.compile(r"\bxargs\b|--pathspec-f")
WRAPPERS = ("env", "command", "nohup", "sudo", "doas", "timeout", "nice", "time",
            "exec", "xargs", "stdbuf", "builtin", "setsid", "ionice")
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
YAML_TYPES = ("yaml", "crystal", "dockercompose", "all")
CWD_LIMIT = 64
DEADLINE = time.monotonic() + 30
JUDGED = ("git", "rm", "patch", "find", "eval", *SHELLS)
LONG_FLAGS = ("--force", "--hard", "--discard-changes", "--dry-run", "--staged",
              "--worktree")
NO_COMMIT = {"merge": ("--ff-only", "--no-commit", "--squash", "--abort", "--quit"),
             "cherry-pick": ("-n", "--no-commit", "--abort", "--quit", "--skip"),
             "revert": ("-n", "--no-commit", "--abort", "--quit", "--skip"),
             "pull": ("--ff-only", "--dry-run"),
             "rebase": ("--abort", "--quit", "--edit-todo", "--show-current-patch")}
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
# @req+ REQ-38099593@WZbBLy6bHv3j 2x3zhi
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
ASSIGNED_NAME = re.compile(
    r"\s*(?:\w+(?:\[[^\]]*\])?\+?=[^\s<>&|;()]*\s+)*(?:(?:declare|local|typeset|export|readonly)\s+(?:-\S+\s+)*)?\w+")
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
QUOTED_TO = {"'": re.compile("[^']*'"), "$'": re.compile(r"(?:\\.|[^\\'])*'", re.S),
             '"': re.compile(r'(?:\\.|[^"\\])*"', re.S)}
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

SEARCHES_CORPUS = (
    "Grep over {base} blocked: it searches the requirements corpus at {root}.\n"
    "Give Grep a path that does not hold the corpus, or a glob or type that matches no "
    "corpus file, such as the glob !requirements.\n"
    "Read the corpus through reqctl: `reqctl context UID`, `reqctl export`."
)

ON_DEFAULT = (
    "Commit on the default branch {branch} blocked.\n"
    "  git checkout -b claude/<name>\n"
    "{branch} is what the owner merges into, never what an agent commits to."
)

LEVEL_WITH_DEFAULT = "\n  git merge --ff-only origin/{branch} brings it level without a commit."

NO_DEFAULT = (
    "Commit blocked: origin names no default branch, so the guard cannot tell "
    "whether this commit lands on it.\n"
    "  git remote set-head origin --auto"
)

MOVES_DEFAULT = (
    "{what} blocked: it points the default branch {branch} at a commit "
    "origin/{branch} does not reach, or at one that does not descend from where "
    "{branch} stands.\n"
    "  git merge --ff-only origin/{branch} brings it level with origin\n"
    "Work that is not on origin belongs on its own branch: git checkout -b claude/<name>"
)

UNNAMED_DEFAULT = (
    "{what} blocked: origin names no default branch, so the guard cannot tell "
    "whether this moves it.\n"
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
    "old_string is not in {target} exactly as written, and the file or new_string holds "
    "a statement citation.\n"
    "Give old_string exactly as the file holds it, quotes and escapes included."
)
# @req- etn3fq
# @req- jzjikg

WHOLE_TREE: list[str] = []
FORCE = ("-f", "--force", "--discard-changes")
# @req> worktree_commands@EtNKXLNk8TvY 3qwrc6
RESTORES = ("checkout", "restore", "reset", "clean", "switch")
JUDGED_GIT = ("push", "commit", "apply", "am", "remote", "symbolic-ref", "update-ref", "fetch",
              "branch", *NO_COMMIT, *RESTORES)
UNTRACKED = ("??", "!!")
UNTRACKED_ONLY = ("??",)

# @req+ REQ-30013664@ijHTWP75cTcK rmhljp
WRITES_DEFAULT = (
    "{what} blocked: it writes to {branch}, the default branch of origin.\n"
    "  git push -u origin claude/<name>, then open a pull request into {branch}\n"
    "Only merging a pull request writes to {branch}."
)

UNRESOLVED_WRITE = (
    "{what} blocked: the guard cannot tell which branch of origin it writes to, or "
    "origin names no default branch.\n"
    "Name the branch outright, or run `git remote set-head origin --auto`."
)
# @req- rmhljp

# @req> origin_query_seconds@QD8PvG3tkf2s lm2l7z
ORIGIN_QUERY_SECONDS = 10

# @req> REQ-14590906@7HafgqX9CF9- 7r3vt3
ORIGIN_SILENT = (
    "{what} blocked: origin did not report its default branch: `git ls-remote --symref "
    f"origin HEAD` failed, named no default branch, or took over {ORIGIN_QUERY_SECONDS} "
    "seconds.\n"
    "Run it to see why, fix origin or the connection, then retry."
)

# @req+ REQ-75564975@kR-BIGM3krAM sjmzez
MOVES_ORIGIN_HEAD = (
    "{what} blocked: it changes or deletes the local origin/HEAD other than by "
    "setting it to origin's default branch.\n"
    "  git remote set-head origin --auto"
)
ORIGIN_HEAD_FILE = re.compile(r"(?<![\w.-])(?:refs/+remotes/+origin/+HEAD|packed-refs)(?![\w.-])")
# @req- sjmzez

# @req> REQ-75038049@hXyFNmxx-SWy g3ql3s
UNHELD_SCRIPT = (
    "Running {file} blocked: it names the requirements corpus ({found}), and the "
    "default branch of origin does not hold it unchanged at its path.\n" + USE_REQCTL
)

# @req+ REQ-75038049@hXyFNmxx-SWy kbbyh4
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FINGERPRINTS = frozenset({
    "d8fb0266921273ad6050061714a47068dc2063de2e516006ccd7ce2d00f43d31",
    "5dfadb71a60606f5136f02bef2f45f117ec08c3249ddafd80562186f9e9a4a24",
    "62dbe3f42dd898d819f40a8c7267fda3e80355e38a2e9d9892d5681abfff4555",
})
# @req- kbbyh4
PLUGIN_SPELLINGS = {str(PLUGIN_ROOT), os.path.abspath(Path(__file__).parent.parent)}
# @req> REQ-59919160@eEBU6tuB77Dq xae2nk
PLUGIN_WRITE = (
    "Changing the reqctl plugin's own folder blocked: {target}\n"
    "The plugin changes through a reqctl release: edit its sources in the reqctl "
    "repository, then `claude plugin update reqctl@reqctl`."
)
# @req> REQ-75038049@hXyFNmxx-SWy 6vfbgw
ENV_CHANGE = re.compile(r"(?:^|[\s;&|(\n`{}/$])(?:[A-Za-z_]\w*(?:\[[^]]*\])?\+?=|(?:env|unset|set|"
                        r"export|declare|typeset|readonly|local|read|readarray|mapfile|getopts|let|"
                        r"eval|exec|source|for|select|hash|coproc|wait|alias|\.)(?=[\s<]|$)"
                        r"|printf(?:\s+-\S+)*?\s+-v|[A-Za-z_][\w.-]*\s*\(\s*\))|\$\{\w+(?:\[[^]]*\])?:?=")
CALL = {"changes_environment": True}
# @req> REQ-59919160@eEBU6tuB77Dq v6s3eb
WRITERS = ("rm", "mv", "cp", "ln", "chmod", "chown", "touch", "mkdir", "rmdir", "tee", "install",
           "rsync", "truncate", "dd", "unlink", "sed", "perl", "tar", "unzip", "patch", "cpio",
           "gzip", "gunzip", "bzip2", "xz", "zstd", "ed", "split", "shred", "sort", "curl", "wget")
READ_WRITES = re.compile(r"^\s*(?:tree|less|file)\s(?:.*\s)?(?:-[A-Za-z]*[oOC]|--(?:log|LOG)-[fF]|--compile)"
                         r"|\s--(?:pre|pager|hostname-bin)\b")

PUSH_VALUED = ("-o", "--push-option", "--receive-pack", "--exec", "--repo")
GH_VALUED = ("-X", "--method", "-f", "--raw-field", "-F", "--field", "--input", "-H",
             "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache",
             "-p", "--preview")
HTTP_BODY = ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--json",
             "--post-data", "--body-data")
HTTP_SENDS = (*HTTP_BODY, "--data-urlencode", "-F", "--form", "-T", "--upload-file",
              "--post-file", "--body-file")
HTTP_VALUED = ("-X", "--request", "--method", *HTTP_SENDS, "-H", "--header", "-o",
               "--output", "-u", "--user", "--url", "-K", "--config")
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
HTTPIE = ("http", "https", "xh", "xhs")
GITHUB_API = re.compile(
    r"(?<![\w.-])(?:https?:/+)?(?:[^/\s@'\"]*@)?api\.github\.com\.?(?::\d+)?(/\S*)?$",
    re.I)
BRANCH_MUTATION = re.compile(r"\b(?:createCommitOnBranch|updateRefs?|deleteRef|mergeBranch)\b")
CONNECTOR_WRITE = re.compile(
    r"github.*__\w*(?:create|update|upsert|push|delete|commit)\w*_(?:files?|commits?|refs?)$",
    re.I)
RUNNERS = {"python": "c", "node": "ep", "perl": "eE", "ruby": "e", "source": "", ".": "",
           **dict.fromkeys((*SHELLS, "fish"), "cs")}
RUN_VALUED = {"python": ("-W", "-X", "-m", "--check-hash-based-pycs"),
              "node": ("-r", "--require", "--import", "--loader"),
              **dict.fromkeys((*SHELLS, "fish"), ("-o", "-O", "--rcfile", "--init-file"))}
SEARCH_VALUED = {
    "grep": ("-A", "-B", "-C", "-D", "-d", "-e", "-f", "-m", "--exclude", "--exclude-dir",
             "--include", "--label", "--max-count", "--context", "--after-context",
             "--before-context", "--regexp", "--file", "--devices", "--directories",
             "--binary-files"),
    "rg": ("-A", "-B", "-C", "-E", "-M", "-T", "-d", "-e", "-f", "-g", "-j", "-m", "-r", "-t",
           "--glob", "--iglob", "--type", "--type-not", "--type-add", "--type-clear",
           "--max-depth", "--max-count", "--max-columns", "--max-filesize", "--context",
           "--after-context", "--before-context", "--regexp", "--file", "--replace", "--sort",
           "--sortr", "--threads", "--encoding", "--engine", "--path-separator",
           "--context-separator", "--field-match-separator", "--field-context-separator",
           "--pre", "--pre-glob", "--ignore-file", "--dfa-size-limit", "--regex-size-limit",
           "--hostname-bin", "--hyperlink-format", "--colors", "--color")}
EXCLUDED_BY = ("--exclude", "--exclude-dir")
GLOBBED_BY = ("-g", "--glob", "--iglob")
SETTERS = ("export", "declare", "typeset", "local", "readonly")
ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")
REBASE_VALUED = ("--onto", "-s", "--strategy", "-X", "--strategy-option", "-x", "--exec",
                 "--whitespace", "-C", "--empty", "--trailer")
ROOT_QUOTED = re.compile(rf"""(['"`])(?:\./)?{CORPUS_ROOT_NAME}/?\1""")
LAUNCHERS = ("uv", "pipx", "poetry", "pdm", "hatch", "rye", "pipenv")
GH_CONFIG_HOMES = ("GH_CONFIG_DIR", "XDG_CONFIG_HOME", "HOME")
CURL_HOMES = ("CURL_HOME", "XDG_CONFIG_HOME", "HOME")
CURL_CONFIG_LINE = re.compile(r"(-{0,2}[A-Za-z0-9][\w-]*)(?:\s*[=:]\s*|\s+|$)(.*)")


def named_paths(value, keys=PATH_KEY, key=""):
    if isinstance(value, str):
        # @req> REQ-38099593@WZbBLy6bHv3j okrfi5
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


def decoded(text):
    for _ in range(3):
        text = unquote(text)
    return text


def url_paths(found):
    spelled = decoded(found.replace("\\", "/"))
    paths = ["/" + spelled[5:].lstrip("/")]
    try:
        paths.append(urlsplit(spelled).path)
    except ValueError:
        pass
    return paths


def file_urls(value):
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [path for v in value for path in file_urls(v)]
    if not isinstance(value, str):
        return []
    return [path for text in (value, re.sub(r"[\t\r\n]", "", value))
            for found in FILE_URL.findall(text) for path in url_paths(found)]


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
    # @req+ REQ-51060455@Z5EVUURxm1nV kfua34
    try:
        while decision:
            decision = decision[os.write(1, decision):]
    except OSError:
        # @req+ REQ-15535068@j58MkfsvW9OK 76xt5k
        refusal = reason.encode(errors="replace")
        try:
            while refusal:
                refusal = refusal[os.write(2, refusal):]
        except OSError:
            pass
        # @req- 76xt5k
        # @req> REQ-29713167@M7nLInYBwBo2 gamoti
        sys.exit(2)
    sys.exit(0)
    # @req- kfua34


def scan(cmd: str, joins=None) -> list[list[str]]:
    commands, pipeline, buf, held, bodies, nest, pending = [], [], [], [], [], [], []
    subscripts, loose = [], []
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

    def shifting():
        enclosing = next((at for at in range(len(nest) - 1, -1, -1) if nest[at] != "("), -1)
        return bool(subscripts and subscripts[-1][0] > enclosing) or (
            enclosing >= 0 and nest[enclosing] in ("((", "$[", "${", '"{'))

    def left_open():
        if any(saw for at, saw in subscripts if at >= len(nest)):
            deny(UNREADABLE.format(what="a << in a subscript left open"))
        subscripts[:] = [entry for entry in subscripts if len(nest) > entry[0]]
        loose[:] = [at for at in loose if len(nest) > at]

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
            if char == "{" and buf[-1:] == ["$"]:
                nest.append("${")
                buf.append(char)
                i += 1
                continue
            if char == "<" and line.startswith("<<", i) and subscripts and subscripts[-1][0] > max(
                    (at for at in range(len(nest)) if nest[at] != "("), default=-1):
                subscripts[-1][1] = True
            if char == "<" and not shifting() and loose and loose[-1] == len(nest) and (
                    heredoc_at(line, i)):
                deny(UNREADABLE.format(what="a << after a [ the guard cannot place"))
            if char == "<" and not shifting() and (heredoc := heredoc_at(line, i)):
                delimiter, _, dash, end = heredoc
                bodies.append(slot := [])
                pending.append((delimiter, dash, slot, sum(entry != "(" for entry in nest)))
                buf.append(line[i:end])
                i = end
                continue
            if char == ")" and nest[-1:] not in ([], ["$["]):
                closed = i if nest[-1] == "(" else closed
                quote = '"' if nest.pop() == '"(' else None
            elif char == "]" and subscripts and subscripts[-1][0] == len(nest):
                subscripts.pop()
            elif char == "]" and loose and loose[-1] == len(nest):
                loose.pop()
            elif char == "]" and nest[-1:] == ["$["]:
                nest.pop()
            elif char == "(":
                nest.append("$(" if buf[-1:] in (["$"], ["<"], [">"])
                            else "((" if buf[-1:] in (["("], ["$("]) else "(")
            elif char == "[" and buf[-1:] == ["$"]:
                nest.append("$[")
            elif char == "[" and ASSIGNED_NAME.fullmatch("".join(buf)):
                subscripts.append([len(nest), False])
            elif char == "[" and buf[-1:] and (buf[-1].isalnum() or buf[-1] in ("_", "]")):
                loose.append(len(nest))
            elif char == ")" and not nest:
                cut_command("&&")
            if nest:
                buf.append(char)
                i += 1
                continue
            # @req> REQ-54260750@MTrWbA9_HZWY 5wgwq2
            if char == "|" and buf[-1:] == [">"]:
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
        left_open()
        if nest:
            held.append("".join(buf) + ";")
            buf.clear()
        else:
            cut_command()
        row += 1
    left_open()
    if any(saw for _, saw in subscripts):
        deny(UNREADABLE.format(what="a << in a subscript left open"))
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
            word.append(text[i + 1])
            quoted, i = True, i + 2
            continue
        if char not in "'\"":
            if char == "`" or text.startswith(("$(", "${"), i):
                break
            take = 1 + text.startswith("$$", i)
            word.append(text[i:i + take])
            i += take
            continue
        shut = QUOTED_TO[opened_quote(char, "$" * dollar)].match(text, i + dollar + 1)
        held = shut and shut[0][:-1]
        if not shut or char == "'" and dollar and "\\" in held or char == '"' and any(
                mark in held for mark in ("$(", "${", "`")):
            break
        word.append(re.sub(r'\\([$`"\\])', r"\1", held.replace("\\\n", ""))
                    if char == '"' else held)
        quoted, i = True, shut.end()
    else:
        return ("".join(word), quoted, found[1] == "-", i) if word else None
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
            found = QUOTED_TO[opened_quote(char, text[at:i])].match(text, i + 1)
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
        elif char == "<" and (heredoc := heredoc_at(text, i)):
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


@functools.cache
def nested(part):
    at = COMPOUND.match(masked(part)).end()
    return [part[at:], *groups(part[:at])] if at else groups(part)


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
            i, dollars = end, 0
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


@functools.cache
def argv(said):
    words, bare = tokens_of(said), tokens_of(masked(said))
    if len(words) != len(bare):
        return words, bare
    kept, pairs = [], zip(words, bare)
    for word, mask in pairs:
        if not REDIRECTION.match(mask) or SUBSHELL.match(mask):
            kept.append((word, mask))
        elif REDIRECTION.fullmatch(mask):
            next(pairs, None)
    return [word for word, _ in kept], [mask for _, mask in kept]


def invoked(words):
    i = 0
    while i < len(words) and (os.path.basename(words[i]) in WRAPPERS or "=" in words[i]
                              or REDIRECTION.match(words[i]) or (i and (
            words[i].startswith("-") or words[i][:1].isdigit()
            or words[i - 1].startswith("-") and os.path.basename(words[i]) not in JUDGED))):
        i += 2 if REDIRECTION.fullmatch(words[i]) else 1
    if i < len(words) and os.path.basename(words[i]) not in (*JUDGED, *WRITES_NOTHING):
        i = next((j for j in range(i, len(words))
                  if os.path.basename(words[j]) in ("rm", "find") or posing(words[j:])
                  or os.path.basename(words[j]) == "git" and j + 1 < len(words)
                  and (words[j + 1].startswith("-") or words[j + 1] in JUDGED_GIT
                       or EXPANSION.search(words[j + 1]))), i)
    if posing(words[i:]):
        return ["git", *words[i + 1:]]
    return [os.path.basename(words[i]), *words[i + 1:]] if i < len(words) else []


def posing(words):
    return len(words) > 1 and EXPANSION.search(words[0]) is not None and words[1] in JUDGED_GIT


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


# @req> REQ-38099593@WZbBLy6bHv3j bc4mmq
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


# @req> REQ-38099593@WZbBLy6bHv3j dek4pk
def unreadable(part):
    quote = None
    for char in part:
        if char in "'\"" and quote in (None, char):
            quote = None if quote else char
        elif (char in "\\$`" and quote != "'") or (char in "{<()" and not quote):
            return f"'{char}'"
    return "a line break" if "\n" in part else None


# @req> REQ-38099593@WZbBLy6bHv3j j6ubo7
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


# @req> REQ-38099593@WZbBLy6bHv3j 4h5lnn
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


MESSAGE_HEAD = re.compile(
    r"(?:\A|(?<=[;(\n])|(?<=(?<![<>])[&|]))[ \t]*(?:git(?:[ \t]+-C[ \t]+[^\s;&|()<>]+)?[ \t]+(?P<git>commit)"
    r"|gh[ \t]+(?:(?:pr|issue)[ \t]+(?:create|edit|comment)|pr[ \t]+review))(?=[ \t\n;&|)]|\Z)")
MESSAGE_FLAGS = {"commit": (("-m", "--message"), ("-F", "--file")),
                 None: (("-t", "--title", "-b", "--body"), ("-F", "--body-file"))}
SHELL_WORD = re.compile(r"[^\s;&|()<>`]+")
BLANKS = re.compile(r"[ \t]*")
LITERAL_TEXT = re.compile(r"'[^']*'|\"[^\"$`\\]*\"")


def message_words(cmd, m, at):
    words, doc = [], None
    while True:
        at = BLANKS.match(m, at).end()
        if opened := heredoc_at(cmd, at):
            doc, at = opened, opened[3]
            continue
        if not (word := SHELL_WORD.match(m, at)):
            return words, doc
        words.append(word.span())
        at = word.end()


def heredoc_body(cmd, m, doc):
    word, quoted, dash, end = doc
    begins = m.find("\n", end) + 1
    closing = begins and m[begins - 2] != "\\" and re.compile("^" + "\t*" * dash + re.escape(word) + "$", re.M).search(cmd, begins)
    if closing and (quoted or not any(c in cmd[begins:closing.start()] for c in "$`\\")):
        return begins, closing.start()
    return None


# @req> REQ-38099593@WZbBLy6bHv3j xdls2r
# @req> REQ-22704490@u7IClIQOfStA ypnv3w
def messageless(cmd):
    m = masked(cmd)
    docs = HEREDOC.findall(m)
    if len(docs) > 1:
        return cmd
    cuts, body = [], None
    for head in MESSAGE_HEAD.finditer(m):
        if body and body[0] <= head.start() < body[1]:
            continue
        texts, stdin = MESSAGE_FLAGS[head["git"]]
        words, doc = message_words(cmd, m, head.end())
        said = [cmd[start:end] for start, end in words]
        fed = False
        for at, word in enumerate(said):
            value = None
            if word in texts and at + 1 < len(words):
                value = words[at + 1]
            elif flag := next((f for f in texts if f.startswith("--") and word.startswith(f + "=")), None):
                value = (words[at][0] + len(flag) + 1, words[at][1])
            if value and LITERAL_TEXT.fullmatch(cmd[value[0]:value[1]]):
                cuts.append((*value, "''"))
            fed = fed or (word in stdin and said[at + 1:at + 2] == ["-"]) or word in {
                f"{f}=-" for f in stdin if f.startswith("--")}
        if doc and fed:
            if not (body := heredoc_body(cmd, m, doc)):
                return cmd
            cuts.append((*body, ""))
    if docs and not body:
        return cmd
    judged = cmd
    for start, end, put in sorted(cuts, reverse=True):
        judged = judged[:start] + put + judged[end:]
    before, after = (scan(AMP_REDIRECT.sub(" ", flatten(ESCAPE.sub("", text)))) for text in (cmd, judged))
    if list(map(len, before)) != list(map(len, after)) or any(
            old != new and not MESSAGE_HEAD.match(masked(old.lstrip()))
            for olds, news in zip(before, after) for old, new in zip(olds, news)):
        return cmd
    return judged


@functools.cache
def refuse_destructive_push(said):
    # @req+ REQ-60587913@64oissmU4Xo2 4aiv2n
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


def git_reads(args, place, seconds=15):
    here, options, settings = place
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", here, *options, "-c", "core.fsmonitor=false",
             *args],
            capture_output=True, text=True, timeout=min(seconds, left()),
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


def discarded(subcommand, rest, place, unread):
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
    forced = unread or any(flag in FORCE for flag in flags) or short_flagged(flags, "f")
    if unread and subcommand != "clean":
        return WHOLE_TREE, False, False
    if subcommand == "reset":
        return (WHOLE_TREE, False, False) if "--hard" in flags else (None, False, False)
    if subcommand == "clean":
        if not forced or any(not f.startswith("--") and "n" in f[1:].split("e", 1)[0]
                                for f in flags) or "--dry-run" in flags:
            return None, False, False
        ignored = unread or short_flagged(flags, "x") or short_flagged(flags, "X")
        return (operands if after and not unread else WHOLE_TREE), True, ignored
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
    unread = any(map(STDIN_ARGUMENTS.search, words)) or any(
        "$" in word or "`" in word for word in rest)
    readings = [reading for said in dict.fromkeys(map(tuple, sayings))
                if (reading := discarded(subcommand, said, place, unread))[0] is not None]
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
    named = []
    if subcommand == "rebase":
        operands = options(rest, REBASE_VALUED)[1]
        named = operands[:1] if "--root" in rest else operands[1:2]
        if any("$" in word or "`" in word for word in named):
            deny(UNREADABLE.format(what=f"which branch git rebase {named[0]} rewrites"))
    branch = named[0] if named else git_sees(["branch", "--show-current"], place).strip()
    default = git_reads(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], place)
    if default is None:
        deny(NO_DEFAULT)
    if default.strip() == f"origin/{branch}":
        deny(ON_DEFAULT.format(branch=branch) + (
            LEVEL_WITH_DEFAULT.format(branch=branch) if subcommand in ("pull", "rebase", "merge")
            else ""))
    # @req- zm6qoo


def flagged(flags, *spelled):
    named = [name for name, _ in flags]
    return any(name in spelled or len(name) > 2 and name.startswith("--") and any(
        full.startswith(name) for full in spelled) for name in named) or any(
        short_flagged(named, full[1]) for full in spelled if len(full) == 2)


def head_branch(place):
    return git_sees(["branch", "--show-current"], place).strip()


def named_object(target, place):
    return target and "$" not in target and "`" not in target and (git_reads(
        ["rev-parse", "--verify", "-q", target], place) or "").strip()


def commit_of(target, place):
    named = named_object(target, place)
    return named and (git_reads(
        ["rev-parse", "--verify", "-q", f"{named}^{{commit}}"], place) or "").strip()


def fetched(remotes, specs, flags, place):
    moves = []
    for remote in remotes:
        for spec in specs or (git_reads(["config", "--get-all", f"remote.{remote}.fetch"],
                                        place) or "").split():
            src, _, dst = spec.partition(":")
            name = dst.removeprefix("refs/").removeprefix("heads/")
            if name and (remote != "origin" or src.startswith("+")
                         or flagged(flags, "-f", "--force")
                         or src.removeprefix("refs/heads/") != name):
                moves.append((name, None))
    return moves


def pushes_here(remote, place):
    if remote in (None, "origin"):
        return False
    if remote == "." or "$" in remote or "`" in remote:
        return True
    url = (git_reads(["remote", "get-url", "--push", remote], place) or remote).strip()
    filed = url.lower().startswith("file:")
    if not filed and ("://" in url or ":" in url.split("/", 1)[0]):
        return False
    path = unquote(urlsplit(url).path) if filed else os.path.expanduser(url)
    common = ["rev-parse", "--path-format=absolute", "--git-common-dir"]
    there = git_reads(["-C", path, *common], place)
    return there is not None and there == git_reads(common, place)


def landings(subcommand, rest, place):
    # @req+ REQ-76235768@1l5tlNlByWT6 amejii
    if subcommand == "update-ref":
        flags, operands = options(rest, ("-m",))
        ref = operands[0] if operands else ""
        if ref == "HEAD" and not flagged(flags, "--no-deref"):
            ref = "refs/heads/" + head_branch(place)
        if flagged(flags, "-d", "--delete") or not ref.startswith("refs/heads/") or (
                operands[1:] and len(operands[1]) in (40, 64) and set(operands[1]) == {"0"}):
            return []
        return [(ref.removeprefix("refs/heads/"), operands[1] if operands[1:] else None)]
    if subcommand == "symbolic-ref":
        flags, operands = options(rest, ("-m",))
        return [(operands[0].removeprefix("refs/heads/"), None)] if len(operands) == 2 and (
            operands[0].startswith("refs/heads/")) else []
    if subcommand == "branch":
        flags, operands = options(rest, ("-u", "--set-upstream-to"))
        if not operands or flagged(flags, *BRANCH_KEEPS):
            return []
        if flagged(flags, "-m", "-M", "--move", "-c", "-C", "--copy"):
            return [(operands[-1], operands[0] if operands[1:] else "HEAD")]
        return [(operands[0], operands[1] if operands[1:] else "HEAD")]
    if subcommand in ("checkout", "switch", "worktree"):
        if subcommand == "worktree":
            if rest[:1] != ["add"]:
                return []
            rest = rest[1:]
        flags, operands = options(rest, ("-b", "-B", "-c", "-C", "--create", "--force-create",
                                         "--orphan", "--reason"))
        start = operands[1 if subcommand == "worktree" else 0:][:1] or ["HEAD"]
        named = [(value, start[0]) for name, value in flags
                 if name in ("-b", "-B", "--create", "--force-create")
                 or subcommand == "switch" and name in ("-c", "-C")]
        if named or not operands:
            return named
        if subcommand != "worktree":
            return [(operands[0].removeprefix("refs/remotes/").partition("/")[2],
                     operands[0])] if flagged(flags, "-t", "--track") else []
        basename = os.path.basename(operands[0].rstrip("/"))
        return [(basename, "HEAD")] if len(operands) == 1 and not flagged(
            flags, "-d", "--detach", "--orphan") and git_reads(
            ["show-ref", "--verify", "-q", f"refs/heads/{basename}"], place) is None else []
    if subcommand == "fast-import":
        return [("*", None)]
    if subcommand == "filter-branch":
        flags, operands = options(rest, FILTER_VALUES)
        if any(name not in (*FILTER_VALUES, "-f", "--force", "--prune-empty", "--tags", "--")
               for name, _ in flags):
            return [("*", None)]
        revisions = [part or "HEAD" for operand in operands
                     for part in (operand.split("...") if "..." in operand
                                  else operand.split("..")[-1:])
                     if not part.startswith("^")]
        return [((git_reads(["rev-parse", "--symbolic-full-name", name], place) or name)
                 .strip().removeprefix("refs/heads/"), None)
                for name in revisions or ([] if flagged(flags, "--tags") else ["HEAD"])] + [
            move for name, value in flags if name == "--state-branch"
            for move in landings("update-ref", [value], place)]
    if subcommand == "remote":
        flags, operands = options(rest, ())
        if operands[:1] != ["update"]:
            return []
        known = (git_reads(["remote"], place) or "").split()
        remotes = [remote for name in operands[1:] or known
                   for remote in ((git_reads(["config", "--get-all", f"remotes.{name}"], place)
                                   or "").split() or ([name] if name in known else known
                                                      if name == "default" else []))]
        return fetched(remotes, [], flags, place)
    if subcommand in ("fetch", "push"):
        flags, operands = options(rest, ("--depth", "--deepen", "--shallow-since",
                                         "--shallow-exclude", "--refmap", "-o",
                                         "--push-option", "--recurse-submodules", "--repo"))
        if subcommand == "fetch":
            every = not operands or flagged(flags, "--all", "--multiple")
            remotes = (git_reads(["remote"], place) or "").split() if every else operands[:1]
            refmaps = [value for name, value in flags if name == "--refmap"]
            return fetched(remotes, [*operands[1:], *refmaps] if operands[1:] and not every
                           else [], flags, place)
        remote = operands[0] if operands else next(
            (value for name, value in flags if name == "--repo"), None)
        if not pushes_here(remote, place):
            return []
        return [(dst.removeprefix("refs/").removeprefix("heads/"), src.removeprefix("+"))
                for src, _, dst in (spec.partition(":") for spec in operands[1:])
                if dst and src.removeprefix("+")]
    current = head_branch(place)
    flags, operands = options(rest, ("-m", "-s", "--strategy", "-X", "--strategy-option",
                                     "-F", "--file", "--into-name", "--cleanup", "--depth",
                                     "--deepen", "--shallow-since", "--shallow-exclude"))
    if subcommand == "reset":
        after = rest[rest.index("--") + 1:] if "--" in rest else []
        if after or len(operands) != 1 or flagged(flags, "-p", "--patch"):
            return []
        if "$" in operands[0] or "`" in operands[0]:
            return [(current, None)]
        return [(current, operands[0])] if named_object(operands[0], place) else []
    refspecs = fetched((git_reads(["remote"], place) or "").split() if not operands
                       else operands[:1], operands[1:], flags, place
                       ) if subcommand == "pull" else []
    fast = next((name for name, _ in reversed(flags)
                 if name in ("--ff", "--no-ff", "--ff-only")), None)
    if fast == "--no-ff" or flagged(flags, "--abort", "--quit", "--continue", "--dry-run",
                                    "--squash"):
        return refspecs
    if subcommand == "merge":
        return [(current, operands[0] if len(operands) == 1
                 else "@{upstream}" if not operands else None)]
    origin = git_reads(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], place)
    pulled = f"origin/{operands[1]}" if operands[1:] else (
        git_reads(["rev-parse", "--abbrev-ref", "@{upstream}"], place) or "").strip()
    return refspecs + ([] if operands[:1] in ([], ["origin"]) and len(operands) <= 2 and origin
                       and pulled == origin.strip() else [(current, None)])
    # @req- amejii


BRANCH_KEEPS = ("-d", "-D", "--delete", "-l", "--list", "-u", "--set-upstream-to",
                "--unset-upstream", "--edit-description", "--contains", "--no-contains",
                "--merged", "--no-merged", "--points-at", "--show-current")

MOVERS = ("update-ref", "symbolic-ref", "branch", "checkout", "switch", "worktree", "fetch",
          "push", "reset", "merge", "pull", "fast-import", "filter-branch", "remote")
FILTER_SCRIPTS = ("--setup", "--env-filter", "--tree-filter", "--index-filter",
                  "--parent-filter", "--msg-filter", "--commit-filter", "--tag-name-filter")
FILTER_VALUES = (*FILTER_SCRIPTS, "--subdirectory-filter", "--original", "-d", "--state-branch")


def refuse_moving_default(words, here):
    # @req+ REQ-76235768@1l5tlNlByWT6 nahqvl
    subcommand, rest = git_subcommand(words)
    if subcommand not in MOVERS:
        return
    place = located(words, here)
    moves = landings(subcommand, rest, place)
    if not moves:
        return
    what = shlex.join(["git", subcommand, *rest])
    default = git_reads(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], place)
    if default is None:
        deny(UNNAMED_DEFAULT.format(what=what))
    branch = default.strip().removeprefix("origin/")
    stands = git_reads(["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], place)
    for name, target in moves:
        if "$" not in name and "`" not in name and not fnmatch.fnmatchcase(branch, name):
            continue
        commit = commit_of(target, place)
        if not commit or git_reads(["merge-base", "--is-ancestor", commit,
                                    "refs/remotes/origin/HEAD"], place) is None or (
                stands and git_reads(["merge-base", "--is-ancestor", stands.strip(),
                                      commit], place) is None):
            deny(MOVES_DEFAULT.format(what=what, branch=branch))
    # @req- nahqvl


def local_relative(url):
    return bool(url) and "://" not in url and ":" not in url.split("/", 1)[0] and not (
        os.path.isabs(url) or url.startswith("~"))


# @req> REQ-14590906@7HafgqX9CF9- efqhzh
def origin_default(what, place, persisted=False):
    if persisted:
        here, options, settings = place
        place = (here, [word for at, word in enumerate(options)
                        if word != "-c" and (not at or options[at - 1] != "-c")],
                 {name: value for name, value in settings.items() if name in READ_ENV})
    urls = [url for args in (["--push", "--all"], ["--all"])[:1 + persisted]
            for url in (git_reads(["remote", "get-url", *args, "origin"], place) or "").splitlines()]
    if any(local_relative(url) for url in urls):
        top = git_reads(["rev-parse", "--show-toplevel"], place)
        urls = [os.path.join(top.strip() if top else place[0], url) if local_relative(url) else url
                for url in urls]
    branches = []
    for url in urls or [""]:
        said = url and git_reads(["-c", "protocol.ext.allow=never", "ls-remote", "--symref", "--",
                                  url, "HEAD"], ("/", [], {"GIT_TERMINAL_PROMPT": "0"}),
                                 ORIGIN_QUERY_SECONDS)
        found = re.search(r"^ref: refs/heads/(\S+)\tHEAD$", said or "", re.MULTILINE)
        if not found:
            deny(ORIGIN_SILENT.format(what=what))
        branches.append(found.group(1))
    return branches


# @req> REQ-75564975@kR-BIGM3krAM owo62a
def refuse_moving_origin_head(words, here):
    subcommand, rest = git_subcommand(words)
    what = " ".join(words)
    if subcommand and any(":" in word and word.rpartition(":")[2].endswith("remotes/origin/HEAD")
                          for word in words):
        deny(MOVES_ORIGIN_HEAD.format(what=what))
    if subcommand not in ("remote", "symbolic-ref", "update-ref", "branch"):
        return
    flags, operands = options(rest, ("-m",))
    named = [name for name, _ in flags]

    def given(*spelled):
        return any(name in spelled or len(name) > 2 and any(
            full.startswith(name) for full in spelled) for name in named) or any(
            short_flagged(named, full[1]) for full in spelled if len(full) == 2)

    if subcommand == "branch":
        if given("-r", "--remotes") and given("-d", "-D", "--delete") and any(
                word.endswith("origin/HEAD") for word in operands):
            deny(MOVES_ORIGIN_HEAD.format(what=what))
        return
    if subcommand == "update-ref":
        if given("--stdin") or not operands or any(
                word.endswith("refs/remotes/origin/HEAD") for word in operands):
            deny(MOVES_ORIGIN_HEAD.format(what=what))
        return
    if subcommand == "symbolic-ref":
        if operands[:1] != ["refs/remotes/origin/HEAD"]:
            return
        if given("-d", "--delete") or len(operands) > 1 and {operands[1]} != {
                "refs/remotes/origin/" + branch
                for branch in origin_default(what, located(words, here), persisted=True)}:
            deny(MOVES_ORIGIN_HEAD.format(what=what))
        return
    verb, *args = operands or [""]
    if args[:1] != ["origin"]:
        return
    if verb in ("remove", "rm", "rename"):
        deny(MOVES_ORIGIN_HEAD.format(what=what))
    if verb != "set-head" or given("-a", "--auto"):
        return
    if given("-d", "--delete") or len(args) > 1 and {args[1]} != set(origin_default(
            what, located(words, here), persisted=True)):
        deny(MOVES_ORIGIN_HEAD.format(what=what))


# @req> REQ-75564975@kR-BIGM3krAM 2ospre
def writes_origin_head(said, plain, here):
    if ">" not in said and (plain == "git" and not OUTPUT_FLAG.search(said)
                            and "-o" not in tokens_of(said) or READ.search(said)):
        return False
    paths = [os.path.normpath(os.path.join(here, os.path.expanduser(alt.lstrip("<>&|0123456789"))))
             for word in tokens_of(said) for alt in bounded(word)]
    if ORIGIN_HEAD_FILE.search(flatten(said)) or any(map(ORIGIN_HEAD_FILE.search, paths)):
        return True
    if not any(set("*?[") & set(path) for path in paths):
        return False
    common = git_reads(["rev-parse", "--path-format=absolute", "--git-common-dir"], (here, [], {}))
    targets = [os.path.join(os.path.realpath(common.strip()), name)
               for name in ("refs/remotes/origin/HEAD", "packed-refs")] if common else []
    return any(fnmatch.fnmatchcase(target, os.path.realpath(path))
               for target in targets for path in paths)


def repo_slug(url):
    return "/".join(url.strip().removesuffix("/").removesuffix(".git").lower()
                    .replace(":", "/").split("/")[-2:])


# @req> REQ-30013664@ijHTWP75cTcK 27lhbr
def guard_default(what, place, targets, slug=None):
    if not targets:
        return
    url = git_reads(["remote", "get-url", "origin"], place)
    named = slug and "$" not in slug and "`" not in slug and repo_slug(slug)
    held = url and repo_slug(url)
    if held and named and named not in (held, held.split("/")[-1]):
        return
    if url is None or None in targets:
        deny(UNRESOLVED_WRITE.format(what=what))
    for branch in origin_default(what, place):
        if any(not target or fnmatch.fnmatchcase(branch, target) for target in targets):
            deny(WRITES_DEFAULT.format(what=what, branch=branch))


def options(words, valued):
    found, operands, at = [], [], 0
    while at < len(words):
        word = words[at]
        name, eq, value = word.partition("=") if word.startswith("--") else (word, "", "")
        name = next((full for full in valued if len(name) > 2 and full.startswith("--")
                     and full.startswith(name)), name) if word.startswith("--") else name
        if word.startswith("-") and not word.startswith("--") and len(word) > 2:
            letter = next((i for i in range(1, len(word)) if "-" + word[i] in valued), None)
            name, value = ("-" + word[letter], word[letter + 1:]) if letter else (word, "")
            eq = "=" if value else ""
        if name in valued and not eq and at + 1 < len(words):
            value, at = words[at + 1], at + 1
        (found.append((name, value)) if word.startswith("-") and word != "-"
         else operands.append(word))
        at += 1
    return found, operands


# @req+ REQ-30013664@ijHTWP75cTcK nl3elr
def destination(spec, place):
    src, colon, dst = spec.removeprefix("+").partition(":")
    name = dst if colon else src
    if "$" in name or "`" in name:
        return None
    if name in ("HEAD", "@"):
        current = git_reads(["symbolic-ref", "--short", "-q", "HEAD"], place)
        return current.strip() if current else None
    if name.startswith(("refs/", "heads/")):
        stem = name.removeprefix("refs/")
        return stem.removeprefix("heads/") if stem.startswith("heads/") else False
    if not colon and git_reads(["show-ref", "--verify", "-q", f"refs/tags/{name}"], place) == "":
        return False
    return name


def refuse_push_to_default(words, here):
    subcommand, rest = git_subcommand(words)
    if subcommand != "push":
        return
    flags, operands = options(rest, PUSH_VALUED)
    named = [name for name, _ in flags]
    if short_flagged(named, "n") or any(len(name) > 2 and "--dry-run".startswith(name)
                                        for name in named):
        return
    place = located(words, here)
    remote = operands[0] if operands else next(
        (value for name, value in flags if name == "--repo"), "origin")
    origin = git_reads(["remote", "get-url", "--push", "origin"], place)
    if origin and remote != "origin" and "$" not in remote and "`" not in remote and repo_slug(
            git_reads(["remote", "get-url", "--push", remote], place) or remote) != repo_slug(origin):
        return
    configured = git_reads(["config", "--get-all", f"remote.{remote}.push"], place)
    if operands[1:]:
        targets = [destination(alt, place) for spec in operands[1:] for alt in bounded(spec)]
    elif {"--all", "--branches"} & set(named) or (
            git_reads(["config", "push.default"], place) or "").strip() == "matching":
        targets = ["*"]
    elif configured:
        targets = [destination(spec, place) for spec in configured.split()]
    elif "--tags" in named:
        targets = []
    else:
        upstream = git_reads(["rev-parse", "--abbrev-ref", "@{upstream}"], place)
        targets = [destination("HEAD", place),
                   *([upstream.strip().partition("/")[2]] if upstream else [])]
    guard_default(shlex.join(["git", "push", *rest]), place,
                  [target for target in targets if target is not False])
# @req- nl3elr


# @req> REQ-30013664@ijHTWP75cTcK p56sug
def api_targets(url, method, body, said):
    hosted = GITHUB_API.match(url)
    parts = unquote(urlsplit((hosted.group(1) or "") if hosted else url).path).strip("/").split("/")
    if method != "GET" and any("$" in text or "`" in text for text in (
            url, method, *map(str, (body or {}).values()))):
        return None, [None]
    if parts[:1] == ["repositories"] and len(parts) > 2:
        parts = ["repos", "{owner}", "{repo}", *parts[2:]]
    if parts == ["graphql"]:
        return None, [None] if body is None or None in body.values() or BRANCH_MUTATION.search(
            said) else []
    if parts[:1] != ["repos"] or len(parts) < 4:
        return None, []
    slug, rest = "/".join(parts[1:3]), parts[3:]

    def field(name):
        value = None if body is None else body.get(name, "")
        return None if value is None else str(value)
    targets = ([field("branch")] if rest[0] == "contents" and method in ("PUT", "DELETE")
               else ["/".join(rest[3:])] if rest[:3] == ["git", "refs", "heads"]
               and method in ("PATCH", "DELETE")
               else ["/".join(rest[1:-1])] if rest[0] == "branches" and rest[-1] == "rename"
               and method == "POST"
               else [field("base")] if rest == ["merges"] and method == "POST"
               else [field("branch")] if rest == ["merge-upstream"] and method == "POST"
               else [])
    return None if slug in ("{owner}/{repo}", ":owner/:repo") else slug, targets


def runner(word):
    name = os.path.basename(word)
    return "python" if re.fullmatch(r"(?:python|pypy)[\d.]*", name) else name


@functools.cache
def gh_aliases(assigned, here):
    try:
        done = subprocess.run(["gh", "alias", "list"], capture_output=True, text=True,
                              timeout=min(15, left()), check=False, cwd=here or None,
                              env={**os.environ, **{name: os.path.expanduser(value) for name, value in
                                                    (word.split("=", 1) for word in assigned)}})
    except subprocess.TimeoutExpired:
        deny(UNREADABLE.format(what="the gh aliases before its time limit"))
    except (OSError, subprocess.SubprocessError):
        return {}
    aliases, name = {}, ""
    for line in done.stdout.splitlines():
        if line[:1] in (" ", "\t") and name:
            aliases[name] += ("\n" if aliases[name] else "") + line.strip()
            continue
        name, _, value = (part.strip() for part in line.partition(":"))
        aliases[name] = "" if value[:1] in ("|", ">") else unquoted(value)
    return aliases


def unquoted(value):
    if len(value) > 1 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) > 1 and value[0] == value[-1] == '"':
        return json.loads(value)
    return value


def curl_configured(called, here, prefix):
    flags, _ = options(called[1:], HTTP_VALUED)
    homes = {**os.environ, **dict(word.split("=", 1) for word in prefix
                                  if word.partition("=")[0] in CURL_HOMES)}
    if found := next((homes[name] for name in CURL_HOMES
                      if "$" in homes.get(name, "") or "`" in homes.get(name, "")), None):
        deny(UNREADABLE.format(what=f"which curl config {found} names"))
    default = [] if called[1:2] in (["-q"], ["--disable"]) else [next(
        (path for name, file in zip(CURL_HOMES, (".curlrc", "curlrc", ".curlrc")) if homes.get(name)
         for path in [os.path.join(here, os.path.expanduser(homes[name]), file)]
         if os.path.isfile(path)), None)]
    added = []
    for file in [*filter(None, default), *(value for name, value in flags
                                            if name in ("-K", "--config"))]:
        path = os.path.join(here, os.path.expanduser(file))
        if file == "-" or "$" in file or "`" in file or not os.path.isfile(path):
            deny(UNREADABLE.format(what=f"the curl config {file}"))
        try:
            text = Path(path).read_text()
        except (OSError, UnicodeError):
            deny(UNREADABLE.format(what=f"the curl config {file}"))
        for line in filter(None, map(str.strip, text.splitlines())):
            found = CURL_CONFIG_LINE.match(line)
            if line.startswith("#"):
                continue
            if not found:
                deny(UNREADABLE.format(what=f"the line {line} of the curl config {file}"))
            name, value = found.groups()
            name = name if name.startswith("-") else ("-" if len(name) == 1 else "--") + name
            if name in ("-K", "--config"):
                deny(UNREADABLE.format(what=f"the curl config {file}, which reads another"))
            added += [name, *shlex.split(value)[:1]]
    return [called[0], *added, *called[1:]]


def read_body(text, here=""):
    try:
        held = json.loads(Path(os.path.join(here, text)).read_text() if here else text)
    except (OSError, ValueError):
        return None
    return held if isinstance(held, dict) else None


# @req> REQ-30013664@ijHTWP75cTcK rbhjoy
def refuse_api_write(words, here, said, expanded=False):
    called = invoked(words)
    place = (here, [], {})
    if called[:1] == ["gh"] and len(called) > 1 and not expanded:
        prefix = words[:len(words) - len(called)]
        assigned = tuple(word for word in prefix if word.partition("=")[0] in GH_CONFIG_HOMES)
        if found := next((word for word in assigned if "$" in word or "`" in word), None):
            deny(UNREADABLE.format(what=f"which gh config {found} names"))
        expansion = gh_aliases(assigned, here).get(called[1])
        if called[1:3] == ["alias", "import"]:
            deny(UNREADABLE.format(what="the aliases gh alias import sets"))
        if called[1:3] == ["alias", "set"]:
            flags, operands = options(called[3:], ())
            if len(operands) < 2 or operands[1] == "-":
                deny(UNREADABLE.format(what="the alias gh alias set defines"))
            shell = any(name in ("-s", "--shell") for name, _ in flags)
            expansion = ("!" if shell and not operands[1].startswith("!") else "") + operands[1]
            called = ["gh", operands[0]]
        if expansion is not None and expansion.startswith("!"):
            args = called[2:]
            judge_shell(re.sub(r"\"?\$([@*]|\d+)\"?", lambda found: shlex.join(args)
                               if found.group(1) in "@*" else shlex.quote(
                args[int(found.group(1)) - 1] if 0 < int(found.group(1)) <= len(args) else ""),
                               expansion[1:]), here)
        elif expansion is not None:
            args, parts = called[2:], shlex.split(expansion, comments=True)
            spelled = [re.sub(r"\$(\d+)", lambda found: args[int(found.group(1)) - 1]
                              if 0 < int(found.group(1)) <= len(args) else "", word)
                       for word in parts]
            used = {int(n) for word in parts for n in re.findall(r"\$(\d+)", word)}
            words = [*prefix, "gh", *spelled, *(arg for at, arg in enumerate(args, 1)
                                                if at not in used)]
            refuse_api_write(words, here, shlex.join(words), True)
            return
    if called[:1] == ["curl"]:
        called = curl_configured(called, here, words[:len(words) - len(called)])
        if found := next((word for word in called if word in ("--next", "-:")
                          or word.startswith(("--expand-", "--variable"))
                          or word[:1] == "-" and word[1:2] != "-" and ":" in word), None):
            deny(UNREADABLE.format(what=f"which request curl sends past {found}"))
    if called[:2] == ["gh", "api"]:
        flags, operands = options(called[2:], GH_VALUED)
        body = {}
        for name, value in flags:
            key, _, held = value.partition("=")
            if name in ("-f", "--raw-field", "-F", "--field") and body is not None:
                body[key] = None if name in ("-F", "--field") and held[:1] == "@" else held
            if name == "--input":
                body = read_body(value, here) if here and value != "-" else None
        method = next((value.upper() for name, value in flags if name in ("-X", "--method")),
                      "POST" if body != {} else "GET")
        endpoint = operands[0] if operands else ""
        slug, targets = api_targets(endpoint, method, body, said)
        guard_default(f"gh api {endpoint}", place, targets, slug)
        return
    if called[:3] == ["gh", "repo", "sync"]:
        flags, operands = options(called[3:], ("-b", "--branch", "-s", "--source"))
        if operands:
            guard_default(f"gh repo sync {operands[0]}", place, [next(
                (value for name, value in flags if name in ("-b", "--branch")), "")], operands[0])
        return
    found = next(filter(None, map(GITHUB_API.search, called)), None)
    if not found:
        return
    httpie = called[0] in HTTPIE
    flags, operands = options(called[1:], () if httpie else HTTP_VALUED)
    sent = [] if httpie else [(name, value) for name, value in flags if name in HTTP_SENDS]
    pairs = [word.partition("=") for word in operands
             if "=" in word and word.find("=") != word.find("==") and not GITHUB_API.search(word)]
    data = next((value for name, value in sent if name in HTTP_BODY), None)
    body = (read_body(data) if data is not None and data[:1] != "@"
            else None if sent else {key.rstrip(":"): None if key.endswith(":") or value[:1] == "@"
                                    else value for key, _, value in pairs})
    method = next((value.upper() for name, value in reversed(flags)
                   if name in ("-X", "--request", "--method")), None) or next(
        (word for word in operands if word in METHODS), None) or (
        "PUT" if any(name in ("-T", "--upload-file") for name, _ in sent)
        else "POST" if sent or pairs else "GET")
    slug, targets = api_targets(found.group(), method, body, said)
    guard_default(f"{called[0]} to api.github.com{found.group(1) or ''}", place, targets, slug)


# @req> REQ-75038049@hXyFNmxx-SWy rvzbno
def refuse_unheld_script(words, here):
    start = len(words) - len(invoked(words))
    if start and runner(words[start - 1]) in RUNNERS:
        start -= 1
    called = words[start:]
    launcher = os.path.basename(called[0]) if called else ""
    if launcher == "uvx" or launcher in LAUNCHERS and "run" in called[1:]:
        rest = called[1:] if launcher == "uvx" else called[called.index("run") + 1:]
        if found := next((word for word in called if "$" in word or "`" in word), None):
            deny(UNREADABLE.format(what=f"which file {called[0]} run runs past {found}"))
        moved = [value for flag, value in itertools.pairwise(called) if flag in ("--directory", "-C")]
        moved += [word.partition("=")[2] for word in called if word.startswith("--directory=")]
        cwd = os.path.join(here, os.path.expanduser(moved[-1])) if moved else here
        for word in rest:
            bases = [base for base in (cwd, here)
                     if os.path.isfile(os.path.join(base, os.path.expanduser(word)))]
            if not word.startswith("-") and bases:
                judge_run(word, os.path.join(bases[0], os.path.expanduser(word)), False, here)
            elif word.endswith(".py"):
                deny(UNREADABLE.format(what=f"{word}, which does not exist yet"))
        for flag, value in itertools.pairwise([*rest, ""]):
            module = value if flag in ("-m", "--module") else flag.partition("=")[2] \
                if flag.startswith("--module=") else None
            if module:
                refuse_unheld_script(["python", "-m", module], cwd)
        at = next((at for at, word in enumerate(rest) if runner(word) in RUNNERS), None)
        if at is not None:
            refuse_unheld_script(rest[at:], cwd)
            for script in scripts_within(rest[at:], cwd):
                judge_shell(script, cwd)
        return
    if not called:
        return
    raw, key = called[0], runner(called[0])
    file, module = (raw if key not in RUNNERS and "/" in raw else None), False
    for previous, word in itertools.pairwise(called) if key in RUNNERS else ():
        inline = RUNNERS[key]
        if inline and (word == "-" or word.startswith(("--eval", "--print"))
                       or any(short_flagged([word], letter) for letter in inline)):
            return
        module = key == "python" and previous == "-m"
        if module or (not word.startswith("-") or not inline) and previous not in RUN_VALUED.get(
                key, ()):
            file = word.replace(".", "/") if module else word
            break
    if file:
        judge_run(raw, file, module, here)


# @req> REQ-75038049@hXyFNmxx-SWy yu277l
def judge_run(raw, file, module, here):
    if "$" in file or "`" in file or not here and not os.path.isabs(file):
        deny(UNREADABLE.format(what=f"which file {raw} runs"))
    path = os.path.realpath(os.path.join(here, os.path.expanduser(file)))
    package = module or os.path.isdir(path)
    path = (path + ".py" if module and os.path.isfile(path + ".py")
            else os.path.join(path, "__main__.py") if package else path)
    if not os.path.isfile(path):
        if package:
            return
        deny(UNREADABLE.format(what=f"{file}, which does not exist yet"))
    try:
        data = Path(path).read_bytes()
    except OSError:
        deny(UNREADABLE.format(what=file))
    text = flatten(data.decode(errors="replace")) if CORPUS_ROOT_NAME.encode() in data else ""
    found = CORPUS_DIR.search(text) or ROOT_QUOTED.search(text)
    if not found:
        return
    if (Path(path).is_relative_to(PLUGIN_ROOT) and not CALL["changes_environment"]
            and hashlib.sha256(data).hexdigest() in FINGERPRINTS):
        return
    place = (here, [], {})
    held = git_reads(["rev-parse", "--verify", "-q", "refs/remotes/origin/HEAD:./"
                      + os.path.relpath(path, os.path.realpath(here))], place)
    if not held or held != git_reads(["hash-object", "--no-filters", "--", path], place):
        deny(UNHELD_SCRIPT.format(file=file, found=found.group()))


BARE_ROOTS = (".", "..", "/", "~")
BARE_SWEEP = (*BARE_ROOTS, "*")


def dotted(found):
    dots = [dot for dot in (".", "..") if expands_to(found[0], dot)]
    return "{%s}" % ",".join([found[0], *dots]) if dots else found[0]


def sweeping(targets, here, bare):
    project = os.environ.get("CLAUDE_PROJECT_DIR", "")
    above = {str(path) for root in {Path(project), Path(project).resolve()} if project
             for path in (root, *root.parents)}
    for w in filter(None, targets):
        alts = list(itertools.islice((form for alt in braced(w) for form in braced(re.sub(
            r"(?<![^/])\.[^/]*[*?[][^/]*", dotted, os.path.expanduser(alt)))), 257))
        if (os.path.normpath(w) in bare
                or "$" in w or "`" in w or w.startswith(("~+", "~-"))
                or len(alts) > 256 or SEQUENCE.search(w)
                or any("{" in alt and "," in alt for alt in alts)
                or any(expands_to(form, path) for alt in alts
                       for form in {f(os.path.join(here, alt))
                                    for f in (os.path.normpath, os.path.realpath)}
                       for path in above)
                or not here and any(not os.path.isabs(alt) and fnmatch.fnmatchcase(
                    path, "*" + os.path.normpath("/" + alt).rstrip("/").replace("[^", "[!"))
                    for alt in alts for path in above)
                or GLOB_CHAR.search(w) and any(reaches_corpus(alt, here, True) for alt in alts)):
            return w


def judge_command(said, here, stdin=()):
    words, unquoted = argv(said)
    refuse_destructive_push(said)
    # @req+ REQ-70178381@2GE_TPwGTZKU dbuwzq
    subcommand, _ = git_subcommand(words)
    # @req> REQ-51296881@8h-e1bOYkZtT 4tzkdu
    if subcommand in ("apply", "am"):
        deny(f"git {subcommand} blocked: the paths it writes live inside the "
             "patch, where this guard cannot see them. Use the editing tools, "
             "and reqctl for the corpus.")
    called = invoked(words)
    operands = called[1:]
    plain = called[0] if called else None
    posed = plain is not None and EXPANSION.search(plain) is not None
    # @req> REQ-60587913@64oissmU4Xo2 4qdiqf
    if "xargs" in map(os.path.basename, words[:len(words) - len(called)]) and (
            plain in SHELLS or plain == "git" and subcommand in (None, *JUDGED_GIT)):
        deny(UNREADABLE.format(what=f"the arguments xargs hands {plain} from standard input"))
    # @req> REQ-51296881@8h-e1bOYkZtT jcpru4
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
    # @req> REQ-22704490@u7IClIQOfStA 6cxbfo
    if (plain == "rm" or posed) and any(
            (len(w) > 2 and "--recursive".startswith(w))
            or (w.startswith("-") and not w.startswith("--") and "r" in w.lower())
            for w in operands):
        # @req> REQ-51296881@8h-e1bOYkZtT 7sfcit
        if swept := sweeping(operands, here, BARE_SWEEP):
            deny(f"{posing_as(plain, 'rm')} -r of '{swept}' blocked: it sweeps the requirements "
                 "corpus along with everything else. Name the paths to delete"
                 f"{'' if plain == 'rm' else ', and the command outright'}.")
    # @req> REQ-91051324@ljHcdWSG-nys vdn4ok
    # @req> REQ-22704490@u7IClIQOfStA mrkvmj
    if (plain == "find" or posed) and any("-delete" in bounded(w) for w in operands):
        at = 0
        while at < len(operands) and (operands[at] in ("-H", "-L", "-P", "-D", "--")
                                      or operands[at].startswith("-O")):
            at += 2 if operands[at] == "-D" else 1
        points = list(itertools.takewhile(
            lambda word: not word.startswith("-") and word not in ("(", "!"),
            operands[at:])) or ["."]
        # @req> REQ-51296881@8h-e1bOYkZtT 4k6mvu
        if swept := sweeping(points, here, BARE_ROOTS):
            deny(f"{posing_as(plain, 'find')} -delete from '{swept}' blocked: it could reach the "
                 "project root, a folder above it, or the requirements corpus. Start find "
                 "from the folder that holds what it should delete"
                 f"{'' if plain == 'find' else ', and name the command outright'}.")
    for word in words:
        if "git" in word and "push" in word and word not in ("git", "push"):
            refuse_destructive_push(word)
    # @req+ REQ-75564975@kR-BIGM3krAM vreqvm
    if writes_origin_head(said, plain, here):
        deny(MOVES_ORIGIN_HEAD.format(what=said.strip()))
    refuse_moving_origin_head(words, here)
    # @req- vreqvm
    refuse_commit_on_default(words, here)
    refuse_moving_default(words, here)
    refuse_push_to_default(words, here)
    refuse_api_write(words, here, said)
    refuse_unheld_script(words, here)
    refuse_discarding_work(words, here)
    for script in scripts_within(words, here):
        judge_shell(script, here, stdin)
    if plain in SHELLS and not short_flagged(itertools.takewhile(
            lambda word: word != "--" and word.startswith(("-", "+")), operands), "c"):
        for script in stdin:
            judge_shell(script, here)


def posing_as(plain, tool):
    return tool if plain == tool else f"{plain}, which the guard cannot tell from {tool},"


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
    # @req> REQ-76235768@1l5tlNlByWT6 2j3niw
    if split and split[2] == "filter-branch":
        return [split[3][at + 1] for at, word in enumerate(split[3][:-1])
                if word in FILTER_SCRIPTS]
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


# @req> REQ-22704490@u7IClIQOfStA 3r7rae
# @req> REQ-54260750@MTrWbA9_HZWY pokpqc
def is_corpus_root(word):
    for value in {word, word.rpartition("=")[2]}:
        trimmed = os.path.normpath(EXPANSION.sub("", value)).rstrip("/")
        if trimmed and (trimmed.rsplit("/", 1)[-1] == CORPUS_ROOT_NAME or any(
                GLOB_CHAR.search(segment) and LITERAL_CHAR.search(segment)
                and any(fnmatch.fnmatchcase(CORPUS_ROOT_NAME, alt)
                        for alt in glob_alternatives(segment))
                for segment in trimmed.split("/"))):
            return True
    return False


def segments_hit(globs, names):
    @functools.cache
    def hit(i, j):
        if i == len(globs):
            return j == len(names)
        if globs[i] == "**":
            return hit(i + 1, j) or j < len(names) and hit(i, j + 1)
        return j < len(names) and fnmatch.fnmatchcase(names[j], globs[i]) and hit(i + 1, j + 1)
    return hit(0, 0)


def glob_hits(glob, path, unread):
    anchored = "/" in glob.rstrip("/")
    try:
        return any(segments_hit(
            ([] if anchored else ["**"]) + alt.replace("[^", "[!").strip("/").split("/"),
            path.split("/")) for alt in bounded(glob))
    except re.error:
        return unread


def last_glob(path, globs):
    verdict = None
    for glob in globs:
        negated = glob.startswith("!")
        if glob_hits(glob[negated:], path, not negated):
            verdict = not negated
    return verdict


def admits(rel, globs, kind):
    folders = list(itertools.accumulate(rel.split("/")[:-1], lambda above, name: f"{above}/{name}"))
    if any(last_glob(folder, globs) is False for folder in folders):
        return False
    verdict = last_glob(rel, globs)
    if verdict is not None:
        return verdict
    return all(glob.startswith("!") for glob in globs) and (not kind or kind in YAML_TYPES)


def searched_corpus(args, cwd):
    kind, glob = args.get("type"), args.get("glob") or ""
    if not isinstance(kind, (str, type(None))) or not isinstance(glob, str):
        deny(UNREADABLE.format(what="the type or glob field"))
    base = os.path.realpath(os.path.join(cwd, os.path.expanduser(args.get("path") or cwd)))
    if not os.path.isdir(base):
        return None
    project = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    globs = [piece for word in glob.split()
             for piece in ([word] if "{" in word else word.split(",")) if piece]
    for top in dict.fromkeys((base, *(str(above) for place in (cwd, project)
                                      for above in (Path(place), *Path(place).parents)))):
        root = os.path.realpath(os.path.join(top, CORPUS_ROOT_NAME))
        if os.path.commonpath([root, base]) not in (root, base):
            continue
        for entry in CORPUS_ENTRIES:
            held = os.path.join(root, entry)
            files = [held] if os.path.isfile(held) else [
                os.path.join(folder, name) for folder, _, names in os.walk(held) for name in names]
            if any(admits(os.path.relpath(file, base), globs, kind) for file in files
                   if os.path.commonpath([file, base]) == base):
                return root
    return None


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
             if value for alt in bounded(os.path.expanduser(EXPANSION.sub("*", value))))
    return any(os.path.isabs(path) and reached(path, root) for path in paths)


@functools.lru_cache(maxsize=4096)
def reaches_plugin(word, cwd):
    paths = (os.path.normpath(os.path.join(cwd, alt))
             for value in {word, word.rpartition("=")[2]} if value
             for alt in bounded(os.path.expanduser(EXPANSION.sub("*", os.path.expandvars(value)))))
    return any(Path(os.path.realpath(found)).is_relative_to(PLUGIN_ROOT)
               for path in paths
               for found in (path, *fnmatch.filter([str(PLUGIN_ROOT)], path),
                             *(matches(path) if GLOB_CHAR.search(path) else ())))


def names_plugin(text):
    spelled = os.path.expandvars(text.replace("~", os.path.expanduser("~")))
    return any(root in spelled for root in PLUGIN_SPELLINGS)


# @req> REQ-59919160@eEBU6tuB77Dq gffcbj
def writes_plugin(said, here, whole):
    git = GIT_READ.search(said)
    if ((READ.search(said) or git and git.group("read"))
            and not OUTPUT_FLAG.search(said) and not READ_WRITES.search(said)):
        return False
    words = tokens_of(said)
    called = invoked(words)
    tool = runner(called[0]) if called else ""
    operands = [word for word in called[1:] if not word.startswith("-")]
    plain = [word for previous, word in itertools.pairwise(["", *called])
             if not REDIRECTION.match(word) and not REDIRECTION.fullmatch(previous)]
    script = next((word for previous, word in itertools.pairwise(plain)
                   if not word.startswith("-") and previous not in RUN_VALUED.get(tool, ())), "")
    inline = any(letter in flag for flag in itertools.takewhile(lambda word: word.startswith("-"), plain[1:])
                 for letter in RUNNERS.get(tool, ""))
    from_stdin = not script or os.path.normpath(os.path.join(here or "/", script)).lstrip("/").startswith(
        ("dev/", "proc/"))
    if tool in RUNNERS and (inline or from_stdin) and names_plugin(whole):
        return True
    naming = [word for word in words if reaches_plugin(word, here)]
    if not naming and not names_plugin(said):
        return tool in WRITERS and (
            any(EXPANSION.search(os.path.expandvars(word)) for word in called[1:])
            or not here and any(not os.path.isabs(os.path.expanduser(word)) for word in operands))
    if tool in ("cd", "pushd"):
        return False
    if tool in RUNNERS:
        return inline or set(naming) - {script} or names_plugin(said.replace(script, "", 1))
    if tool in ("cp", "rsync"):
        return (not operands or reaches_plugin(operands[-1], here)
                or any(word.startswith(("-t", "--target")) for word in called))
    return True


def expands(word):
    bare = PARAMETER.sub("", word)
    return "{" in bare and ("," in bare or ".." in bare)


def bounded(word):
    found = list(itertools.islice(braced(word), 257))
    if len(found) > 256:
        deny(UNREADABLE.format(what=f"{word}, past 256 brace alternatives"))
    return found


def search_operands(words):
    called = invoked(words)
    tool = called[0] if called else ""
    if tool not in ("grep", "egrep", "fgrep", "rg"):
        return words
    valued = SEARCH_VALUED["rg" if tool == "rg" else "grep"]
    head = list(itertools.takewhile(lambda word: word != "--", called[1:]))
    flags, positional = options(head, valued)
    positional += called[len(head) + 2:]
    explicit = any(name in ("-e", "-f", "--regexp", "--file", "--files", "--type-list")
                   for name, _ in flags) or any(
        not word.startswith("--") and len(word) > 2 and set("ef") & set(word[1:])
        for word in called[1:] if word.startswith("-"))
    kept = [word for name, value in flags if not (
        name in EXCLUDED_BY or name in GLOBBED_BY and value.startswith("!"))
            for word in (name, value) if word]
    return [*words[:len(words) - len(called) + 1], *kept, *positional[not explicit:]]


# @req> REQ-59919160@eEBU6tuB77Dq wxfbic
def judge_plugin_writes(pipelines, places, unquoted, cwd, running):
    heres = {cwd}.union(*places)
    for found in REDIRECT_TARGET.finditer(masked(unquoted)):
        target = unquoted[found.start(1):found.end(1)]
        if (names_plugin(target) or EXPANSION.search(os.path.expandvars(target))
                or "" in heres and not os.path.isabs(os.path.expanduser(target.strip()))
                or any(reaches_plugin(word, here) for word in tokens_of(target) for here in heres)):
            deny(PLUGIN_WRITE.format(target=unquoted[found.start():found.end()]))
    for pipeline, places_of in zip(pipelines, places):
        naming = [part for part, here in itertools.product(pipeline, places_of)
                  if names_plugin(heading(part)) or any(reaches_plugin(word, here)
                                                        for word in tokens_of(heading(part)))]
        for part, here in itertools.product(pipeline, places_of):
            said = heading(part)
            if writes_plugin(said, here, unquoted) or naming and (running or part not in naming and not (
                    READ.search(said) or GIT_READ.search(said)
                    or SINK.search(said) and not SINK_WRITES.search(said))):
                deny(PLUGIN_WRITE.format(target=said.strip()))


def names_corpus(part, cwd):
    if CORPUS_DIR.search(part):
        return True
    operands = [GLUED_OPTION.sub("", word) for word in search_operands(tokens_of(heading(part)))]
    return any(CORPUS_DIR.search(word) or is_corpus_root(word)
               or reaches_corpus(word, cwd) for word in operands)


@functools.cache
def judge_shell(raw, cwd, stdin=()):
    # @req+ REQ-22704490@u7IClIQOfStA ak47k7
    if (spelled := ansi_c(raw)) != raw:
        judge_shell(spelled, cwd, stdin)
    cmd = flatten(ESCAPE.sub("", raw))
    joins = []
    pipelines = scan(AMP_REDIRECT.sub(" ", cmd), joins)
    places = cwds(pipelines, joins, cwd)
    assigned = assignments(pipelines)
    unquoted = QUOTED_REDIRECT.sub(r"\1\3", cmd.replace("\\\n", ""))
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
    judge_plugin_writes(pipelines, places, unquoted, cwd, running)
    for pipeline, heres in zip(pipelines, places):
        for (at, part), here in itertools.product(enumerate(pipeline), heres):
            left()
            invocation = heading(part)
            # @req> REQ-21901290@fc_rdI5ms5IC 5zrapb
            # @req> REQ-91051324@ljHcdWSG-nys 343uga
            # @req> REQ-70178381@2GE_TPwGTZKU vzfqst
            for spelled in resolved(invocation, assigned):
                judge_command(spelled, here, piped(stdin, pipeline, at))
            judge_command(part if any(
                len(alternatives) > 256 or any(map(STDIN_ARGUMENTS.search, alternatives))
                for word in tokens_of(invocation)
                for alternatives in [list(itertools.islice(braced(word), 257))]) else invocation,
                here, piped(stdin, pipeline, at))
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
        for (at, part), here in itertools.product(enumerate(pipeline), heres):
            for script in nested(part):
                left()
                judge_shell(script, here, piped(stdin, pipeline, at))
    # @req- ak47k7


def assignments(pipelines):
    assigned = {}
    for part in itertools.chain.from_iterable(pipelines):
        words = list(itertools.dropwhile(lambda word: word in SETTERS or word.startswith("-"),
                                         tokens_of(heading(part))))
        if words and all(ASSIGNMENT.match(word) for word in words):
            for word in words:
                name, _, value = word.partition("=")
                assigned.setdefault(name, set()).add(value)
    return assigned


def resolved(invocation, assigned):
    for name, values in assigned.items():
        named = re.compile(rf"\$(?:\{{{name}\}}|{name}(?!\w))")
        if named.search(invocation):
            for value in values:
                for spelled in (shlex.quote(value), value):
                    yield named.sub(spelled.replace("\\", "\\\\"), invocation)


def ansi_c(raw):
    pieces, at = [], 0
    for found in ANSI_C.finditer(masked(raw)):
        if found[1] is not None and len(found[1]) % 2:
            text = raw[found.start(2) + 1:found.end() - 1]
            pieces += [raw[at:found.start(2) - 1], shlex.quote(ANSI_ESCAPE.sub(escaped, text))]
            at = found.end()
    return "".join(pieces) + raw[at:]


def escaped(found):
    digits = next((group for group in found.groups() if group), None)
    return found[0] if digits is None else chr(min(int(digits, 8 if found[1] else 16),
                                                   sys.maxunicode))


def piped(stdin, pipeline, at):
    return (*stdin, *(text for part in pipeline[:at + 1] for text in feeds(part)))


@functools.cache
def feeds(part):
    said = heading(part)
    words, bare = tokens_of(said), tokens_of(masked(said))
    echoed = invoked(argv(said[COMPOUND.match(masked(said)).end():])[0])
    texts = [part[len(said):]]
    if echoed[:1] == ["echo"]:
        texts.append(" ".join(itertools.dropwhile(ECHO_FLAGS.fullmatch, echoed[1:])))
    for word, mask, following in zip(words, bare, [*words[1:], ""]):
        if (found := REDIRECTION.match(mask)) and found[0].endswith("<<<"):
            texts.append(word[found.end():] or following)
    return tuple(dict.fromkeys(alt for text in texts if text
                               for alt in (text, re.sub(r"\\([\\`$])", r"\1", text))))


def cwds(pipelines, joins, cwd):
    places, heres, start = [], {cwd}, {cwd}
    for pipeline, before, after in zip(pipelines, [";", *joins], joins):
        certain = before not in ("&&", "||")
        start = heres if certain else start
        places.append(sorted(heres))
        heres = start if after == "&" else moved(pipeline, heres, certain, places)
        if len(heres) > CWD_LIMIT:
            deny(UNREADABLE.format(what=f"where the command runs, past {CWD_LIMIT} folders"))
    return places


def moved(pipeline, heres, certain, places):
    said = heading(pipeline[-1])
    at = COMPOUND.match(masked(said)).end()
    certain = certain and not at and len(pipeline) == 1
    called = invoked(argv(said[at:])[0])
    if called[:1] == ["eval"]:
        called = invoked(argv(" ".join(called[1:]))[0])
    tool, *rest = called or [""]
    if tool not in ("cd", "pushd", "popd"):
        return heres
    folder = next((word for word in rest if word == "-" or not word.startswith(
        "-" if tool == "cd" else ("-", "+"))), "~" if tool == "cd" else None)
    if tool == "popd" or folder is None:
        return heres.union(*places)
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
        # @req> REQ-67599992@TMfnHY-C4hOv lh5igq
        if old and old not in after and any(
                CITATION_LINE.match(line) for text in (after, new) for line in text.split("\n")):
            deny(INEXACT.format(target=target))
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


# @req> REQ-38099593@WZbBLy6bHv3j 3yvytz
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


# @req> REQ-38099593@WZbBLy6bHv3j cebvfg
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

    # @req> REQ-54260750@MTrWbA9_HZWY haai6c
    if tool not in READS_NO_URL:
        for path in file_urls(args):
            named = flatten(path)
            if CORPUS_DIR.search(named) or is_corpus_root(named) or reaches_corpus(named, cwd):
                deny(DIRECT_READ.format(target=path))

    # @req> REQ-22704490@u7IClIQOfStA qfasw3
    if tool not in ("Bash", "Read", "Grep", "Glob"):
        for value in dict.fromkeys(spelled for found in named_paths(args) + bare_paths(args)
                                   for spelled in (found, unquote(found))):
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

    # @req> REQ-59919160@eEBU6tuB77Dq sdfaun
    if tool not in ("Bash", "Read", "Grep", "Glob"):
        for value in named_paths(args) + bare_paths(args):
            if names_plugin(value) or reaches_plugin(value, cwd):
                deny(PLUGIN_WRITE.format(target=f"{tool} of {value}"))

    # @req> REQ-75564975@kR-BIGM3krAM cxtbyd
    if tool not in ("Bash", "Read", "Grep", "Glob"):
        for value in named_paths(args) + bare_paths(args):
            if ORIGIN_HEAD_FILE.search(flatten(value.replace("\\", "/"))):
                deny(MOVES_ORIGIN_HEAD.format(what=f"{tool} of {value}"))

    # @req> REQ-54260750@MTrWbA9_HZWY xkcay3
    if tool in ("Read", "Grep", "Glob"):
        paths = named_paths(args)
        values = paths + named_paths(args, GLOB_KEY if tool == "Glob" else GREP_GLOB_KEY)
        for value in values:
            named = flatten(value.replace("\\", "/"))
            if (CORPUS_DIR.search(named) or is_corpus_root(named)
                    or value in paths and reaches_corpus(named, cwd)):
                deny(DIRECT_READ.format(target=value))
        if tool == "Grep" and (root := searched_corpus(args, cwd)):
            deny(SEARCHES_CORPUS.format(base=args.get("path") or cwd, root=root))

    # @req> REQ-30013664@ijHTWP75cTcK dwz6id
    if CONNECTOR_WRITE.search(tool):
        owner, repo, branch = args.get("owner"), args.get("repo"), args.get("branch") or ""
        guard_default(tool, (cwd, [], {}), [
            branch.removeprefix("refs/heads/") if isinstance(branch, str) else None],
            f"{owner}/{repo}" if all(isinstance(v, str) and v for v in (owner, repo)) else None)

    judge_citation_edit(tool, args, cwd)
    commands = [messageless(value) for value in named_paths(args, COMMAND_KEY)]
    # @req> REQ-75038049@hXyFNmxx-SWy hwgp36
    CALL["changes_environment"] = any(
        ENV_CHANGE.search(re.sub(r"[\\'\"]", "", ansi_c(judged).replace("\\\n", "")))
                                      for judged in commands)
    for judged in commands:
        judge_shell(judged, cwd)
        judge_citation_shell(judged)


def main() -> None:
    # @req+ REQ-18701923@7CvKXOjSI6Kb mvehq6
    try:
        data = json.load(sys.stdin)
    except Exception:
        deny(UNREADABLE.format(what="the hook input, which is not JSON"))
    if not isinstance(data, dict):
        deny(UNREADABLE.format(what="the hook input, which is not a JSON object"))
    # @req- mvehq6
    # @req+ REQ-51060455@Z5EVUURxm1nV 4gmqti
    try:
        decide(data)
    except Exception as error:
        deny(UNREADABLE.format(what=f"the call: judging it raised {type(error).__name__}"))
    sys.exit(0)
    # @req- 4gmqti


if __name__ == "__main__":
    # @req> REQ-38288492@4l6tMNjp19tH bhnqhd
    main()
