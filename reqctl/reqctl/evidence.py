import json
import os

from . import cite
from . import graph
from . import validate
from .corpus import ReqctlError

GATES = ".reqctl/gates.json"
# @req> gate_step_outcomes@LMCYqqlETeXS 4ahnpu
OUTCOMES = ("passed", "failed", "skipped")
PASSES = {True: "passes", False: "does not pass"}


def _step(held):
    return (isinstance(held, dict) and isinstance(held.get("name"), str)
            and held.get("outcome") in OUTCOMES
            and (held["outcome"] != "skipped" or isinstance(held.get("reason"), str)))


def gates(root):
    # @req> REQ-83330302@kWkBOJuy81la tcygas
    path = root / GATES
    # @req> REQ-74192068@wqaVZoxWF25v l7elak
    if not os.path.lexists(path):
        return None
    # @req+ REQ-96243908@_JWPW5ZdbY9b kdw2mt
    # @req+ REQ-96699115@zhnZnL6or8Cz 5t5s4n
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        # @req> REQ-30898926@Vu28eWaG_1mE awigjw
        # @req> REQ-65393615@LeFXBgH9P-29 b4sowa
        raise ReqctlError(f"{GATES} does not read as JSON: {error} -- run the "
                          "gates again, or delete the file") from error
    if not (isinstance(held, dict) and isinstance(held.get("commit"), str)
            and isinstance(held.get("steps"), list)
            and all(_step(step) for step in held["steps"])):
        # @req> REQ-30898926@Vu28eWaG_1mE ert3gh
        # @req> REQ-65393615@LeFXBgH9P-29 5r7v6a
        raise ReqctlError(f"{GATES} does not state a commit and, of each step, a "
                          f"name, an outcome of {', '.join(OUTCOMES)} and the "
                          "reason for a skip -- run the gates again, or delete "
                          "the file")
    return {"commit": held["commit"],
            "steps": [{key: step[key] for key in ("name", "outcome", "reason")
                       if key in step} for step in held["steps"]]}
    # @req- 5t5s4n
    # @req- kdw2mt


# @req> REQ-26348048@aTcCvMjFCdmR 2a3l36
def read(tree, root, ref):
    compared = cite.compare(root, ref)
    touches = [{"uid": uid,
                "citations": [row for row in compared["citations"]
                              if row["uid"] == uid],
                "files": [row for row in compared["files"] if row["uid"] == uid]}
               for uid in compared["touches"]]
    # @req> REQ-34657590@ZhBfEGE4gcUK smylog
    valid = not validate.run(root)
    # @req+ REQ-50410350@TUylyZq4Y6oY 53uvyo
    traced = graph.trace(tree, root, base=ref)
    traces = not (traced["problems"] or traced["stale"])
    # @req- 53uvyo
    # @req> REQ-26884656@F6FCcDIagP_f fv7sjv
    head = cite._git(root, "rev-parse", "HEAD").strip()
    # @req> REQ-29385748@NsfOmiGdMQm0 ght24q
    uncommitted = bool(cite._git(root, "status", "--porcelain",
                                 "--untracked-files=no").strip())
    # @req> REQ-83330302@kWkBOJuy81la p6vr64
    held = gates(root)
    return {"touches": touches, "validate": valid, "trace": traces,
            "head": head, "uncommitted": uncommitted, "gates": held}


# @req> REQ-26348048@aTcCvMjFCdmR ktj6wc
def _touched(touches):
    if not touches:
        return ["No item was touched."]
    lines = []
    for touch in touches:
        lines.append(f"- {touch['uid']}")
        lines += [f"  - `{row['id']}` in `{row['path']}`: {', '.join(row['state'])}"
                  for row in touch["citations"]]
        lines += [f"  - whole file `{row['path']}`: {', '.join(row['state'])}"
                  for row in touch["files"]]
    return lines


# @req> REQ-96243908@_JWPW5ZdbY9b nqy2sa
def _stepped(step):
    said = f"- {step['name']}: {step['outcome']}"
    return f"{said} -- {step['reason']}" if step["outcome"] == "skipped" else said


def _gated(held, head):
    # @req> REQ-74192068@wqaVZoxWF25v wndpjk
    if held is None:
        return ["No gate results were given."]
    # @req> REQ-96243908@_JWPW5ZdbY9b clndxe
    lines = [f"Gate results of commit `{held['commit']}`."]
    # @req> REQ-26884656@F6FCcDIagP_f 2c7qev
    if held["commit"] != head:
        lines.append("These gate results are those of another commit: HEAD names "
                     f"`{head}`.")
    # @req> REQ-96243908@_JWPW5ZdbY9b hj6fnz
    return lines + [""] + [_stepped(step) for step in held["steps"]]


# @req> REQ-29385748@NsfOmiGdMQm0 oglnda
def _uncommitted(stated):
    return ["Tracked files have uncommitted changes.", ""] if stated else []


# @req> REQ-26348048@aTcCvMjFCdmR 56k566
def block(data):
    lines = ["## Evidence", "", *_uncommitted(data["uncommitted"]),
             "### Items touched", "",
             *_touched(data["touches"]), "", "### Checks", ""]
    # @req> REQ-34657590@ZhBfEGE4gcUK msqtrb
    lines.append(f"- `reqctl validate`: {PASSES[data["validate"]]}")
    # @req> REQ-50410350@TUylyZq4Y6oY japrql
    lines.append(f"- `reqctl trace`: {PASSES[data["trace"]]}")
    lines += ["", "### Gate steps", "", *_gated(data["gates"], data["head"])]
    return "\n".join(lines)
