import json
import re
import subprocess
from pathlib import Path

from . import cite, corpus, graph, validate
from .reach import Reach

# @req> reading_verdicts@HpeJsZ_Iw3sd 6k34lr
VERDICTS: dict[str, dict] = {"satisfied": {}, "not_satisfied": {}, "cannot_tell": {}}
# @req> REQ-18193596@I26mta6oEsfZ pbcpee
OWN = re.compile(r"(text|acceptance criteria|value|entries)\s{2,}")
# @req> REQ-18193596@I26mta6oEsfZ vibeld
NAMED = ("parameters", "concepts")
FOLDER = Path(".reqctl") / "readings"
RECORD = Path(".reqctl") / "readings.json"
PASS = Path(".reqctl") / "pass.json"


# @req> REQ-18193596@I26mta6oEsfZ ctq62o
def printed(uid):
    try:
        done = subprocess.run(["reqctl", "context", uid], capture_output=True,
                              text=True, check=False)
    except OSError as absent:
        # @req> REQ-92715984@izHQzbW23L0y itq5hu
        raise corpus.ReqctlError(f"cannot run reqctl: {absent.strerror} -- install "
                                 "reqctl or put it on PATH") from absent
    if done.returncode:
        # @req> REQ-92715984@izHQzbW23L0y tk2onc
        raise corpus.ReqctlError(done.stderr.strip()
                                 or f"reqctl context {uid} exited {done.returncode}")
    return done.stdout


# @req> REQ-18193596@I26mta6oEsfZ iiyl4x
def stated(uid):
    head, *blocks = printed(uid).split("\n\n")
    lines = [line for line in head.split("\n") if OWN.match(line)]
    if not lines:
        # @req> REQ-92715984@izHQzbW23L0y p2ylmq
        raise corpus.ReqctlError(f"reqctl context {uid} printed no text, acceptance "
                                 "criteria, value or entries -- install the reqctl "
                                 "release this plugin ships with")
    for block in blocks:
        title, _, body = block.strip("\n").partition("\n")
        if title in NAMED and body:
            lines += ["", title, body]
    return lines


# @req> REQ-18193596@I26mta6oEsfZ tkgt6p
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


# @req> REQ-18193596@I26mta6oEsfZ wr2xfv
def code(root, uid, files, citations, reach, texts):
    lines = []
    for path, numbers in sorted(taken(uid, citations, reach).items()):
        if texts.get(path) is None:
            # @req> REQ-92715984@izHQzbW23L0y vdqdoy
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


# @req> REQ-18193596@I26mta6oEsfZ 3qt2h3
# @req> REQ-18762283@KHBhiDTwKW9T p3h6ie
# @req> REQ-13632010@magDohgvXtNz mkchz3
def prompt(root, uid, files, citations, reach, texts):
    held = code(root, uid, files, citations, reach, texts)
    mark = corpus.digest("\n".join(held))
    return "\n".join([
        f"ITEM {uid}", *stated(uid), "", f"CODE STARTS {mark}", *held,
        f"CODE ENDS {mark}", "", "RETURN",
        (f"Write your reply to {(FOLDER / uid).as_posix()}.json, in the shape "
         f"your definition states, with verdict one of {', '.join(VERDICTS)}."),
        ""])


# @req> REQ-85663008@z5Y4x8rasoxc feayaa
def records(root):
    where = root / RECORD
    if not where.exists():
        return {}
    try:
        held = json.loads(corpus.read_text(where))
    except ValueError as broken:
        # @req> REQ-92715984@izHQzbW23L0y bowzly
        raise corpus.ReqctlError(f"{RECORD.as_posix()} does not read as JSON: "
                                 f"{broken} -- delete the file") from broken
    if not isinstance(held, dict):
        # @req> REQ-92715984@izHQzbW23L0y obtuoc
        raise corpus.ReqctlError(f"{RECORD.as_posix()} is not a JSON object "
                                 "-- delete the file")
    return held


# @req> REQ-85663008@z5Y4x8rasoxc uuafux
def standing(root, held, text):
    was = held.get(corpus.digest(text))
    read = sound(was, text)
    if read and read["verdict"] == "satisfied":
        return read
    found = was.get("searching") if isinstance(was, dict) else None
    if (isinstance(found, dict) and found.get("verdict") == "satisfied"
            and unchanged(root, found.get("files"))):
        return found
    return None


# @req> REQ-18418155@kQKuNMnvZhlx o753d5
def digested(root, name):
    try:
        place, top = (root / name).resolve(), root.resolve()
        if (not place.is_relative_to(top) or place.is_relative_to(top / FOLDER.parent)
                or place.is_relative_to(corpus.folder_for(top, "requirement").parent)):
            return None, None
        text = corpus.read_text(place)
    except (corpus.ReqctlError, OSError, ValueError):
        return None, None
    return text, corpus.digest(text)


def unchanged(root, files):
    return isinstance(files, dict) and all(
        was and digested(root, name)[1] == was for name, was in files.items())


# @req> REQ-85663008@z5Y4x8rasoxc rb3uzl
def kept(root, held, text):
    was = held.get(corpus.digest(text))
    return accepted(was) and unchanged(root, was.get("files", {}))


# @req> REQ-18882967@W34Ole45XgJE vlryx4
# @req> REQ-12678136@0uDF0n6a2v1j aezlzi
# @req> REQ-27227735@7V5PywZWMbkg w6tflb
def sound(held, text):
    said = {line.strip() for line in text.split("\n")}
    if not (isinstance(held, dict) and isinstance(held.get("verdict"), str)
            and held["verdict"] in VERDICTS
            and isinstance(held.get("lines"), list) and held["lines"]
            and all(isinstance(line, str) and line.strip() in said - {""}
                    for line in held["lines"])
            and (issue := at_issue(held)) is not None):
        return None
    return {"verdict": held["verdict"], "lines": held["lines"], **issue}


def at_issue(reply):
    if reply["verdict"] == "satisfied":
        return {}
    said = reply.get("issue")
    if not isinstance(said, str) or not said.strip() or "\n" in said.strip():
        return None
    return {"issue": said.strip()}


# @req> REQ-42425794@haYtnGYRwgcG 2sqtfv
def accepted(was):
    if not (isinstance(was, dict) and was.get("accepted") is True):
        return {}
    return {key: was[key] for key in ("accepted", "reason", "files") if key in was}


def prompts(store, root, ref):
    compared = cite.compare(root, ref)
    citations = {held["id"]: held for held in cite.read(root)[0]}
    texts = dict(cite._sources(root))
    reach = Reach(texts)
    return {uid: prompt(root, uid,
                        corpus.mapping(corpus.find(store, uid).data, corpus.WHOLE_FILES),
                        citations, reach, texts)
            for uid in compared["touches"]}


# @req> REQ-30077988@Ugzat0welz0c 7rvm24
def unsettled(store, root, ref):
    held = records(root)
    for uid, text in prompts(store, root, ref).items():
        if standing(root, held, text) or kept(root, held, text):
            continue
        read = sound(held.get(corpus.digest(text)), text)
        yield (f"{uid}: {read['verdict'].replace('_', ' ') if read else 'no verdict'}, "
               "and no acceptance by the owner that counts -- run the pre-pr pass's "
               "reading of it, or record the owner's acceptance")


# @req> REQ-23123938@pNzjD3R4wwAe g3ymgd
# @req> REQ-30077988@Ugzat0welz0c uowvyt
def record(store, root, ref):
    traced = graph.trace(store, root, base=ref)
    faults = [f"reqctl {name} reports a problem -- run it and fix what it names"
              for name, failed in (("validate", validate.run(root)),
                                   ("trace", traced["problems"] or traced["stale"]))
              if failed]
    faults += unsettled(store, root, ref)
    if faults:
        raise corpus.ReqctlError("no pass record is written:\n" + "\n".join(faults))
    head = cite._git(root, "rev-parse", "HEAD").strip()
    corpus.atomic_write(root / PASS, json.dumps({"commit": head}) + "\n")
    return head
