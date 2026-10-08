#!/usr/bin/env python3
import argparse
import ast
import subprocess
import sys
from pathlib import Path

SINKS = ("help", "description", "epilog")
PARSERS = ("ArgumentParser", "add_argument", "add_argument_group",
           "add_mutually_exclusive_group", "add_parser", "add_subparsers")
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
    sinks, owners = {}, {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        slots = ({arg.arg: at for at, arg in
                  enumerate(node.args.posonlyargs + node.args.args)}
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
                    sinks.setdefault(node.name, set()).add(
                        (slots[keyword.value.id], keyword.value.id))
    return sinks, owners


def survey(paths):
    counted, refused = 0, []
    # @req> GUARD-21526521@G_BddcqGKnJP pcvm4c
    # @req> GUARD-83751348@rb37sHKC5bnL nafhnh
    for path in paths:
        tree = parsed_tree(path)
        sinks, owners = forwarders(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = named(node)
            if name in PARSERS or name in sinks:
                refused += [(path, keyword.value.lineno,
                             f"{name}() is given ** keywords this guard cannot "
                             "read; write each one out")
                            for keyword in node.keywords if keyword.arg is None]
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
            for keyword in node.keywords:
                if keyword.arg not in SINKS:
                    continue
                if is_literal(keyword.value):
                    counted += 1
                    # @req> GUARD-75672058@ekQlMqKRpmul vdrexj
                    if path != CLI:
                        refused.append((path, keyword.value.lineno, STRAY))
                elif isinstance(keyword.value, ast.Name):
                    if keyword.value.id not in {
                            param for _, param in sinks.get(owners.get(id(node)), ())}:
                        refused.append(
                            (path, keyword.value.lineno,
                             f"{keyword.arg}= is given a name this guard "
                             "cannot resolve to its text"))
                else:
                    refused.append(
                        (path, keyword.value.lineno,
                         f"{keyword.arg}= is built by an expression this guard "
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
