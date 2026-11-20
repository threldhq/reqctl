#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from reqctl.reach import Reach

from reqctl import baseline, cite, corpus

# @req> reading_verdicts@wJS-OszXMr_Q 3qo4wm
VERDICTS: dict[str, dict] = {"satisfied": {}, "not_satisfied": {}, "cannot_tell": {}}
# @req> REQ-18193596@I26mta6oEsfZ 6rm73a
OWN = re.compile(r"(text|acceptance criteria|value|entries)\s{2,}")
# @req> REQ-18193596@I26mta6oEsfZ 4zf45f
NAMED = ("parameters", "concepts")
FOLDER = Path(".reqctl") / "readings"
RECORD = Path(".reqctl") / "readings.json"
# @req> pre_pr_agents.reading@O0Qk99QMNGY1 rvwyy7
SPAWNED = {"model": "claude-sonnet-5-5", "effort": "high"}
# @req+ REQ-17125120@feot1-3cXxVn km2e6r
FITS = 524288
SCRIPT = """export const meta = {
  name: 'reading',
  description: 'Spawn one reading agent per prompt the build wrote',
  phases: [{ title: 'Read', detail: 'one reading agent per item, in parallel' }],
}
const readings = [
%s
]
const results = await parallel(readings.map(one => () =>
  agent(one.prompt, { label: one.label, phase: 'Read', model: one.model, effort: one.effort, agentType: one.agentType })))
return {
  spawned: readings.length,
  failed: readings.filter((one, at) => !results[at]).map(one => one.label),
}
"""
# @req- km2e6r


# @req> REQ-18193596@I26mta6oEsfZ lcqfuw
def printed(uid):
    try:
        done = subprocess.run(["reqctl", "context", uid], capture_output=True,
                              text=True, check=False)
    except OSError as absent:
        # @req> REQ-92715984@izHQzbW23L0y tp44ab
        raise corpus.ReqctlError(f"cannot run reqctl: {absent.strerror} -- install "
                                 "reqctl or put it on PATH") from absent
    if done.returncode:
        # @req> REQ-92715984@izHQzbW23L0y rkatxd
        raise corpus.ReqctlError(done.stderr.strip()
                                 or f"reqctl context {uid} exited {done.returncode}")
    return done.stdout


# @req> REQ-18193596@I26mta6oEsfZ v5do75
def stated(uid):
    head, *blocks = printed(uid).split("\n\n")
    lines = [line for line in head.split("\n") if OWN.match(line)]
    if not lines:
        # @req> REQ-92715984@izHQzbW23L0y 4kxswd
        raise corpus.ReqctlError(f"reqctl context {uid} printed no text, acceptance "
                                 "criteria, value or entries -- install the reqctl "
                                 "release this plugin ships with")
    for block in blocks:
        title, _, body = block.strip("\n").partition("\n")
        if title in NAMED and body:
            lines += ["", title, body]
    return lines


# @req> REQ-18193596@I26mta6oEsfZ x2ryeq
def taken(uid, citations, reach):
    wanted = {}
    for held in citations.values():
        if held["uid"] != uid:
            continue
        wanted.setdefault(held["path"], set()).update(held["lines"])
        for path, line in reach.reached(held["path"], held["lines"]):
            wanted.setdefault(path, set()).add(line)
    marks = {(held["path"], line) for held in citations.values()
             for line in held["marks"]}
    return {path: sorted(line for line in lines if (path, line) not in marks)
            for path, lines in wanted.items()}


# @req> REQ-18193596@I26mta6oEsfZ su5ahl
def code(root, uid, files, citations, reach, texts):
    lines = []
    for path, numbers in sorted(taken(uid, citations, reach).items()):
        if texts.get(path) is None:
            # @req> REQ-92715984@izHQzbW23L0y 44kmga
            raise corpus.ReqctlError(f"cannot read {path}, which a citation of {uid} "
                                     "takes in -- make the file readable as UTF-8")
        said = texts[path].split("\n")
        lines += ["", f"=== {path} ==="]
        for at, number in enumerate(numbers):
            if at and number != numbers[at - 1] + 1:
                lines.append("-----")
            lines.append(said[number - 1])
    for path in sorted(files):
        if (root / path).is_file():
            lines += ["", f"=== {path} ===", corpus.read_text(root / path).rstrip("\n")]
    return lines


# @req> REQ-18193596@I26mta6oEsfZ xdxo6t
# @req> REQ-18762283@KHBhiDTwKW9T plidzn
def prompt(root, uid, files, citations, reach, texts):
    return "\n".join([
        f"ITEM {uid}", *stated(uid), "", "CODE",
        *code(root, uid, files, citations, reach, texts), "", "RETURN",
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
    read = sound(held.get(corpus.digest(text)), text)
    return read if read and read["verdict"] == "satisfied" else None


# @req> REQ-18882967@W34Ole45XgJE 7xdgt7
def shown(uid, read):
    return [f"{uid}: {read['verdict']}", *(f"    {line}" for line in read["lines"])]


# @req> REQ-99520421@EA982CV9V8L5 veennf
def registered(name):
    plugin = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
    if not plugin.is_file():
        return name
    try:
        return f"{json.loads(corpus.read_text(plugin))['name']}:{name}"
    except (ValueError, KeyError, TypeError) as broken:
        # @req> REQ-92715984@izHQzbW23L0y ih4xig
        raise corpus.ReqctlError(f"{plugin} states no plugin name: {broken!r} "
                                 "-- install the plugin again") from broken


# @req> REQ-17125120@feot1-3cXxVn 6ravfp
def workflows(needed, agent):
    room, packs, held = FITS - len(SCRIPT % ""), [], 0
    for uid, text in needed.items():
        entry = json.dumps({"label": uid, "prompt": text, **SPAWNED,
                            "agentType": agent})
        size = len(entry) + len(",\n")
        if size > room:
            # @req> REQ-92715984@izHQzbW23L0y ckixes
            raise corpus.ReqctlError(
                f"the prompt of {uid} takes {size} bytes of a reading workflow, "
                f"which holds {room} -- cite {uid} over less code")
        if not packs or held + size > room:
            packs.append([])
            held = 0
        packs[-1].append(entry)
        held += size
    return [SCRIPT % ",\n".join(pack) for pack in packs]


# @req> REQ-85663008@aQdSXq7ibn2j ajo3rv
# @req> REQ-18193596@I26mta6oEsfZ dt63ke
def build(args):
    store, root = corpus.load()
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
    built = {uid: prompt(root, uid,
                         corpus.mapping(corpus.find(store, uid).data, corpus.WHOLE_FILES),
                         citations, reach, texts)
             for uid in compared["touches"]}
    needed = {}
    for uid, text in built.items():
        corpus.atomic_write(folder / f"{uid}.md", text)
        read = standing(held, text)
        if not read:
            needed[uid] = text
        print("\n".join(shown(uid, read) + ["    read before from an identical prompt"])
              if read else f"{uid}: reading needed -- {(FOLDER / uid).as_posix()}.md")
    # @req> REQ-17125120@feot1-3cXxVn v7riys
    # @req> REQ-99520421@EA982CV9V8L5 faw5sx
    for at, script in enumerate(workflows(needed, registered("reading")), 1):
        corpus.atomic_write(folder / f"workflow-{at}.js", script)
        print(f"reading workflow: {(folder / f'workflow-{at}.js').as_posix()}")
    if not compared["touches"]:
        print("No item was touched.")
    return 0


# @req> REQ-18882967@W34Ole45XgJE up776f
def sound(held, text):
    said = {line.strip() for line in text.split("\n")}
    if not (isinstance(held, dict) and isinstance(held.get("verdict"), str)
            and held["verdict"] in VERDICTS
            and isinstance(held.get("lines"), list) and held["lines"]
            and all(isinstance(line, str) and line.strip() in said - {""}
                    for line in held["lines"])):
        return None
    return {"verdict": held["verdict"], "lines": held["lines"]}


# @req> REQ-18882967@W34Ole45XgJE w3h7qz
def returned(where, text):
    if not where.exists():
        return None
    try:
        return sound(json.loads(corpus.read_text(where)), text)
    except ValueError:
        return None


# @req> REQ-18882967@W34Ole45XgJE woxofe
def take(_):
    _, root = corpus.load()
    held, folder = records(root), root / FOLDER
    built = sorted(folder.glob("*.md")) if folder.is_dir() else []
    for where in built:
        uid, text = where.stem, corpus.read_text(where)
        read = standing(held, text) or returned(where.with_suffix(".json"), text)
        if read is None:
            print(f"{uid}: no verdict")
            continue
        held[corpus.digest(text)] = {"uid": uid, **read}
        print("\n".join(shown(uid, read)))
    if not built:
        print("No prompt was built.")
    corpus.atomic_write(root / RECORD, json.dumps(held, indent=1, sort_keys=True) + "\n")
    return 0


# @req> REQ-18193596@I26mta6oEsfZ rswytl
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
