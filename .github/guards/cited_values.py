#!/usr/bin/env python3
import argparse
import ast
import json
import sys
from pathlib import Path

from citations import read

ROOT = Path(__file__).resolve().parents[2]


def carried(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return node


def keyed(node):
    return {key.value if isinstance(key, ast.Constant)
            else f"[{ast.unparse(key) if key else '**' + ast.unparse(value)}]": value
            for key, value in zip(node.keys, node.values)}


def compared(where, entry, fields, stated):
    # @req> GUARD-21296330@1vKKetZd35C0 3fxisb
    for field, node in keyed(fields).items():
        value = carried(node)
        if isinstance(value, ast.AST):
            yield (f"{where} carries {entry}.{field} as "
                   f"{ast.unparse(value)!r}, which the build cannot compare "
                   "with the corpus -- write the value itself")
        elif field not in stated:
            yield (f"{where} carries {entry}.{field} {value!r}, a field the "
                   "corpus does not state for that entry")
        elif json.dumps(value, sort_keys=True, default=repr) != json.dumps(
                stated[field], sort_keys=True, default=repr):
            yield (f"{where} carries {entry}.{field} {value!r}, the corpus "
                   f"states {stated[field]!r}")


def faults(citations, entries):
    trees, found = {}, []
    for citation in citations:
        stated = entries.get(citation["uid"])
        path = citation["path"]
        if stated is None or not path.endswith(".py"):
            continue
        if path not in trees:
            # @req+ GUARD-83168738@zhoOQpGgBd9R yhsbhh
            try:
                trees[path] = ast.parse((ROOT / path).read_text())
            except (OSError, UnicodeDecodeError, SyntaxError) as error:
                found.append(f"{path}: cannot parse: {error}")
                trees[path] = None
            # @req- yhsbhh
        if trees[path] is None:
            continue
        # @req+ GUARD-21296330@1vKKetZd35C0 jlm6mf
        where = (f"citation {citation['id']} of {citation['address']} in "
                 f"{path}:{citation['first']}-{citation['last']}")
        entry = citation["entry"]
        for node in ast.walk(trees[path]):
            if not (isinstance(node, ast.Dict)
                    and citation["first"] <= node.lineno
                    and node.end_lineno <= citation["last"]):
                continue
            held = keyed(node)
            if entry:
                if entry in stated and held.keys() & stated[entry].keys():
                    found.extend(compared(where, entry, node, stated[entry]))
                continue
            if not held.keys() & stated.keys():
                continue
            for name, fields in held.items():
                if name not in stated:
                    found.append(f"{where} carries {name!r}, an entry the "
                                 f"corpus does not state for {citation['uid']}")
                elif isinstance(fields, ast.Dict):
                    found.extend(compared(where, name, fields, stated[name]))
                else:
                    found.append(f"{where} carries {name} as "
                                 f"{ast.unparse(fields)!r} -- write its "
                                 "fields as a dict the build can compare")
        # @req- jlm6mf
    return found


def main():
    trace = read("trace")
    if not isinstance(trace, dict) or "citations" not in trace:
        raise SystemExit(f"cannot read trace: {trace}")
    listed = read("list", "data")
    if not isinstance(listed, dict) or "items" not in listed:
        raise SystemExit(f"cannot read the data items: {listed}")
    data = {item["uid"] for item in listed["items"]}
    cited = sorted({row["uid"] for row in trace["citations"]} & data)
    held = read("context", *cited) if cited else []
    if not isinstance(held, list):
        raise SystemExit(f"cannot read context: {held}")
    found = faults(trace["citations"],
                   {item["uid"]: item["entries"] for item in held})
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    sys.exit(main())
