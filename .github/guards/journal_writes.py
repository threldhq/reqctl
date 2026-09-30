#!/usr/bin/env python3
import ast
import subprocess
import sys
from pathlib import Path

from reqctl import corpus

SOURCES = ("reqctl", "plugin")
JOURNAL = "reqctl/reqctl/corpus.py"
DATA = "file_writes"
PATH = "pathlib.Path"
# @req+ GUARD-15820124@9ypnh2GEXx5T kcim4i
FUNCTIONS = {
    "builtins.open": "open_to_write", "io.open": "open_to_write",
    "os.open": "open_to_write",
    "os.link": "create", "os.symlink": "create", "tempfile.mkstemp": "create",
    "tempfile.NamedTemporaryFile": "create", "tempfile.TemporaryFile": "create",
    "os.rename": "rename", "os.renames": "rename", "os.replace": "rename",
    "shutil.move": "rename",
    "os.remove": "delete", "os.unlink": "delete", "shutil.rmtree": "delete",
    "shutil.copyfile": "copy", "shutil.copy": "copy", "shutil.copy2": "copy",
    "shutil.copytree": "copy",
}
METHODS = {
    "open": "open_to_write",
    "write_text": "write", "write_bytes": "write",
    "touch": "create", "symlink_to": "create", "hardlink_to": "create",
    "rename": "rename", "replace": "rename",
    "unlink": "delete",
}
# @req- kcim4i
ONE_TARGET = {"rename", "replace"}
NO_ARGUMENT = {"unlink"}
WRITING_MODES = set("wax+")
WRITING_FLAGS = {"O_WRONLY", "O_RDWR", "O_APPEND", "O_CREAT", "O_TRUNC",
                 "O_TMPFILE"}
STRAY = (f"makes one of the {DATA} outside {JOURNAL} -- change the file "
         "through corpus.atomic_write or corpus.remove")


def scanned():
    found = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", *(f"{root}/*.py" for root in SOURCES)],
        capture_output=True, text=True, check=False)
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    return sorted({path for path in found.stdout.split("\0") if path})


def parsed_tree(path):
    try:
        return ast.parse(Path(path).read_text(encoding="utf-8"),
                         filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as broken:
        raise SystemExit(f"cannot read {path}: {broken}") from broken


def imported(tree):
    held = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                held[alias.asname or root] = (alias.name if alias.asname
                                              else root)
        elif isinstance(node, ast.ImportFrom):
            source = "." * node.level + (node.module or "")
            for alias in node.names:
                held[alias.asname or alias.name] = f"{source}.{alias.name}"
    return held


def shadows_open(tree):
    for node in tree.body:
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)) and node.name == "open"):
            return True
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "open"
                for target in node.targets):
            return True
    return False


def resolved(node, held):
    if isinstance(node, ast.Name):
        return held.get(node.id)
    if isinstance(node, ast.Attribute):
        base = resolved(node.value, held)
        return f"{base}.{node.attr}" if base else None
    return None


def argument(node, spot, keyword):
    if spot < len(node.args):
        return node.args[spot]
    return next((one.value for one in node.keywords if one.arg == keyword),
                None)


def mode_writes(mode):
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return bool(WRITING_MODES & set(mode.value))
    return None


def flags_write(flags):
    if flags is None:
        return None
    named = {node.attr for node in ast.walk(flags)
             if isinstance(node, ast.Attribute)}
    named |= {node.id for node in ast.walk(flags) if isinstance(node, ast.Name)}
    stated = {name for name in named if name.startswith("O_")}
    if stated & WRITING_FLAGS:
        return True
    if not stated or named - stated - {"os"}:
        return None
    return False


def opened(node, name, held):
    if name in ("builtins.open", "io.open", "os.open"):
        target = argument(node, 0, "path" if name == "os.open" else "file")
        if resolved(target, held) == "os.devnull":
            return False
        if name == "os.open":
            return flags_write(argument(node, 1, "flags"))
        return mode_writes(argument(node, 1, "mode"))
    if name == f"{PATH}.open":
        return mode_writes(argument(node, 1, "mode"))
    keyed = next((one.value for one in node.keywords if one.arg == "mode"),
                 None)
    if keyed is not None:
        return mode_writes(keyed)
    first = node.args[0] if node.args else None
    literal = isinstance(first, ast.Constant) and isinstance(first.value, str)
    return mode_writes(first) if literal else False


def classified(node, held, shadowed):
    func = node.func
    name = resolved(func, held)
    if (name is None and isinstance(func, ast.Name) and func.id == "open"
            and not shadowed):
        name = "builtins.open"
    if name in FUNCTIONS:
        return FUNCTIONS[name], name
    if not isinstance(func, ast.Attribute) or func.attr not in METHODS:
        return None
    owner = resolved(func.value, held)
    if owner == PATH:
        return METHODS[func.attr], name
    if isinstance(func.value, ast.Name) and owner is not None:
        return None
    if func.attr in ONE_TARGET and (len(node.args) != 1 or node.keywords):
        return None
    if func.attr in NO_ARGUMENT and node.args:
        return None
    return METHODS[func.attr], ast.unparse(func)


# @req+ GUARD-15820124@9ypnh2GEXx5T 4squcr
def refusals(path):
    tree = parsed_tree(path)
    held, shadowed = imported(tree), shadows_open(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        made = classified(node, held, shadowed)
        if made is None:
            continue
        member, form = made
        writes = (opened(node, form, held) if member == "open_to_write"
                  else True)
        if writes is None:
            found.append((node.lineno, f"{form} is given a mode this guard "
                                       "cannot read -- state it as a literal"))
        elif writes:
            found.append((node.lineno, f"{form} {STRAY}"))
    return found


def drift(root):
    store, _ = corpus.load(root)
    held = {str(item.uid): corpus.raw(item) for item in corpus.items(store)}
    data = held.get(DATA)
    if data is None or corpus.kind_of(DATA, data) != "data":
        return [f"the corpus holds no data item named {DATA} to read the "
                "refused calls from"]
    stated = set(corpus.entries(data) or {})
    known = set(FUNCTIONS.values()) | set(METHODS.values())
    return ([f"{DATA} names {member}, which {Path(__file__).name} does not "
             "refuse -- teach it that member's calls"
             for member in sorted(stated - known)]
            + [f"{Path(__file__).name} refuses {member}, which {DATA} does "
               "not name -- drop it from the guard"
               for member in sorted(known - stated)])


def main():
    found = [f"::error::{fault}" for fault in drift(Path("."))]
    paths = scanned()
    for root in SOURCES:
        if not any(path.startswith(f"{root}/") for path in paths):
            found.append(f"::error::no Python file lies under {root}/ -- point "
                         f"SOURCES in {Path(__file__).name} at the sources")
    for path in paths:
        if path == JOURNAL:
            continue
        found += [f"::error file={path},line={line}::{why}"
                  for line, why in refusals(path)]
    for fault in found:
        print(fault)
    return 1 if found else 0
# @req- 4squcr


if __name__ == "__main__":
    try:
        sys.exit(main())
    except corpus.ReqctlError as unreadable:
        sys.exit(f"{Path(__file__).name}: {unreadable}")
