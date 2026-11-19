#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from reqctl.reach import Reach

from reqctl import baseline, cite, corpus

# @req> reading_verdicts@wJS-OszXMr_Q dtiqoy
VERDICTS = ("satisfied", "not_satisfied", "cannot_tell")
# @req> REQ-18193596@oSjMcEZMnBK6 6rm73a
OWN = re.compile(r"(text|acceptance criteria|value|entries)\s{2,}")
# @req> REQ-18193596@oSjMcEZMnBK6 4zf45f
NAMED = ("parameters", "concepts")
FOLDER = Path(".reqctl") / "readings"
RECORD = Path(".reqctl") / "readings.json"
# @req> REQ-18193596@oSjMcEZMnBK6 tpw4qc
UNTOUCHED = (["moved"], ["deleted"])


# @req> REQ-18193596@oSjMcEZMnBK6 lcqfuw
def printed(uid):
    done = subprocess.run(["reqctl", "context", uid], capture_output=True,
                          text=True, check=False)
    if done.returncode:
        # @req> REQ-92715984@izHQzbW23L0y rkatxd
        raise corpus.ReqctlError(done.stderr.strip()
                                 or f"reqctl context {uid} exited {done.returncode}")
    return done.stdout


# @req> REQ-18193596@oSjMcEZMnBK6 v5do75
def stated(uid):
    head, *blocks = printed(uid).split("\n\n")
    lines = [line for line in head.split("\n") if OWN.match(line)]
    for block in blocks:
        title, _, body = block.strip("\n").partition("\n")
        if title in NAMED and body:
            lines += ["", title, body]
    return lines


# @req> REQ-18193596@oSjMcEZMnBK6 x2ryeq
def taken(uid, compared, citations, reach):
    wanted = {}
    for row in compared["citations"]:
        if row["uid"] != uid or row["state"] in UNTOUCHED:
            continue
        held = citations[row["id"]]
        wanted.setdefault(held["path"], set()).update(held["lines"])
        for path, line in reach.reached(held["path"], held["lines"]):
            wanted.setdefault(path, set()).add(line)
    marks = {(held["path"], line) for held in citations.values()
             for line in held["marks"]}
    return {path: sorted(line for line in lines if (path, line) not in marks)
            for path, lines in wanted.items()}


# @req> REQ-18193596@oSjMcEZMnBK6 su5ahl
def code(root, uid, compared, citations, reach, texts):
    lines = []
    for path, numbers in sorted(taken(uid, compared, citations, reach).items()):
        said = texts[path].split("\n")
        lines += ["", f"=== {path} ==="]
        for at, number in enumerate(numbers):
            if at and number != numbers[at - 1] + 1:
                lines.append("-----")
            lines.append(said[number - 1])
    for row in compared["files"]:
        if row["uid"] == uid and row["state"] != ["deleted"]:
            lines += ["", f"=== {row['path']} ===",
                      corpus.read_text(root / row["path"]).rstrip("\n")]
    return lines


# @req> REQ-18193596@oSjMcEZMnBK6 xdxo6t
# @req> REQ-18762283@02ASyELj83Tv plidzn
def prompt(root, uid, compared, citations, reach, texts):
    return "\n".join([
        f"ITEM {uid}", *stated(uid), "", "CODE",
        *code(root, uid, compared, citations, reach, texts), "",
        (f"Write your reading to {(FOLDER / uid).as_posix()}.json as one JSON "
         f"object holding verdict, one of {', '.join(VERDICTS)}, and lines, a "
         "list of the lines of the code above that show the verdict, each "
         "copied exactly."), ""])


# @req> REQ-85663008@aQdSXq7ibn2j z6mbsu
def records(root):
    where = root / RECORD
    if not where.exists():
        return {}
    try:
        held = json.loads(corpus.read_text(where))
    except ValueError as broken:
        # @req> REQ-92715984@izHQzbW23L0y 7hkm6e
        raise corpus.ReqctlError(f"{RECORD.as_posix()} does not read as JSON: "
                                 f"{broken} -- delete the file") from broken
    if not isinstance(held, dict):
        # @req> REQ-92715984@izHQzbW23L0y 6nan42
        raise corpus.ReqctlError(f"{RECORD.as_posix()} is not a JSON object "
                                 "-- delete the file")
    return held


# @req> REQ-85663008@aQdSXq7ibn2j neu5tj
def standing(held, text):
    read = held.get(corpus.digest(text))
    return read if isinstance(read, dict) and read.get("verdict") == VERDICTS[0] else None


# @req> REQ-18882967@W34Ole45XgJE 7xdgt7
def shown(uid, read):
    return [f"{uid}: {read['verdict']}", *(f"    {line}" for line in read["lines"])]


# @req> REQ-85663008@aQdSXq7ibn2j ajo3rv
# @req> REQ-18193596@oSjMcEZMnBK6 dt63ke
def build(args):
    _, root = corpus.load()
    ref = args.base or baseline._default_ref(root)
    # @req> REQ-92715984@izHQzbW23L0y 6l7fzx
    if ref is None:
        raise corpus.ReqctlError("no origin to compare against -- name one with --base")
    compared = cite.compare(root, ref)
    citations = {held["id"]: held for held in cite.read(root)[0]}
    texts = dict(cite._sources(root))
    reach, held = Reach(texts), records(root)
    folder = root / FOLDER
    if folder.is_dir():
        for earlier in sorted(folder.iterdir()):
            corpus.remove(earlier)
    for uid in compared["touches"]:
        text = prompt(root, uid, compared, citations, reach, texts)
        corpus.atomic_write(folder / f"{uid}.md", text)
        read = standing(held, text)
        print("\n".join(shown(uid, read) + ["    read before from an identical prompt"])
              if read else f"{uid}: reading needed -- {(FOLDER / uid).as_posix()}.md")
    if not compared["touches"]:
        print("No item was touched.")
    return 0


# @req> REQ-18882967@W34Ole45XgJE up776f
def returned(where):
    try:
        held = json.loads(where.read_text())
    except (OSError, ValueError):
        return None
    if not (isinstance(held, dict) and held.get("verdict") in VERDICTS
            and isinstance(held.get("lines"), list) and held["lines"]
            and all(isinstance(line, str) and line.strip() for line in held["lines"])):
        return None
    return {"verdict": held["verdict"], "lines": held["lines"]}


# @req> REQ-18882967@W34Ole45XgJE woxofe
def take(_):
    _, root = corpus.load()
    held, folder = records(root), root / FOLDER
    built = sorted(folder.glob("*.md")) if folder.is_dir() else []
    for where in built:
        uid, text = where.stem, corpus.read_text(where)
        read = standing(held, text) or returned(where.with_suffix(".json"))
        if read is None:
            print(f"{uid}: no verdict")
            continue
        held[corpus.digest(text)] = {"uid": uid, **read}
        print("\n".join(shown(uid, read)))
    if not built:
        print("No prompt was built.")
    corpus.atomic_write(root / RECORD, json.dumps(held, indent=1, sort_keys=True) + "\n")
    return 0


# @req> REQ-18193596@oSjMcEZMnBK6 rswytl
def main(argv=None):
    parsed = argparse.ArgumentParser()
    steps = parsed.add_subparsers(dest="step", required=True)
    steps.add_parser("build").add_argument("--base", metavar="REF")
    steps.add_parser("take")
    args = parsed.parse_args(argv)
    return {"build": build, "take": take}[args.step](args)


# @req> REQ-92715984@izHQzbW23L0y qwkkhk
if __name__ == "__main__":
    try:
        sys.exit(main())
    except (corpus.ReqctlError, OSError, UnicodeError) as unreadable:
        sys.exit(f"{Path(__file__).name}: " + " ".join(str(unreadable).split()))
