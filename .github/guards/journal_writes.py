#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

import references
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
ARITY = {"rename": (1, 1, "target"), "replace": (1, 1, "target"),
         "unlink": (0, 1, "missing_ok")}
MODULES = {name.split(".")[0] for name in FUNCTIONS} | {PATH.split(".")[0]}
WRITING_MODES = set("wax+")
STRAY = (f"makes one of the {DATA} outside {JOURNAL} -- change the file "
         "through corpus.atomic_write or corpus.remove")


def imported(tree):
    held = {"open": "builtins.open"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                held[bound] = alias.name if alias.asname else bound
        elif isinstance(node, ast.ImportFrom):
            source = "." * node.level + (node.module or "")
            for alias in node.names:
                held[alias.asname or alias.name] = f"{source}.{alias.name}"
    return held


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


def opened(node, name, held):
    if any(isinstance(one, ast.Starred) for one in node.args) or any(
            one.arg is None for one in node.keywords):
        return None
    if name in FUNCTIONS or name == f"{PATH}.open":
        target = argument(node, 0, "path" if name == "os.open" else "file")
        if resolved(target, held) == "os.devnull":
            return False
        if name == "os.open":
            return resolved(argument(node, 1, "flags"), held) != "os.O_RDONLY"
        return mode_writes(argument(node, 1, "mode"))
    keyed = next((one.value for one in node.keywords if one.arg == "mode"),
                 None)
    if keyed is not None:
        return mode_writes(keyed)
    return bool(mode_writes(node.args[0] if node.args else None))


def classified(node, held):
    func = node.func
    name = resolved(func, held)
    if name in FUNCTIONS:
        return FUNCTIONS[name], name
    if not isinstance(func, ast.Attribute) or func.attr not in METHODS:
        return None
    owner = resolved(func.value, held)
    if owner == PATH:
        return METHODS[func.attr], name
    if isinstance(func.value, ast.Name) and owner == func.value.id:
        return None
    if func.attr in ARITY:
        low, high, keyword = ARITY[func.attr]
        given = len(node.args) + sum(one.arg in (keyword, None)
                                     for one in node.keywords)
        if not low <= given <= high:
            return None
    return METHODS[func.attr], ast.unparse(func)


# @req+ GUARD-15820124@9ypnh2GEXx5T 4squcr
def refusals(path):
    tree = references.parsed(path)
    held = imported(tree)
    for node in ast.walk(tree):
        if (isinstance(node, ast.ImportFrom) and node.module in MODULES
                and any(alias.name == "*" for alias in node.names)):
            yield node.lineno, (f"from {node.module} import * hides which of "
                                f"the {DATA} this file makes -- import the "
                                "names it uses")
        if not isinstance(node, ast.Call):
            continue
        made = classified(node, held)
        if made is None:
            continue
        member, form = made
        writes = (opened(node, form, held) if member == "open_to_write"
                  else True)
        if writes is None:
            yield node.lineno, (f"{form} is given a mode this guard cannot "
                                "read -- state it as a literal")
        elif writes:
            yield node.lineno, f"{form} {STRAY}"


def drift(root):
    stated = set(corpus.entries(corpus.read(corpus.path_for(root, DATA)))
                 or {})
    known = set(FUNCTIONS.values()) | set(METHODS.values())
    return ([f"{DATA} names {member}, which {Path(__file__).name} does not "
             "refuse -- teach it that member's calls"
             for member in sorted(stated - known)]
            + [f"{Path(__file__).name} refuses {member}, which {DATA} does "
               "not name -- drop it from the guard"
               for member in sorted(known - stated)])


def main():
    found = [f"::error::{fault}" for fault in drift(Path("."))]
    paths = references.tracked(*(f"{root}/*.py" for root in SOURCES))
    found += [f"::error::no Python file lies under {root}/ -- point SOURCES "
              f"in {Path(__file__).name} at the sources"
              for root in SOURCES
              if not any(path.startswith(f"{root}/") for path in paths)]
    found += [f"::error file={path},line={line}::{why}"
              for path in paths if path != JOURNAL
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
