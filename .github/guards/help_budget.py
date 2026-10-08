#!/usr/bin/env python3
import argparse
import ast
import subprocess
import sys
from pathlib import Path

SINKS = ("help", "description", "epilog")
PARSERS = ("ArgumentParser", "add_argument", "add_argument_group",
           "add_mutually_exclusive_group", "add_parser", "add_subparsers")
POSITIONAL = {"ArgumentParser": {2: "description", 3: "epilog"},
              "add_argument_group": {1: "description"}}
GOVERNED = "requirements/"
CLI = "reqctl/reqctl/cli.py"
STRAY = f"gives an argument parser help text, which only {CLI} may; delete it"


def scanned():
    found = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "*.py"],
        capture_output=True, text=True, check=False)
    # @req> GUARD-83168738@zhoOQpGgBd9R prznio
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    return sorted({path for path in found.stdout.split("\0")
                   if path and not path.startswith(GOVERNED)})


def parsed_tree(path):
    # @req+ GUARD-83168738@zhoOQpGgBd9R agarbl
    try:
        return ast.parse(Path(path).read_text(encoding="utf-8"),
                         filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as broken:
        raise SystemExit(f"cannot read {path}: {broken}") from broken
    # @req- agarbl


def is_literal(node):
    return isinstance(node, (ast.Constant, ast.JoinedStr))


def named(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def forwarders(tree):
    sinks, owners, faults = {}, {}, []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        whole = node.args.posonlyargs + node.args.args
        placed = whole[1:] if whole and whole[0].arg in ("self", "cls") else whole
        defaulted = ({arg.arg for arg in whole[len(whole) - len(node.args.defaults):]}
                     | {arg.arg for arg, value in
                        zip(node.args.kwonlyargs, node.args.kw_defaults)
                        if value is not None})
        took = set()
        slots = ({arg.arg: at for at, arg in enumerate(placed)}
                 | {arg.arg: None for arg in node.args.kwonlyargs})
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            owners.setdefault(id(inner), node.name)
            for keyword in inner.keywords:
                if keyword.arg not in SINKS:
                    continue
                if not isinstance(keyword.value, ast.Name):
                    continue
                if keyword.value.id in slots:
                    took.add(keyword.value.id)
                    sinks.setdefault(node.name, set()).add(
                        (slots[keyword.value.id], keyword.value.id))
        # @req+ GUARD-83751348@rb37sHKC5bnL icqk2j
        if took and node.name in ("__init__", "__call__"):
            faults.append((node.lineno, f"{node.name}() passes help text on, "
                           "which this guard cannot follow; use a function"))
        faults += [(node.lineno, f"{node.name}() gives {param} a default this "
                    "guard cannot count; pass it at each call")
                   for param in sorted(took & defaulted)]
        # @req- icqk2j
    return sinks, owners, faults


def survey(paths):
    counted, refused, sinks, owners = 0, [], {}, {}
    trees = [(path, parsed_tree(path)) for path in paths]
    for path, tree in trees:
        found, held, faults = forwarders(tree)
        refused += [(path, line, why) for line, why in faults]
        for helper, slots in found.items():
            sinks.setdefault(helper, set()).update(slots)
        owners.update(held)
    # @req> GUARD-21526521@G_BddcqGKnJP pcvm4c
    # @req> GUARD-83751348@rb37sHKC5bnL nafhnh
    for path, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = named(node)
            if name in PARSERS or name in sinks:
                refused += [(path, keyword.value.lineno,
                             f"{name}() is given ** keywords this guard cannot "
                             "read; write each one out")
                            for keyword in node.keywords if keyword.arg is None]
                refused += [(path, given.lineno,
                             f"{name}() is given * positionals this guard cannot "
                             "read; write each one out")
                            for given in node.args if isinstance(given, ast.Starred)]
            for spot, param in sinks.get(name, ()):
                if spot is not None and spot < len(node.args):
                    said = node.args[spot]
                else:
                    said = None if param in SINKS else next(
                        (keyword.value for keyword in node.keywords
                         if keyword.arg == param), None)
                if said is not None:
                    if is_literal(said):
                        counted += 1
                        # @req> GUARD-75672058@ekQlMqKRpmul mb63cn
                        if path != CLI:
                            refused.append((path, said.lineno, STRAY))
                    else:
                        refused.append(
                            (path, said.lineno,
                             f"{name}() is given help text this guard cannot read"))
            given = [(keyword.arg, keyword.value) for keyword in node.keywords]
            given += [(sink, node.args[at])
                      for at, sink in POSITIONAL.get(name, {}).items()
                      if at < len(node.args)]
            for sink, value in given:
                if sink not in SINKS:
                    continue
                if is_literal(value):
                    counted += 1
                    # @req> GUARD-75672058@ekQlMqKRpmul vdrexj
                    if path != CLI:
                        refused.append((path, value.lineno, STRAY))
                elif isinstance(value, ast.Name):
                    if value.id not in {
                            param for _, param in sinks.get(owners.get(id(node)), ())}:
                        refused.append(
                            (path, value.lineno,
                             f"{sink}= is given a name this guard "
                             "cannot resolve to its text"))
                else:
                    refused.append(
                        (path, value.lineno,
                         f"{sink}= is built by an expression this guard "
                         "cannot read"))
    return counted, refused


def main(ceiling):
    counted, refused = survey(scanned())
    for path, line, why in refused:
        print(f"::error file={path},line={line}::{why}")
    print(f"{counted} help strings")
    if refused:
        return 1
    # @req> GUARD-21526521@G_BddcqGKnJP v4ifk3
    if counted != ceiling:
        fix = ("Delete it, or raise the ceiling in ci.yml and say who "
               "reads it."
               if counted > ceiling else
               "Lower the ceiling in ci.yml to hold the ground.")
        print(f"::error::the help budget is {ceiling}; this branch has "
              f"{counted}. {fix}")
        return 1
    return 0


if __name__ == "__main__":
    stated = argparse.ArgumentParser()
    stated.add_argument("--max", type=int, required=True)
    sys.exit(main(stated.parse_args().max))
