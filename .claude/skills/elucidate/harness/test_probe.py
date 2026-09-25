#!/usr/bin/env python3
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "synthesis"))
import plan
import probe
import verdicts as accepted

from reqctl import corpus

faults = []


def check(name, held, wanted):
    if held != wanted:
        faults.append(f"{name}: expected {wanted!r}, got {held!r}")


def truthy(name, held):
    if not held:
        faults.append(f"{name}: expected something true, got {held!r}")


RECORDS = {
    "REQ-10000001": {
        "status": "approved",
        "text": "When a [shard](shard) is shared, the product shall "
                "keep it for ${cache_retention}.",
        "relations": {"REQ-10000002": "derives_from",
                      "REQ-10000003": "depends_on",
                      "REQ-10000004": "supersedes"},
    },
    "REQ-10000002": {"status": "approved",
                     "text": "The product shall keep a shard."},
    "REQ-10000003": {"status": "draft",
                     "text": "The product shall do a drafted thing."},
    "REQ-10000004": {"status": "approved",
                     "text": "The product shall do a superseded thing."},
    "shard": {"status": "approved", "kind": "term",
              "entries": {"shard": {"definition": "A part of an export."}}},
    "cache_retention": {"status": "approved", "kind": "parameter",
                        "name": "cache_retention", "unit": "days",
                        "entries": {"30": {}}},
    "platform": {"status": "approved", "kind": "parameter", "name": "platform",
                 "default": "ui", "entries": {"api": {}, "ui": {}}},
    "storage_targets": {"status": "approved", "kind": "data",
                         "name": "storage_targets",
                         "entries": {"primary_disk": {}, "local_disk": {}}},
}


def reference(address):
    return probe.statement(
        RECORDS, {"text": "The product shall use ${%s}." % address})


check("a statement keeps its term links, which the lint the build runs demands, "
      "and writes only its parameter references out",
      probe.statement(RECORDS, RECORDS["REQ-10000001"]),
      "When a [shard](shard) is shared, the product shall keep it for 30 days.")

check("a statement referencing a platform member binds to it, by the name the "
      "parameter carries and by nothing else",
      (plan.bound("platform", "platform", "shall run on ${platform.api}."),
       plan.bound("platform", "platform", "shall run on ${PARAM-20000002.ui}.")),
      ({"api"}, set()))
check("and a probe binds to every platform, because mint writes every "
      "reference out as its literal and leaves no reference to bind it",
      plan.bound("platform", "platform",
                 probe.statement(RECORDS, {"text": "shall run on "
                                                   "${platform.api}."})),
      set())

check("a bare reference to a set names the set, not its first member",
      reference("platform"), "The product shall use api, ui.")
check("a bare reference to a single value names the value and its unit",
      reference("cache_retention"), "The product shall use 30 days.")
check("a default is named by the member it selects",
      reference("platform.default"), "The product shall use ui.")
check("a member is named by itself",
      reference("platform.api"), "The product shall use api.")
check("a bare data reference names the item",
      reference("storage_targets"),
      "The product shall use storage_targets.")
check("an addressed data entry names the entry",
      reference("storage_targets.primary_disk"),
      "The product shall use primary_disk.")

check("a statement carries no uid for an agent to match on",
      corpus.UID_IN_PROSE.findall(
          probe.statement(RECORDS, RECORDS["REQ-10000001"])), [])

check("a neighbour is an approved requirement it leans on",
      probe.neighbours(RECORDS, RECORDS["REQ-10000001"]), ["REQ-10000002"])

check("compound injects a second obligation and no second shall, which the "
      "lint refuses",
      (probe.injected("The product shall keep it.", "compound"),
       probe.injected("The product shall keep it.", "compound").count("shall")),
      ("The product shall keep it and record the change.", 1))
truthy("foreign_id injects an identifier from outside the corpus",
       "BD-CAP-001" in probe.injected("The product shall keep it.",
                                      "foreign_id"))

key = probe.build(RECORDS, count=1, faults=2, seed=7)
check("probes are numbered from one, without a gap",
      [held["proposal"] for held in key["probes"]], [1, 2, 3])
check("duplicates come first", [held["kind"] for held in key["probes"]],
      ["duplicate", "fault", "fault"])
check("the key carries its own limitation", key["limitation"], probe.LIMITATION)
check("a fault probe names the fault it injected",
      sorted(held["fault"] for held in key["probes"] if held["kind"] == "fault"),
      ["compound", "foreign_id"])
check("the same seed mints the same probes",
      probe.build(RECORDS, 1, 2, 7), key)

PAIRED = dict(RECORDS, **{
    "REQ-10000005": {"status": "approved",
                     "text": "The product shall relate to a shard.",
                     "relations": {"REQ-10000002": "derives_from"}}})
APPROVED = {uid: data for uid, data in PAIRED.items()
            if uid.startswith("REQ-") and data["status"] == "approved"}
pairs = probe.paired(PAIRED, APPROVED, random.Random(7), set(), 2, 1)

check("a pair is two probes that point at each other",
      [(held["proposal"], held["expects"]) for held in pairs],
      [(1, 2), (2, 1), (3, 4), (4, 3)])
check("the first pair is a statement and its verbatim restatement, which is "
      "the floor of what Pass B exists to catch",
      (pairs[0]["link"], pairs[0]["statement"] == pairs[1]["statement"]),
      ("duplicate", True))
check("the second is a statement and the neighbour the corpus says it leans on",
      (pairs[2]["link"],
       pairs[3]["source"] in probe.neighbours(PAIRED, PAIRED[pairs[2]["source"]])),
      ("neighbour", True))
check("a corpus with no source to spare mints no pair",
      probe.paired(PAIRED, APPROVED, random.Random(7), set(APPROVED), 2, 1), [])

try:
    probe.build({"REQ-10000002": RECORDS["REQ-10000002"]}, 1, 1, 7)
except SystemExit as refused:
    truthy("a corpus with no neighbour to probe is refused",
           "no approved requirement declares a neighbour" in str(refused))
else:
    faults.append("a corpus with no neighbour to probe was not refused")

check("a sibling is cited by its number, wherever a verdict names it",
      probe.cited_siblings({
          "covered_by": [{"uids": ["proposal 2", "REQ-10000001"]}],
          "relations": [{"target": "proposal 3"}],
          "conflicts": [{"uid": "REQ-10000004"}]}),
      {"proposal 2", "proposal 3"})

check("citations are collected from every shape a verdict credits an item in, "
      "and never from the nearest it named as not covering the proposal: a "
      "probe is its source verbatim, so a source placed there was missed",
      probe.cited({
          "covered_by": [{"uids": ["REQ-10000002", "REQ-10000004"]}],
          "conflicts": [{"uid": "DATA-40000001.entry"}],
          "nearest": [{"uid": "REQ-10000006"}],
          "relations": [{"target": "REQ-10000003"}, {"target": "proposal 4"}],
      }),
      {"REQ-10000002", "REQ-10000004", "DATA-40000001", "REQ-10000003"})

check("a verdict naming nothing cites nothing",
      probe.cited({"covered_by": [], "conflicts": [], "relations": []}), set())

check("a value or a word names a corpus item as much as a relation does",
      probe.cited({"values": [{"belongs_with": "PARAM-20000001.30"},
                              {"belongs_with": None}],
                   "words": [{"defined_by": "TERM-30000001"},
                             {"defined_by": None}]}),
      {"PARAM-20000001", "TERM-30000001"})


def verdict(number, **over):
    held = {"proposal": number, "covered_by": [], "conflicts": [],
            "relations": [], "nearest": [], "values": [], "words": [],
            "faults": [], "questions": []}
    held.update(over)
    return held


SCORED = {"limitation": probe.LIMITATION, "probes": [
    {"proposal": 1, "kind": "duplicate", "source": "REQ-10000001",
     "self": "REQ-10000001", "neighbours": ["REQ-10000002", "REQ-10000005"]},
    {"proposal": 2, "kind": "fault", "source": "REQ-10000004",
     "fault": "compound"},
    {"proposal": 3, "kind": "fault", "source": "REQ-10000002",
     "fault": "foreign_id"},
]}

STATE = {
    "proposals": {"1": {}, "2": {}, "3": {}},
    "recall": {"requirements-1-b1": {"shard": "requirements-1", "batch": 1,
                                     "proposals": [1, 2, 3]}},
    "shards": {"requirements-1": {"scope": "requirements", "batch": 40,
                                  "items": ["REQ-10000001", "REQ-10000002"]}},
    "named": {"1": {"REQ-10000001": ["same: the same obligation"]},
              "2": {}, "3": {}},
}

RETURN = {"shard": "requirements-1", "batch": 1, "results": [
    {"proposal": 1, "hits": [{"uid": "REQ-10000001", "bearing": "same",
                              "clause": "the same obligation"}]},
    {"proposal": 2, "hits": []},
    {"proposal": 3, "hits": []}]}

BLIND = dict(RETURN, results=[{"proposal": at, "hits": []} for at in (1, 2, 3)])

FOUND = (
    (1, verdict(1, covered_by=[{"uids": ["REQ-10000001"], "covers": "whole",
                                "reason": "the same obligation"}])),
    (2, verdict(2, faults=[{"fault": "compound", "reason": "as injected"}])),
    (3, verdict(3, faults=[{"fault": "foreign_id", "reason": "as injected"}])),
)


def laid(room, state=STATE, returns=(("requirements-1-b1", RETURN),),
         judged=()):
    run = Path(room)
    (run / "returns" / "recall").mkdir(parents=True, exist_ok=True)
    (run / "verdicts").mkdir(parents=True, exist_ok=True)
    (run / "answers.json").write_text(json.dumps(SCORED))
    (run / plan.STATE).write_text(json.dumps(state))
    for label, body in returns:
        (run / "returns" / "recall" / f"{label}.json").write_text(
            json.dumps(body))
    for number, body in judged:
        (run / "verdicts" / f"{number}.json").write_text(json.dumps(body))
    return run


with tempfile.TemporaryDirectory() as room:
    run = laid(room, judged=(
        (1, verdict(1, covered_by=[{"uids": ["REQ-10000001"], "covers": "whole",
                                    "reason": "the same obligation"}],
                    relations=[{"target": "REQ-10000002", "kind": "depends_on",
                                "reason": "leans on it"},
                               {"target": "REQ-10000009", "kind": "depends_on",
                                "reason": "outside the key"}])),
        (2, verdict(2, faults=[{"fault": "compound", "reason": "as injected"}])),
    ))
    recalled, named, unread = probe.reach(run, plan.state(run))
    check("the recall hits a probe's source was reached by are read from the "
          "returns the build's recall prompts wrote",
          (recalled, unread),
          ({1: {"REQ-10000001"}, 2: set(), 3: set()}, []))
    check("and what the judge prompt then stated is read from build.json",
          named, {1: {"REQ-10000001"}, 2: set(), 3: set()})

    held, absent = probe.returned(run, SCORED)
    rows = probe.measure(SCORED, held, recalled, named)
    check("a probe with no verdict is named, not scored", absent, [3])
    check("the source is recalled, stated and found, which are three passes "
          "and three columns",
          (rows[0]["recalled"], rows[0]["stated"], rows[0]["self"]),
          (True, True, True))
    check("a neighbour found is credited", rows[0]["neighbours_found"],
          ["REQ-10000002"])
    check("a neighbour missed is not", rows[0]["neighbours_wanted"],
          ["REQ-10000002", "REQ-10000005"])
    check("a citation outside the key is counted, not penalised",
          rows[0]["outside_the_key"], 1)
    check("an injected fault the agent named is credited", rows[1]["named"],
          True)

    totals = probe._totals(rows)
    check("totals count what was wanted, not what was returned",
          (totals["neighbours_found"], totals["neighbours_wanted"]), (1, 2))
    check("totals count the faults named", (totals["faults_named"],
                                            totals["fault_probes"]), (1, 1))
    check("and count the reach of each pass over the duplicate probes",
          (totals["source_recalled"], totals["source_stated"],
           totals["source_found"], totals["duplicate_probes"]), (1, 1, 1, 1))

    written = probe.report(rows, absent, unread, totals)
    truthy("the report prints the limitation, every run",
           probe.LIMITATION in written)
    truthy("the report says a short run is not comparable",
           "the run is short" in written)
    truthy("the report calls the neighbour figure a floor, not a rate",
           "a floor, not a rate" in written)
    truthy("the report names what each pass reached",
           "what the recall pass reached" in written
           and "what the judge prompt then carried" in written)
    truthy("the limitation says why a neighbour may be unreachable",
           "never had a way to reach" in probe.LIMITATION)
    truthy("and that the cut sweep the old measure reported is gone",
           "gone with" in probe.LIMITATION)

    code = probe.main(["score", "--run", str(run)])
    check("a run short a verdict is a failure, not a zero", code, 1)
    truthy("scoring writes its figures beside the key",
           json.loads((run / "score.json").read_text())["limitation"]
           == probe.LIMITATION)

with tempfile.TemporaryDirectory() as room:
    run = laid(room, judged=((1, verdict(1)), (2, verdict(2)), (3, verdict(3))))
    check("a run where every verdict is empty fails; a total regression is "
          "not a green run", probe.main(["score", "--run", str(run)]), 1)
    scored = json.loads((run / "score.json").read_text())["totals"]
    truthy("and the figures say the run did not work", probe.unsound(scored))
    truthy("which the report states rather than leaving the reader to it",
           "the run did not work" in probe.report([], [], [], scored))

with tempfile.TemporaryDirectory() as room:
    run = laid(room, judged=((1, verdict(4)),))
    try:
        probe.returned(run, SCORED)
    except SystemExit as refused:
        truthy("a verdict answering another proposal is refused by number",
               "answers proposal 4, not 1" in str(refused))
    else:
        faults.append("a verdict answering another proposal was scored anyway")

with tempfile.TemporaryDirectory() as room:
    run = laid(room)
    (run / "verdicts" / "1.json").write_text('{"proposal": 1}')
    try:
        probe.returned(run, SCORED)
    except SystemExit as refused:
        truthy("a verdict the judge shape refuses names the file and the "
               "field, not a traceback",
               "1.json" in str(refused) and "schema" in str(refused))
    else:
        faults.append("a verdict the judge shape refuses was scored anyway")

with tempfile.TemporaryDirectory() as room:
    run = laid(room, returns=(), judged=FOUND)
    recalled, _, unread = probe.reach(run, plan.state(run))
    check("a recall return that never came is named rather than read as a miss",
          (recalled, unread),
          ({1: set(), 2: set(), 3: set()},
           ["requirements-1-b1 returned nothing"]))
    check("and a run whose every verdict came back and found its source still "
          "fails on it, so the missing return alone answers the exit code",
          probe.main(["score", "--run", str(run)]), 1)
    truthy("which the report states rather than printing it as a source or a "
           "sibling missed, both of which now read that column",
           "never read rather than where a source or a sibling was missed"
           in probe.report([], [], unread, probe._totals([])))

with tempfile.TemporaryDirectory() as room:
    run = laid(room, returns=(("requirements-1-b1", BLIND),), judged=FOUND)
    recalled, named, unread = probe.reach(run, plan.state(run))
    held, _ = probe.returned(run, SCORED)
    rows = probe.measure(SCORED, held, recalled, named)
    check("a source recall never reached that the judge prompt still named is "
          "the floor carrying the run, and the three columns say so apart",
          (rows[0]["recalled"], rows[0]["stated"], rows[0]["self"], unread),
          (False, True, True, []))

SIBLINGS = {"limitation": probe.LIMITATION, "probes": [
    {"proposal": 1, "kind": "sibling", "link": "neighbour",
     "source": "REQ-10000001", "expects": 2},
    {"proposal": 2, "kind": "sibling", "link": "neighbour",
     "source": "REQ-10000002", "expects": 1},
]}

reach = {1: {"proposal 2"}, 2: set()}
rows = probe.measure(
    SIBLINGS,
    {1: verdict(1, covered_by=[{"uids": ["proposal 2"], "covers": "whole",
                                "reason": "the sibling beside it"}]),
     2: verdict(2)},
    reach, reach)
check("a sibling carries the recalled and named columns a duplicate does, so a "
      "pair missed says which pass lost it",
      (rows[0]["recalled"], rows[0]["stated"], rows[0]["named"]),
      (True, True, True))
check("and a pair the recall return never held the other of reads no on both, "
      "while still scoring as missed",
      (rows[1]["recalled"], rows[1]["stated"], rows[1]["named"]),
      (False, False, False))

totals = probe._totals(rows)
check("which the totals count pass by pass",
      (totals["siblings_recalled"], totals["siblings_stated"],
       totals["siblings_found"], totals["sibling_probes"]), (1, 1, 1, 2))

written = probe.report(rows, [], [], totals)
check("and the report prints both on a sibling row, where it printed a dash",
      [held[2:4] for held in map(str.split, written.splitlines())
       if held[:2] in (["1", "sibling"], ["2", "sibling"])],
      [["yes", "yes"], ["no", "no"]])
truthy("naming the two passes apart for siblings as for sources",
       "siblings recalled" in written and "siblings named" in written)

with tempfile.TemporaryDirectory() as room:
    run = laid(room, state=dict(STATE, recall={}))
    try:
        probe.reach(run, plan.state(run))
    except SystemExit as refused:
        truthy("a build that wrote no recall prompt is refused, rather than "
               "scored as a run that reached nothing, and the refusal names "
               "the remedy",
               "recorded no recall prompt" in str(refused)
               and "Build the run again" in str(refused))
    else:
        faults.append("a run with no recall prompt was scored anyway")

with tempfile.TemporaryDirectory() as room:
    run = Path(room) / "run"
    run.mkdir()
    try:
        probe.main(["score", "--run", str(run)])
    except SystemExit as refused:
        truthy("scoring before minting names the key it wants",
               "no key here" in str(refused))
    else:
        faults.append("a run with no key was scored anyway")

with tempfile.TemporaryDirectory() as room:
    store, _ = corpus.load()
    live = {item.uid: item.data for item in corpus.items(store)}
    real = probe.build(live, count=6, faults=2, seed=3)
    for held in real["probes"]:
        if corpus.UID_IN_PROSE.findall(held["statement"]):
            faults.append(f"probe {held['proposal']} leaks a uid: "
                          f"{held['statement']}")
        if held["kind"] == "duplicate":
            if not held["neighbours"]:
                faults.append(f"probe {held['proposal']} labels no neighbour")
            for named_uid in [held["self"]] + held["neighbours"]:
                if live.get(named_uid, {}).get("status") != "approved":
                    faults.append(f"probe {held['proposal']} keys {named_uid}, "
                                  "which is not an approved item")

    out = Path(room) / "run"
    probe.main(["mint", "--out", str(out), "--count", "1", "--faults", "1",
                "--pairs", "1"])
    minted = json.loads((out / "answers.json").read_text())
    numbers = [held["proposal"] for held in minted["probes"]]
    check("mint writes a proposal file per probe, where the build reads them",
          sorted(path.name for path in (out / "proposals").glob("*.md")),
          [f"{at:02d}.md" for at in numbers])
    check("and mints the sibling pair it was asked for",
          sum(1 for held in minted["probes"] if held["kind"] == "sibling"), 2)
    check("the file holds the statement the key states",
          (out / "proposals" / "01.md").read_text().strip(),
          minted["probes"][0]["statement"])
    recorded = corpus.read(out / "run.yaml")
    check("mint records no binding where the corpus nominates no dimension, "
          "which the build accepts rather than refusing for want of a record",
          plan.BINDS in recorded, False)
    check("with no parameter reference left in any statement to narrow that "
          "binding, and none the build would refuse as parsing as nothing",
          [held["proposal"] for held in minted["probes"]
           if corpus.PARAM_REF.search(held["statement"])], [])
    check("and traces every probe to its own statement",
          recorded[plan.TRACE],
          {held["proposal"]: [held["statement"]] for held in minted["probes"]})
    spoken_words = (out / "words.md").read_text()
    truthy("which words.md is written from, so the trace check finds them there",
           all(held["statement"] in spoken_words
               for held in minted["probes"]))

    check("the build accepts the run mint wrote, lint and trace and binding "
          "and all", plan.build(out, plan.SHARD_CHARS, plan.SHARD_ITEMS), 0)

    state_held = plan.state(out)
    spoken = {held["proposal"]: held for held in minted["probes"]}
    for label, spec in state_held["recall"].items():
        items = set(state_held["shards"][spec["shard"]]["items"])
        (out / "returns" / "recall" / f"{label}.json").write_text(json.dumps({
            "shard": spec["shard"], "batch": spec["batch"], "results": [
                {"proposal": number, "hits": [
                    {"uid": uid, "bearing": "same", "clause": "as minted"}
                    for uid in (spoken[number]["source"],
                                f"proposal {spoken[number].get('expects')}")
                    if uid in items and uid != f"proposal {number}"]}
                for number in spec["proposals"]]}))

    check("and the judge step reads those returns and names what it carried",
          plan.judge(out), 0)
    state_held = plan.state(out)
    for number, held in spoken.items():
        stated = set(state_held["named"][str(number)])
        if held["kind"] == "sibling":
            body = verdict(number, covered_by=[
                {"uids": [f"proposal {held['expects']}"], "covers": "whole",
                 "reason": "the sibling it was planted beside"}])
        elif held["kind"] == "fault":
            body = verdict(number, faults=[{"fault": held["fault"],
                                            "reason": "as injected"}])
        else:
            body = verdict(number, covered_by=[
                {"uids": [held["self"]], "covers": "whole",
                 "reason": "the same obligation"}])
        for cited_uid in probe.cited(body) | probe.cited_siblings(body):
            if cited_uid not in stated:
                faults.append(f"proposal {number}: the judge prompt did not "
                              f"state {cited_uid}, which the key expects")
        (out / "returns" / "judge" / f"{number}.json").write_text(
            json.dumps(body))

    check("verdicts.py accepts them into verdicts/N.json, unpadded",
          (accepted.main(["--run", str(out)]),
           sorted(path.name for path in (out / "verdicts").glob("*.json"))),
          (0, sorted(f"{number}.json" for number in numbers)))

    check("and a run that found every source, sibling and fault passes",
          probe.main(["score", "--run", str(out)]), 0)
    scored = json.loads((out / "score.json").read_text())["totals"]
    check("every pass reached the source it was handed",
          (scored["source_recalled"], scored["source_stated"],
           scored["source_found"], scored["duplicate_probes"]), (1, 1, 1, 1))
    check("the sibling pair is credited to Pass B, and the recall pass and the "
          "judge prompt that carried it are counted apart",
          (scored["siblings_recalled"], scored["siblings_stated"],
           scored["siblings_found"], scored["sibling_probes"]), (2, 2, 2, 2))
    check("and the injected fault is credited",
          (scored["faults_named"], scored["fault_probes"]), (1, 1))

    probe.main(["mint", "--out", str(out), "--count", "1", "--faults", "1",
                "--pairs", "1", "--seed", "11"])
    check("minting again into the same run retires the verdicts the old key "
          "was answered with, rather than leaving a stale one to be scored "
          "against the statement that replaced it",
          sorted(path.name for path in (out / "verdicts").glob("*.json")), [])

if faults:
    print("\n".join(faults))
    sys.exit(1)
print(f"probe harness self-test: {len(faults)} fault(s)")
sys.exit(0)
