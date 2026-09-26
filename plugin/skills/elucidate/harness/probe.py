#!/usr/bin/env python3
import argparse
import json
import random
import sys
from pathlib import Path

import yaml

from reqctl import corpus, validate

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "synthesis"))
import plan
import shapes

# @req> REQ-91336482@TiPdPxI_xFIm 6gegy3
LIMITATION = """This is a regression guard, not a quality score.

Every probe is a near-verbatim restatement of an approved requirement: its term
links are the source's own and only its parameter references are written out as
the values they hold, because the lint the build runs demands the links and
nothing here can paraphrase deterministically. A probe is its source with the
numbers filled in. That is the easy end of the task. A probe measures whether
the agents still find what they already found -- not whether they find what is
hard: coverage that is partial, a conflict stated in other units, an obligation
nobody asked for.

Recall is read from what this run's own recall pass returned and what the judge
prompt then carried, not from a ranking of this harness's own. A source recall
never reached that the judge prompt still named is the floor carrying the run
rather than the reading. Nothing here says how much of the corpus a reading had
to admit to reach anything: the sweep over cuts that measured that is gone with
the ranking it swept.

The key states what the corpus declares, not everything a correct verdict may
name, so a citation outside the key is counted and never penalised.

A sibling pair is the floor of what Pass B exists to catch, not its measure: one
statement beside its own verbatim restatement, and one beside the neighbour the
corpus already says it leans on. Both are labelled by the corpus rather than
paraphrased, so a pass that misses them has not failed at something hard.

Neighbours found is a floor, not a rate. A probe is its source with the numbers
filled in, so an agent holding the source finds a whole duplicate -- and the
shape has it wire no relation for one. Only an agent whose set holds a neighbour
without the source can cite that neighbour, so a neighbour the run
never had a way to reach counts against the figure exactly as a real miss does.
Read a rise as a rise and a fall as worth investigating; do not read the ratio
itself.

A green run says nothing has regressed. It does not say the skill is accurate."""

INJECTED = {
    "compound": " and record the change",
    "foreign_id": ", as required by BD-CAP-001",
}


def _literal(records, address):
    uid, rest = corpus.split_address(address)
    held = records.get(uid) or {}
    entries = corpus.entries(held) or {}
    unit = held.get("unit")

    def shown(member):
        return f"{member} {unit}" if unit else str(member)

    if rest == "default":
        member = held.get("default")
    elif rest:
        member = rest.split(".")[0]
    elif corpus.kind_of(uid, held) == "parameter" and len(entries) == 1:
        member = next(iter(entries))
    else:
        member = None
    if member is not None:
        return shown(member)
    if corpus.kind_of(uid, held) == "parameter" and entries:
        return ", ".join(shown(key) for key in entries)
    return str(held.get("name") or uid)


def statement(records, data):
    text = corpus.PARAM_REF.sub(
        lambda found: _literal(records, found.group(1) + found.group(2)),
        str(data.get("text") or ""))
    return " ".join(text.split())


def paired(records, reqs, draw, taken, wanted, start):
    sources = [uid for uid in sorted(set(reqs) - taken)
               if neighbours(records, reqs[uid])]
    held, number = [], start
    for at, uid in enumerate(draw.sample(sources, min(wanted, len(sources)))):
        said = statement(records, reqs[uid])
        other = neighbours(records, reqs[uid])[0] if at % 2 else uid
        held += [
            {"proposal": number, "kind": "sibling",
             "link": "neighbour" if at % 2 else "duplicate", "source": uid,
             "statement": said, "expects": number + 1},
            {"proposal": number + 1, "kind": "sibling",
             "link": "neighbour" if at % 2 else "duplicate", "source": other,
             "statement": statement(records, reqs[other]) if at % 2 else said,
             "expects": number},
        ]
        number += 2
    return held


def neighbours(records, data):
    # @req> REQ-20722175@BniiLBiwu3XL rgpt75
    return sorted(
        target
        for target, relation in corpus.mapping(data, "relations").items()
        if relation in validate.LEANS_ON and target.startswith("REQ-")
        and (records.get(target) or {}).get("status") == "approved"
    )


def injected(text, fault):
    return text.rstrip().rstrip(".") + INJECTED[fault] + "."


def build(records, count, faults, seed, pairs=2):
    # @req> REQ-23706540@e-JqhR3Ui-ke g5zodz
    reqs = {uid: data for uid, data in records.items()
            if uid.startswith("REQ-") and data.get("status") == "approved"}
    # @req+ REQ-27446623@DvVquw4gXGWi 3xjgfd
    with_neighbours = sorted(uid for uid, data in reqs.items()
                             if neighbours(records, data))
    if not with_neighbours:
        raise SystemExit("no approved requirement declares a neighbour to probe")
    # @req- 3xjgfd
    draw = random.Random(seed)
    chosen = draw.sample(with_neighbours, min(count, len(with_neighbours)))

    probes = []
    for number, uid in enumerate(chosen, start=1):
        probes.append({
            "proposal": number,
            "kind": "duplicate",
            "source": uid,
            "statement": statement(records, reqs[uid]),
            "self": uid,
            "neighbours": neighbours(records, reqs[uid]),
        })

    names = sorted(INJECTED)
    spare = draw.sample(sorted(set(reqs) - set(chosen)),
                        min(faults, len(reqs) - len(chosen)))
    for offset, uid in enumerate(spare):
        fault = names[offset % len(names)]
        probes.append({
            "proposal": len(chosen) + offset + 1,
            "kind": "fault",
            "source": uid,
            "statement": injected(statement(records, reqs[uid]), fault),
            "fault": fault,
        })

    probes += paired(records, reqs, draw, set(chosen) | set(spare), pairs,
                     len(probes) + 1)

    return {
        "limitation": LIMITATION,
        "seed": seed,
        "corpus": {"items": len(records), "approved_requirements": len(reqs)},
        "probes": probes,
    }


def _named(verdict):
    found = set()
    for entry in verdict.get("covered_by") or []:
        found |= {str(uid) for uid in entry.get("uids") or []}
    for field, key in (("conflicts", "uid"), ("relations", "target"),
                       ("values", "belongs_with"), ("words", "defined_by")):
        for entry in verdict.get(field) or []:
            found.add(str(entry.get(key)))
    return found


def cited(verdict):
    return {corpus.split_address(name)[0] for name in _named(verdict)
            if corpus.ADDRESS.match(name)}


def cited_siblings(verdict):
    return {name for name in _named(verdict) if name.startswith("proposal ")}


def returned(run, key):
    held, absent = {}, []
    for probe in key["probes"]:
        number = probe["proposal"]
        path = run / "verdicts" / f"{number}.json"
        data, why = plan.read_return(path, shapes.JUDGE)
        # @req+ REQ-46371318@bTR5XgyXXjAC tgcyaj
        if data is None:
            if why == "returned nothing":
                absent.append(number)
                continue
            raise SystemExit(f"{path}: {why}")
        if data["proposal"] != number:
            raise SystemExit(f"{path}: answers proposal {data['proposal']}, "
                             f"not {number}")
        # @req- tgcyaj
        held[number] = data
    return held, absent


def reach(run, state_held):
    # @req> REQ-32019340@Ce9zMv1R_f5m xjprat
    if not state_held["recall"]:
        raise SystemExit(
            f"{run / plan.STATE}: the build recorded no recall prompt, and "
            "whether a probe's source was reached is read from what recall "
            "returned. Build the run again.")
    hit, stopped, refused = plan.recalled(run, state_held)
    unread = sorted(list(stopped.values())
                    + [f"{label} {'; '.join(why)}" for label, why in refused])
    return ({int(number): set(uids) for number, uids in hit.items()},
            {int(number): set(items)
             for number, items in state_held["named"].items()},
            unread)


def measure(key, held, recalled, named):
    # @req+ REQ-75438506@GIywOiWYUqgH 733yqr
    rows = []
    for probe in key["probes"]:
        verdict = held.get(probe["proposal"])
        if verdict is None:
            continue
        reached = recalled.get(probe["proposal"], set())
        carried = named.get(probe["proposal"], set())
        if probe["kind"] == "duplicate":
            names = cited(verdict)
            wanted = set(probe["neighbours"])
            source = probe["self"]
            rows.append({
                "proposal": probe["proposal"],
                "kind": "duplicate",
                "source": probe["source"],
                "recalled": source in reached,
                "stated": source in carried,
                "self": source in names,
                "neighbours_found": sorted(wanted & names),
                "neighbours_wanted": sorted(wanted),
                "outside_the_key": len(names - wanted - {source}),
            })
        elif probe["kind"] == "sibling":
            said = cited_siblings(verdict)
            wanted = f"proposal {probe['expects']}"
            rows.append({
                "proposal": probe["proposal"], "kind": "sibling",
                "link": probe["link"], "source": probe["source"],
                "recalled": wanted in reached,
                "stated": wanted in carried,
                "named": wanted in said,
                "outside_the_key": len(said - {wanted}),
            })
        else:
            said = {str(entry.get("fault"))
                    for entry in verdict.get("faults") or []}
            rows.append({
                "proposal": probe["proposal"],
                "kind": "fault",
                "source": probe["source"],
                "fault": probe["fault"],
                "named": probe["fault"] in said,
                "outside_the_key": len(said - {probe["fault"]}),
            })
    return rows
    # @req- 733yqr


def _totals(rows):
    # @req+ REQ-75438506@GIywOiWYUqgH xwdm24
    duplicates = [row for row in rows if row["kind"] == "duplicate"]
    faults = [row for row in rows if row["kind"] == "fault"]
    siblings = [row for row in rows if row["kind"] == "sibling"]
    wanted = sum(len(row["neighbours_wanted"]) for row in duplicates)
    found = sum(len(row["neighbours_found"]) for row in duplicates)
    return {
        "duplicate_probes": len(duplicates),
        "source_recalled": sum(1 for row in duplicates if row["recalled"]),
        "source_stated": sum(1 for row in duplicates if row["stated"]),
        "source_found": sum(1 for row in duplicates if row["self"]),
        "neighbours_wanted": wanted,
        "neighbours_found": found,
        "fault_probes": len(faults),
        "faults_named": sum(1 for row in faults if row["named"]),
        "sibling_probes": len(siblings),
        "siblings_recalled": sum(1 for row in siblings if row["recalled"]),
        "siblings_stated": sum(1 for row in siblings if row["stated"]),
        "siblings_found": sum(1 for row in siblings if row["named"]),
    }
    # @req- xwdm24


def unsound(totals):
    return totals["source_found"] < totals["duplicate_probes"]


def _line(label, part, whole, note=""):
    shown = f"{100 * part / whole:.1f}%" if whole else "n/a"
    return (f"{label:<18}{part}/{whole}  ({shown})"
            + (f"   {note}" if note else ""))


def report(rows, absent, unread, totals):
    # @req+ REQ-75438506@GIywOiWYUqgH cx4ygh
    lines = [f"{'proposal':>8}  {'kind':<9}  {'recall':<7}{'named':<7}"
             f"{'result':<32}outside the key"]
    for row in rows:
        reach_at = (("yes" if row["recalled"] else "no",
                     "yes" if row["stated"] else "no")
                    if "recalled" in row else ("-", "-"))
        if row["kind"] == "duplicate":
            result = (f"source {'found' if row['self'] else 'MISSED'}, "
                      f"neighbours {len(row['neighbours_found'])}"
                      f"/{len(row['neighbours_wanted'])}")
        elif row["kind"] == "sibling":
            result = (f"{row['link']} sibling "
                      f"{'found' if row['named'] else 'MISSED'}")
        else:
            result = f"{row['fault']} {'named' if row['named'] else 'MISSED'}"
        lines.append(f"{row['proposal']:>8}  {row['kind']:<9}  {reach_at[0]:<7}"
                     f"{reach_at[1]:<7}{result:<32}{row['outside_the_key']}")
    lines += ["", _line("source recalled", totals["source_recalled"],
                        totals["duplicate_probes"],
                        "what the recall pass reached"),
              _line("source named", totals["source_stated"],
                    totals["duplicate_probes"],
                    "what the judge prompt then carried"),
              _line("source found", totals["source_found"],
                    totals["duplicate_probes"],
                    "sanity: near-verbatim probes should all land"),
              _line("neighbours found", totals["neighbours_found"],
                    totals["neighbours_wanted"],
                    "a floor, not a rate -- see below"),
              _line("faults named", totals["faults_named"],
                    totals["fault_probes"]),
              _line("siblings recalled", totals["siblings_recalled"],
                    totals["sibling_probes"]),
              _line("siblings named", totals["siblings_stated"],
                    totals["sibling_probes"]),
              _line("siblings found", totals["siblings_found"],
                    totals["sibling_probes"], "what Pass B alone can see")]
    # @req- cx4ygh
    # @req+ REQ-22288699@6DWNPu-0CCxf tdrp6q
    if absent:
        lines.append("")
        lines.append("no verdict returned for proposal "
                     + ", ".join(str(number) for number in sorted(absent))
                     + " -- the run is short, so the figures above are not "
                       "comparable with a complete one")
    if unread:
        lines.append("")
        lines.append("the recall column reads no where a return was never "
                     "read rather than where a source or a sibling was "
                     "missed: "
                     + "; ".join(sorted(unread)))
    if unsound(totals):
        lines.append("")
        lines.append("a near-verbatim probe did not find the statement it was "
                     "derived from, so the run did not work rather than "
                     "measuring badly -- read its recall and named columns to "
                     "see which pass lost it before quoting any figure above")
    # @req- tdrp6q
    # @req+ REQ-91336482@TiPdPxI_xFIm vxxogb
    lines.append("")
    lines.append(LIMITATION)
    # @req- vxxogb
    return "\n".join(lines)


def cmd_mint(args):
    _store, records = plan.loaded()
    key = build(records, args.count, args.faults, args.seed, args.pairs)
    dims = plan.dimensions(corpus.find_root(), records)

    out = Path(args.out)
    (out / "proposals").mkdir(parents=True, exist_ok=True)
    stale = (sorted((out / "proposals").glob("*.md"))
             + sorted((out / "verdicts").glob("*.json")))
    for path in stale:
        path.unlink()
    for probe in key["probes"]:
        (out / "proposals" / f"{probe['proposal']:02d}.md").write_text(
            probe["statement"] + "\n")
    (out / "words.md").write_text(
        "".join(f"{probe['statement']}\n\n" for probe in key["probes"]))
    (out / "answers.json").write_text(json.dumps(key, indent=2) + "\n")
    recorded = {}
    if dims:
        recorded[plan.BINDS] = {
            name: {probe["proposal"]:
                   sorted(plan.bound(name, uid, probe["statement"])) or "all"
                   for probe in key["probes"]}
            for name, (uid, _members) in dims.items()}
    recorded[plan.TRACE] = {probe["proposal"]: [probe["statement"]]
                            for probe in key["probes"]}
    (out / "run.yaml").write_text(yaml.safe_dump(recorded, sort_keys=False))

    # @req+ REQ-79267149@1zBteGwniUwU 4avsug
    counted = {kind: sum(1 for probe in key["probes"] if probe["kind"] == kind)
               for kind in ("duplicate", "fault", "sibling")}
    print(f"{counted['duplicate']} duplicate probe(s), {counted['fault']} fault "
          f"probe(s) and {counted['sibling']} sibling probe(s) in {out}")
    # @req- 4avsug
    print(f"  proposals   {out}/proposals/NN.md, numbered as the proposal number")
    print(f"  words       {out}/words.md, the statements each probe traces to")
    print(f"  run         {out}/run.yaml, each probe's binding and trace")
    print(f"  key         {out}/answers.json")
    # @req> REQ-79267149@1zBteGwniUwU u3gura
    if stale:
        print(f"  retired     {len(stale)} file(s) of the run this key "
              "replaces, its verdicts among them")
    print(f"Build it with plan.py build --run {out}, spawn step 2's agents over "
          f"the prompts it writes, accept the returns with verdicts.py, then: "
          f"{Path(__file__).name} score --run {out}")
    return 0


def cmd_score(args):
    run = Path(args.run)
    where = run / "answers.json"
    # @req> REQ-32019340@Ce9zMv1R_f5m cwfhxj
    if not where.is_file():
        raise SystemExit(f"{where}: no key here; mint the probes first")
    key = json.loads(where.read_text())
    recalled, named, unread = reach(run, plan.state(run))
    held, absent = returned(run, key)
    rows = measure(key, held, recalled, named)
    totals = _totals(rows)
    print(report(rows, absent, unread, totals))
    (run / "score.json").write_text(json.dumps(
        {"totals": totals, "probes": rows, "no_verdict": sorted(absent),
         "no_recall_return": sorted(unread), "limitation": LIMITATION},
        indent=2) + "\n")
    return 1 if absent or unread or unsound(totals) else 0


def main(argv=None):
    parsed = argparse.ArgumentParser()
    sub = parsed.add_subparsers(dest="command", required=True)

    mint = sub.add_parser("mint")
    mint.add_argument("--out", required=True, metavar="DIR")
    mint.add_argument("--count", type=int, default=12)
    mint.add_argument("--faults", type=int, default=4)
    mint.add_argument("--pairs", type=int, default=2)
    mint.add_argument("--seed", type=int, default=7)
    mint.set_defaults(handler=cmd_mint)

    score = sub.add_parser("score")
    score.add_argument("--run", required=True, metavar="DIR")
    score.set_defaults(handler=cmd_score)

    args = parsed.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
