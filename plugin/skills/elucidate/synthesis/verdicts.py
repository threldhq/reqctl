#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan
import shapes

from reqctl import corpus


def cited(data, stated):
    # @req+ REQ-62710822@voiCNXQxSuF9 adhfwh
    found = []
    for field, key in shapes.CITING.items():
        for entry in data.get(field) or []:
            names = entry[key] if isinstance(entry[key], list) else [entry[key]]
            for name in names:
                if name not in stated:
                    found.append(f"{field} cites {name}, which the prompt did "
                                 "not state")
    return found
    # @req- adhfwh


def judged(run, state_held):
    accepted, failed, absent = [], [], []
    for number, spec in sorted(state_held["judge"].items(),
                               key=lambda pair: int(pair[0])):
        folder = "final" if spec["groups"] else "judge"
        path = run / "returns" / folder / f"{number}.json"
        data, why = plan.read_return(path, shapes.JUDGE)
        # @req> REQ-46162234@7Wvh6guc-Moy fmxygz
        if data is None:
            (absent if why == "returned nothing" else failed).append(
                (number, [why]))
            continue
        # @req+ REQ-62710822@voiCNXQxSuF9 v3dukx
        faults = ([f"answers proposal {data['proposal']}, not {number}"]
                  if str(data["proposal"]) != number else [])
        faults += cited(data, set(state_held["named"][number]))
        if faults:
            failed.append((number, faults))
            continue
        # @req- v3dukx
        corpus.atomic_write(run / "verdicts" / f"{number}.json",
                            json.dumps(data, indent=1) + "\n")
        accepted.append((number, data))
    return accepted, failed, absent


def grouped(accepted):
    # @req+ REQ-91823330@YBrjy3XTcDS0 7xe5ny
    held = {}
    for number, data in accepted:
        for field, key in shapes.CITING.items():
            for entry in data.get(field) or []:
                names = (entry[key] if isinstance(entry[key], list)
                         else [entry[key]])
                for name in names:
                    held.setdefault((field, name), []).append(
                        (number, entry.get("reason") or entry.get("why_not")
                         or ""))
    return held
    # @req- 7xe5ny


def report(accepted, failed, absent):
    # @req> REQ-55679883@RYeaIjP7qP3t u37uos
    lines = [(f"{len(accepted)} accepted, {len(failed)} failed, "
              f"{len(absent)} never returned")]
    # @req+ REQ-82676674@FK_7la2Hg_XC hbpale
    for number, why in absent:
        lines.append(f"  no verdict: proposal {number}")
    for number, faults in failed:
        lines.append(f"  proposal {number}: spawn its judge again")
        lines += [f"    {fault}" for fault in faults]
    # @req- hbpale
    # @req+ REQ-91823330@YBrjy3XTcDS0 ih4cxu
    held = grouped(accepted)
    if held:
        lines += ["", "findings, by what they name"]
        for (field, name), entries in sorted(held.items()):
            lines.append(f"  {name}  ({field}, {len(entries)} proposal(s))")
            lines += [f"    proposal {number}: {reason}"
                      for number, reason in entries]
    # @req- ih4cxu
    # @req> REQ-90450530@3hD9gxWAaXt4 v3dvwn
    for number, data in accepted:
        for field in ("values", "words", "faults", "questions"):
            for entry in data.get(field) or []:
                lines.append(f"  proposal {number} {field}: "
                             + (entry if isinstance(entry, str)
                                else json.dumps(entry)))
    return "\n".join(lines)


def respawn(run, state_held, numbers):
    spawned = []
    for number in numbers:
        folder = "final" if state_held["judge"][number]["groups"] else "judge"
        spawned.append(plan.spawn(run, folder, number, f"{folder}:{number}",
                                  shapes.JUDGE, state_held["models"]["judge"],
                                  plan.PHASES["judge"]))
        (run / "returns" / folder / f"{number}.json").unlink(missing_ok=True)
    return plan.manifest(run, "judge", spawned)


def main(argv=None):
    parsed = argparse.ArgumentParser()
    parsed.add_argument("--run", required=True, metavar="DIR")
    args = parsed.parse_args(argv)
    run = Path(args.run)
    state_held = plan.state(run)
    # @req> REQ-32019340@Ce9zMv1R_f5m 7v53qm
    if not state_held["judge"]:
        raise SystemExit("no judge prompt was built; run `plan.py judge` first")
    accepted, failed, absent = judged(run, state_held)
    print(report(accepted, failed, absent))
    # @req> REQ-82676674@FK_7la2Hg_XC zeg5gl
    if failed or absent:
        print(f"{len(failed) + len(absent)} judge(s) to spawn again: "
              f"{respawn(run, state_held, [n for n, _ in failed + absent])}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (corpus.ReqctlError, OSError) as unreadable:
        sys.exit(f"{Path(__file__).name}: {unreadable}")
