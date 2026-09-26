#!/usr/bin/env python3
import argparse
import ast
import subprocess
import sys
from pathlib import Path

SINKS = ("help", "description", "epilog")
GOVERNED = "requirements/"
CLI = "reqctl/reqctl/cli.py"


def scanned():
    found = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "*.py"],
        capture_output=True, text=True, check=False)
    if found.returncode != 0:
        raise SystemExit(f"cannot list files: {found.stderr.strip()}")
    return sorted({path for path in found.stdout.split("\0")
                   if path and not path.startswith(GOVERNED)})


def parsed_tree(path):
    try:
        return ast.parse(Path(path).read_text(encoding="utf-8"),
                         filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as broken:
        raise SystemExit(f"cannot read {path}: {broken}") from broken


def is_literal(node):
    return isinstance(node, (ast.Constant, ast.JoinedStr))


def named(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def forwarders(tree):
    sinks, forwarded, owners = {}, set(), {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        taken = [arg.arg for arg in node.args.args]
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            owners.setdefault(id(inner), node.name)
            for keyword in inner.keywords:
                if keyword.arg not in SINKS:
                    continue
                if not isinstance(keyword.value, ast.Name):
                    continue
                if keyword.value.id in taken:
                    sinks.setdefault(node.name, set()).add(
                        taken.index(keyword.value.id))
                    forwarded.add((node.name, keyword.value.id))
    return sinks, forwarded, owners


def survey(paths):
    counted, refused = 0, []
    for path in paths:
        tree = parsed_tree(path)
        sinks, forwarded, owners = forwarders(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = named(node)
            for spot in sinks.get(name, ()):
                if spot < len(node.args):
                    said = node.args[spot]
                    if is_literal(said):
                        counted += 1
                    else:
                        refused.append(
                            (path, said.lineno,
                             f"{name}() is given help text this guard cannot read"))
            for keyword in node.keywords:
                if keyword.arg not in SINKS:
                    continue
                if is_literal(keyword.value):
                    counted += 1
                elif isinstance(keyword.value, ast.Name):
                    if (owners.get(id(node)), keyword.value.id) not in forwarded:
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
    counted, refused, strays = 0, [], []
    for path in scanned():
        held, why = survey([path])
        counted += held
        refused += why
        if held and path != CLI:
            strays.append(path)
    for path, line, why in refused:
        print(f"::error file={path},line={line}::{why}")
    for path in strays:
        print(f"::error file={path}::gives an argument parser help text, "
              f"which only {CLI} may; delete it")
    print(f"{counted} help strings")
    if refused or strays:
        return 1
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
