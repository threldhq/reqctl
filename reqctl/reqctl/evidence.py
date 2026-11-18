import json
from pathlib import Path

from . import cite
from . import graph
from . import validate
from .corpus import ReqctlError

GATES = ".reqctl/gates.json"
OUTCOMES = ("passed", "failed", "skipped")
PASSES = {True: "passes", False: "does not pass"}


def _step(held):
    return (isinstance(held, dict) and isinstance(held.get("name"), str)
            and held.get("outcome") in OUTCOMES
            and (held["outcome"] != "skipped" or isinstance(held.get("reason"), str)))


def gates(root):
    path = Path(root) / GATES
    # @req> REQ-74192068@wqaVZoxWF25v l7elak
    if not path.is_file():
        return None
    # @req+ REQ-96243908@PG2NeOENWp_B kdw2mt
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ReqctlError(f"{GATES} does not read as JSON: {error} -- run the "
                          "gates again, or delete the file") from error
    if not (isinstance(held, dict) and isinstance(held.get("commit"), str)
            and isinstance(held.get("steps"), list)
            and all(_step(step) for step in held["steps"])):
        raise ReqctlError(f"{GATES} does not state a commit and, of each step, a "
                          f"name, an outcome of {', '.join(OUTCOMES)} and the "
                          "reason for a skip -- run the gates again, or delete "
                          "the file")
    return {"commit": held["commit"],
            "steps": [{key: step[key] for key in ("name", "outcome", "reason")
                       if key in step} for step in held["steps"]]}
    # @req- kdw2mt


# @req> REQ-26348048@DZtMIa67gVG9 2a3l36
def read(tree, root, ref):
    compared = cite.compare(root, ref)
    touches = [{"uid": uid,
                "citations": [row for row in compared["citations"]
                              if row["uid"] == uid]}
               for uid in compared["touches"]]
    # @req> REQ-34657590@ZhBfEGE4gcUK smylog
    valid = not validate.run(root)
    # @req+ REQ-50410350@TUylyZq4Y6oY 53uvyo
    traced = graph.trace(tree, root, base=ref)
    traces = not (traced["problems"] or traced["stale"])
    # @req- 53uvyo
    # @req> REQ-26884656@F6FCcDIagP_f fv7sjv
    head = cite._git(root, "rev-parse", "HEAD").strip()
    return {"touches": touches, "validate": valid, "trace": traces,
            "head": head, "gates": gates(root)}


# @req> REQ-26348048@DZtMIa67gVG9 ktj6wc
def _touched(touches):
    if not touches:
        return ["No item was touched."]
    lines = []
    for touch in touches:
        lines.append(f"- {touch['uid']}")
        lines += [f"  - `{row['id']}` in `{row['path']}`: {', '.join(row['state'])}"
                  for row in touch["citations"]]
    return lines


# @req> REQ-96243908@PG2NeOENWp_B nqy2sa
def _stepped(step):
    said = f"- {step['name']}: {step['outcome']}"
    return f"{said} -- {step['reason']}" if step["outcome"] == "skipped" else said


def _gated(held, head):
    # @req> REQ-74192068@wqaVZoxWF25v wndpjk
    if held is None:
        return ["No gate results were given."]
    # @req> REQ-96243908@PG2NeOENWp_B clndxe
    lines = [f"Gate results of commit `{held['commit']}`."]
    # @req> REQ-26884656@F6FCcDIagP_f 2c7qev
    if held["commit"] != head:
        lines.append("These gate results are those of another commit: HEAD names "
                     f"`{head}`.")
    # @req> REQ-96243908@PG2NeOENWp_B hj6fnz
    return lines + [""] + [_stepped(step) for step in held["steps"]]


# @req> REQ-26348048@DZtMIa67gVG9 56k566
def block(data):
    lines = ["## Evidence", "", "### Items touched", "",
             *_touched(data["touches"]), "", "### Checks", ""]
    # @req> REQ-34657590@ZhBfEGE4gcUK msqtrb
    lines.append(f"- `reqctl validate`: {PASSES[data["validate"]]}")
    # @req> REQ-50410350@TUylyZq4Y6oY japrql
    lines.append(f"- `reqctl trace`: {PASSES[data["trace"]]}")
    lines += ["", "### Gate steps", "", *_gated(data["gates"], data["head"])]
    return "\n".join(lines)
