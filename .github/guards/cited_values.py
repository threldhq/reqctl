#!/usr/bin/env python3
import argparse
import ast
import json
import os
import re
import sys
from collections import Counter
from itertools import groupby
from pathlib import Path
from re import _constants as sre, _parser

from citations import read, touched

ROOT = Path(__file__).resolve().parents[2]
SPAN = re.compile(r"`([^`]+)`")
QUOTED = re.compile(r"\"([^\"]*)\"|'([^']*)'")
LISTED = re.compile(r"[^\s,]+(?:\s*,\s*[^\s,]+)+")
FIELD = re.compile(r"\s*([\w-]+):\s*(.*?)\s*")


def carried(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return node


def keyed(node):
    return {key.value if isinstance(key, ast.Constant)
            else f"[{ast.unparse(key) if key else '**' + ast.unparse(value)}]": value
            for key, value in zip(node.keys, node.values)}


def canonical(value):
    return json.dumps(value, sort_keys=True, default=repr)


def compared(where, entry, held, stated):
    for field, node in held.items():
        value = carried(node)
        if isinstance(value, ast.AST):
            yield (f"{where} carries {entry}.{field} as "
                   f"{ast.unparse(value)!r}, which the build cannot compare "
                   "with the corpus -- write the value itself")
        elif field not in stated:
            yield (f"{where} carries {entry}.{field} {value!r}, a field the "
                   "corpus does not state for that entry")
        elif canonical(value) != canonical(stated[field]):
            yield (f"{where} carries {entry}.{field} {value!r}, the corpus "
                   f"states {stated[field]!r}")


def spellings(name, fields):
    found = {name}
    for value in fields.values():
        for part in value if isinstance(value, list) else [value]:
            if isinstance(part, str):
                found.add(part)
                found.update(word.rstrip(",;.") for word in part.split())
    return found


def spelled(sub):
    found = [""]
    for op, av in sub:
        if op == sre.LITERAL:
            parts = [chr(av)]
        elif op == sre.IN and all(kind == sre.LITERAL for kind, _ in av):
            parts = [chr(code) for _, code in av]
        elif op == sre.SUBPATTERN:
            parts = spelled(av[-1])
        elif op == sre.BRANCH:
            subs = [spelled(branch) for branch in av[1]]
            parts = None if None in subs else [tail for sub in subs for tail in sub]
        elif op == sre.ATOMIC_GROUP:
            parts = spelled(av)
        elif op == sre.AT:
            parts = [""]
        else:
            return None
        if parts is None:
            return None
        found = [head + tail for head in found for tail in parts]
    return found


def branched(sub, lists, prefix="", suffix=""):
    sub = ([(sre.LITERAL, ord(char)) for char in prefix] + list(sub)
           + [(sre.LITERAL, ord(char)) for char in suffix])
    runs = [list(run) for _, run in
            groupby(sub, lambda item: spelled([item]) is not None)]
    texts = [spelled(run) for run in runs]
    for index, (run, parts) in enumerate(zip(runs, texts)):
        if parts is not None:
            if len(parts) > 1:
                lists.append(("members", [(text, repr(text)) for text in parts]))
            continue
        lead = texts[index - 1][0] if index and len(texts[index - 1]) == 1 else ""
        trail = (texts[index + 1][0]
                 if index + 1 < len(runs) and len(texts[index + 1]) == 1 else "")
        for place, (op, av) in enumerate(run):
            head = lead if place == 0 else ""
            tail = trail if place == len(run) - 1 else ""
            if op == sre.BRANCH:
                members = []
                for branch in av[1]:
                    alternative = spelled(branch)
                    if alternative is None:
                        members.append((None, "an alternative of no fixed spelling"))
                        branched(branch, lists, head, tail)
                    else:
                        members.extend((head + part + tail, repr(head + part + tail))
                                       for part in alternative)
                lists.append(("members", members))
            elif op == sre.SUBPATTERN:
                branched(av[-1], lists, head, tail)
            else:
                for held in av if isinstance(av, (tuple, list)) else [av]:
                    if isinstance(held, _parser.SubPattern):
                        branched(held, lists)


def literal(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def member(node):
    return ((node.value, repr(node.value)) if literal(node)
            else (None, ast.unparse(node)))


def gathered(node, first, last, carriers):
    inside = (getattr(node, "lineno", None) is not None
              and first <= node.lineno and node.end_lineno <= last)
    if inside and isinstance(node, ast.Dict):
        carriers.append(("dict", keyed(node)))
    elif inside and isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        members = []
        for element in node.elts:
            if (isinstance(element, (ast.Tuple, ast.List)) and element.elts
                    and literal(element.elts[0])):
                members.append(member(element.elts[0]))
                for rest in element.elts[1:]:
                    gathered(rest, first, last, carriers)
            else:
                members.append(member(element))
                if not literal(element):
                    gathered(element, first, last, carriers)
        carriers.append(("members", members))
    elif (inside and isinstance(node, ast.Call)
          and isinstance(node.func, ast.Attribute)
          and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
          and node.args and literal(node.args[0])):
        branched(_parser.parse(node.args[0].value), carriers)
        for rest in node.args[1:] + [keyword.value for keyword in node.keywords]:
            gathered(rest, first, last, carriers)
    elif inside and literal(node):
        carriers.append(("members", [member(node)]))
    else:
        for child in ast.iter_child_nodes(node):
            gathered(child, first, last, carriers)


def written(text, path, numbers):
    front = ()
    if text and text[0].strip() == "---" and path.endswith(".md"):
        end = next((index for index, line in enumerate(text[1:], 2)
                    if line.strip() == "---"), 1)
        front = range(2, end)
    carriers = []
    for number in numbers:
        line = text[number - 1]
        body = line.strip().rstrip(";.")
        if number in front:
            field = FIELD.fullmatch(line)
            if field:
                carriers.append(("fields", {field[1]: field[2]}))
        elif path.endswith(".md") and SPAN.search(line):
            carriers.append(("members", [(span, f"`{span}`")
                                         for span in SPAN.findall(line)]))
        elif path.endswith(".md") and LISTED.fullmatch(body):
            carriers.append(("members", [(part.strip(), repr(part.strip()))
                                         for part in body.split(",")]))
        elif not path.endswith(".md") and QUOTED.search(line):
            carriers.append(("members", [
                (found[found.lastindex], found[0])
                for found in QUOTED.finditer(line)]))
    return carriers


# @req> GUARD-21296330@1vKKetZd35C0 gcjdgm
def judged(where, uid, entry, stated, carriers):
    if entry and entry not in stated:
        return [f"{where} names {entry}, an entry the corpus does not state "
                f"for {uid}"]
    named = {name: spellings(name, fields) for name, fields in stated.items()}
    counts, fielded, found = Counter(), set(), []
    for kind, held in carriers:
        if kind == "fields" and entry is None:
            found.append(f"{where} cites the whole of {uid} over front matter "
                         "-- cite the entry whose fields it carries")
        elif kind == "fields":
            fielded.add(entry)
            found.extend(compared(where, entry, {
                field: ast.Constant([part.strip() for part in text.split(",")]
                                    if isinstance(stated[entry].get(field), list)
                                    else text)
                for field, text in held.items()}, stated[entry]))
        elif kind == "dict" and not held.keys() & stated.keys():
            if entry and held.keys() & stated[entry].keys():
                fielded.add(entry)
                found.extend(compared(where, entry, held, stated[entry]))
        elif kind == "dict":
            for name, fields in held.items():
                if name not in stated:
                    found.append(f"{where} carries {name!r}, an entry the "
                                 f"corpus does not state for {uid}")
                    continue
                counts[name] += 1
                if isinstance(fields, ast.Dict):
                    found.extend(compared(where, name, keyed(fields),
                                          stated[name]))
                else:
                    found.append(f"{where} carries {name} as "
                                 f"{ast.unparse(fields)!r} -- write its "
                                 "fields as a dict the build can compare")
        else:
            owners = [None if text is None
                      else [name for name, said in named.items() if text in said]
                      for text, _ in held]
            if not any(owners):
                continue
            for (text, shown), names in zip(held, owners):
                if names is None:
                    found.append(f"{where} carries {shown}, which the build "
                                 "cannot compare with the corpus -- write the "
                                 "value itself")
                elif not names:
                    found.append(f"{where} carries {shown}, which the corpus "
                                 f"does not state for {uid}")
                elif len(names) > 1:
                    found.append(f"{where} carries {shown}, which spells "
                                 f"{', '.join(names)} at once -- write the "
                                 "value of one entry")
                else:
                    counts.update(names)
    if entry is None or stated[entry] or counts or fielded:
        found.extend(f"{where} does not carry {name}, an entry the corpus "
                     f"states for {uid}"
                     for name in ([entry] if entry else sorted(stated))
                     if name not in counts and name not in fielded)
    found.extend(f"{where} carries {name} {count} times -- carry it once"
                 for name, count in sorted(counts.items()) if count > 1)
    return found


def faults(citations, entries):
    texts, found, checked = {}, [], 0
    for citation in citations:
        stated = entries.get(citation["uid"])
        path = citation["path"]
        if stated is None:
            continue
        if path not in texts:
            # @req+ GUARD-83168738@zhoOQpGgBd9R 45c7wu
            try:
                text = (ROOT / path).read_text()
                texts[path] = (ast.parse(text) if path.endswith(".py")
                               else text.splitlines())
            except (OSError, UnicodeDecodeError, SyntaxError) as error:
                found.append(f"{path}: cannot parse: {error}")
                texts[path] = None
            # @req- 45c7wu
        if texts[path] is None:
            continue
        where = (f"citation {citation['id']} of {citation['address']} in "
                 f"{path}:{citation['first']}-{citation['last']}")
        carriers = []
        # @req+ GUARD-83168738@zhoOQpGgBd9R jc5ad4
        try:
            if path.endswith(".py"):
                gathered(texts[path], citation["first"], citation["last"],
                         carriers)
            else:
                carriers = written(texts[path], path, citation["lines"])
        except re.error as error:
            found.append(f"{where} carries a pattern that cannot parse: {error}")
            continue
        # @req- jc5ad4
        checked += 1
        found.extend(judged(where, citation["uid"], citation["entry"], stated,
                            carriers))
    return found, checked


# @req> GUARD-21296330@1vKKetZd35C0 yggkzf
def main():
    trace = read("trace")
    if not isinstance(trace, dict) or "citations" not in trace:
        raise SystemExit(f"cannot read trace: {trace}")
    listed = read("list", "data")
    if not isinstance(listed, dict) or "items" not in listed:
        raise SystemExit(f"cannot read the data items: {listed}")
    data = {item["uid"] for item in listed["items"]}
    citations = trace["citations"]
    # @req+ GUARD-21296330@1vKKetZd35C0 ijk324
    base = os.environ.get("BASE_REF", "")
    if base:
        changed = touched(base, [(row["id"], row["path"],
                                  f"{row['address']}@{row['pinned']} {row['id']}", None)
                                 for row in citations if row["uid"] in data])
        citations = [row for row in citations if row["id"] in changed]
    # @req- ijk324
    cited = sorted({row["uid"] for row in citations} & data)
    contexts = read("context", *cited) if cited else []
    if not isinstance(contexts, list):
        raise SystemExit(f"cannot read context: {contexts}")
    if sorted(item["uid"] for item in contexts) != cited:
        raise SystemExit(f"cannot read context: asked for {cited}, read "
                         f"{sorted(item['uid'] for item in contexts)}")
    found, checked = faults(citations,
                            {item["uid"]: item["entries"] for item in contexts})
    for fault in found:
        print(f"::error::{fault}")
    print(f"compared {checked} data-item citation(s) with the corpus")
    return 1 if found else 0


# @req> GUARD-21296330@1vKKetZd35C0 6aeg2s
if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    sys.exit(main())
