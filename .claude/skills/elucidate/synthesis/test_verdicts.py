#!/usr/bin/env python3
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan
import shapes
import verdicts

faults = []


def check(name, held, wanted):
    if held != wanted:
        faults.append(f"{name}: expected {wanted!r}, got {held!r}")


def truthy(name, held):
    if not held:
        faults.append(f"{name}: expected something true, got {held!r}")


def verdict(number, **fields):
    held = {"proposal": number, "covered_by": [], "conflicts": [], "relations": [],
            "nearest": [], "values": [], "words": [], "faults": [], "questions": []}
    held.update(fields)
    return held


STATE = {
    "proposals": {"1": {"kind": "REQ", "statement": "The product shall a."},
                  "2": {"kind": "REQ", "statement": "The product shall b."}},
    "judge": {"1": {"groups": None}, "2": {"groups": [["REQ-10000001"], ["REQ-10000002"]]}},
    "named": {"1": {"REQ-10000001": ["same: c"], "proposal 2": ["overlaps: d"]},
              "2": {"REQ-10000001": [], "REQ-10000002": []}},
    "models": {"recall": "sonnet", "judge": "opus"},
}

check("a citation of an item the prompt did not state is a fault naming the field and the item",
      verdicts.cited(verdict(1, conflicts=[{"uid": "REQ-77777777", "reason": "r"}],
                             covered_by=[{"uids": ["REQ-10000001", "proposal 2"],
                                          "covers": "part", "reason": "r"}]),
                     {"REQ-10000001", "proposal 2"}),
      ["conflicts cites REQ-77777777, which the prompt did not state"])


def written(run, folder, number, data):
    (run / "returns" / folder).mkdir(parents=True, exist_ok=True)
    (run / "returns" / folder / f"{number}.json").write_text(
        data if isinstance(data, str) else json.dumps(data))


with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    (run / "verdicts").mkdir()
    written(run, "judge", 1, verdict(1, covered_by=[
        {"uids": ["REQ-10000001"], "covers": "whole", "reason": "restates it"}]))
    written(run, "final", 2, verdict(2, relations=[
        {"target": "REQ-10000002", "kind": "derives_from", "reason": "narrower"}]))
    accepted, failed, absent = verdicts.judged(run, json.loads(json.dumps(STATE)))
    check("a single judge's return and a final judge's return are each read from their folder",
          ([number for number, _ in accepted], failed, absent), (["1", "2"], [], []))
    truthy("and an accepted verdict is written under the proposal's number",
           (run / "verdicts" / "1.json").is_file() and (run / "verdicts" / "2.json").is_file())
    report = verdicts.report(accepted, failed, absent)
    truthy("the report groups findings by what they name, with the reason",
           "REQ-10000001  (covered_by, 1 proposal(s))" in report
           and "proposal 1: restates it" in report
           and "REQ-10000002  (relations, 1 proposal(s))" in report)

    written(run, "judge", 1, verdict(1, conflicts=[{"uid": "REQ-99999999", "reason": "r"}]))
    written(run, "final", 2, verdict(3))
    (run / "verdicts" / "1.json").unlink()
    accepted, failed, absent = verdicts.judged(run, json.loads(json.dumps(STATE)))
    check("a verdict citing an unstated item, and one answering another proposal, fail",
          ([number for number, _ in failed], accepted, absent),
          (["1", "2"], [], []))
    truthy("and each fault says what it found",
           "conflicts cites REQ-99999999, which the prompt did not state" in failed[0][1]
           and "answers proposal 3, not 2" in failed[1][1])
    truthy("and no verdict is written for either",
           not (run / "verdicts" / "1.json").exists())

    (run / "returns" / "judge" / "1.json").unlink()
    written(run, "final", 2, "{not json")
    accepted, failed, absent = verdicts.judged(run, json.loads(json.dumps(STATE)))
    check("an absent return is reported as never returned, and a broken one as failed",
          ([number for number, _ in absent], [number for number, _ in failed]),
          (["1"], ["2"]))
    (run / "prompts" / "judge").mkdir(parents=True)
    (run / "workflow").mkdir()
    where = verdicts.respawn(run, STATE, ["1", "2"])
    written = json.loads(where.read_text())
    check("the judges to spawn again are named with their folder, the judge's model "
          "and the judge shape stated once",
          ([(one["label"], one["model"], one["schema"]) for one in written["prompts"]],
           list(written["shapes"].values())),
          ([("judge:1", "opus", "shape-1"), ("final:2", "opus", "shape-1")],
           [shapes.JUDGE]))
    truthy("and their stale returns are retired",
           not (run / "returns" / "final" / "2.json").exists())

    (run / plan.STATE).write_text(json.dumps(STATE))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = verdicts.main(["--run", str(run)])
    check("main exits 1 while a judge is owed", code, 1)
    truthy("and says how many to spawn again", "2 judge(s) to spawn again" in out.getvalue())

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("verdict check self-test: 0 fault(s)")
sys.exit(0)
