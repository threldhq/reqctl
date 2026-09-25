#!/usr/bin/env python3
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan
import shapes

from reqctl import corpus

faults = []


def check(name, held, wanted):
    if held != wanted:
        faults.append(f"{name}: expected {wanted!r}, got {held!r}")


def truthy(name, held):
    if not held:
        faults.append(f"{name}: expected something true, got {held!r}")


def refused(name, call, *words):
    try:
        call()
    except SystemExit as stop:
        for word in words:
            if word not in str(stop):
                faults.append(f"{name}: the refusal does not say {word!r}: {stop}")
    else:
        faults.append(f"{name}: not refused")


def block(uid, extra="", status="approved"):
    return (f'<a id="{uid}"></a>\n## {uid}\nThe product shall hold {uid}.\n'
            f"{extra}- status: {status}\n\n")


def held(prefix, count, extra=""):
    return [(f"{prefix}-{10000000 + at}", block(f"{prefix}-{10000000 + at}", extra))
            for at in range(count)]


def proposal(number, statement, kind="REQ"):
    return (number, statement, Path(f"{number:02d}.md"), kind)


RECORDS = {
    "TERM-30000001": {"kind": "term", "status": "approved",
                      "entries": {"archive": {"word": "archive", "aliases": ["archived"],
                                            "definition": "The holding state."}}},
    "TERM-30000002": {"kind": "term", "status": "approved",
                      "entries": {"record": {"word": "record",
                                             "definition": "A thing held."}}},
    "hop_limit": {"kind": "parameter", "name": "hop_limit", "text": "How far.",
                  "value_type": "count", "entries": {"3": {}}, "unit": "hops"},
    "platform": {"kind": "data", "name": "platform", "text": "Where it runs.",
                 "entries": {"android": {"store": "play"}, "ios": {}}},
    "challenge_roles": {"kind": "data", "name": "challenge_roles",
                        "text": "Who judges.",
                        "entries": {"recall": {"model": "claude-sonnet-5"},
                                    "judge": {"model": "claude-opus-5"}}},
    "REQ-10000001": {"kind": "requirement", "status": "approved",
                     "text": "The product shall [archive](archive) a [record](record)."},
    "REQ-10000002": {"kind": "requirement", "status": "approved",
                     "text": "The product shall keep a [record](record)."},
    "REQ-10000003": {"kind": "requirement", "status": "draft",
                     "text": "The product shall wait ${hop_limit}."},
}

check("the export splits at its anchors and nowhere else",
      [uid for uid, _ in plan.blocks(block("REQ-10000001") + block("TERM-30000001"))],
      ["REQ-10000001", "TERM-30000001"])

check("a parameter is read from the one value it states",
      plan.parameter(RECORDS, "hop_limit"), 3)
refused("a parameter the corpus lacks is refused with the remedy",
        lambda: plan.parameter(RECORDS, "recall_batch"), "recall_batch", "Mint one")
check("the roles are read from the data item, by the model's family",
      plan.roles(RECORDS), {"recall": "sonnet", "judge": "opus"})
refused("a role whose model is not a name is refused",
        lambda: plan.roles({**RECORDS, "challenge_roles": {
            "kind": "data", "name": "challenge_roles", "text": "Who judges.",
            "entries": {"recall": {"model": True}, "judge": {"model": "claude-opus-5"}}}}),
        "names no model for recall")
check("a corpus stating no roles item uses the models the build ships",
      plan.roles({k: v for k, v in RECORDS.items() if k != "challenge_roles"}),
      plan.MODELS)
check("a corpus naming one role ships the rest",
      plan.roles({**RECORDS, "challenge_roles": {
          "kind": "data", "name": "challenge_roles", "text": "Who judges.",
          "entries": {"judge": {"model": "claude-fable-5-1"}}}}),
      {"recall": plan.MODELS["recall"], "judge": "fable"})
check("a default model covers every role the corpus does not name",
      plan.roles({**RECORDS, "challenge_roles": {
          "kind": "data", "name": "challenge_roles", "text": "Who judges.",
          "default": "every", "entries": {"every": {"model": "claude-haiku-4-5"}}}}),
      {"recall": "haiku", "judge": "haiku"})
check("and a role named on its own wins over the default",
      plan.roles({**RECORDS, "challenge_roles": {
          "kind": "data", "name": "challenge_roles", "text": "Who judges.",
          "default": "every",
          "entries": {"every": {"model": "claude-haiku-4-5"},
                      "judge": {"model": "claude-opus-5"}}}}),
      {"recall": "haiku", "judge": "opus"})

TIER = {"tier": {"kind": "data", "name": "tier", "text": "Which tier.",
                 "entries": {"free": {}, "paid": {}}}}
MARKED = ('$schema: "https://json-schema.org/draft/2020-12/schema"\n'
          "x-binding: true\ntype: object\n")


def nominating(room, *names):
    schemas = Path(room) / "requirements" / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    for name in names:
        (schemas / f"{name}.schema.yaml").write_text(MARKED)
    return Path(room)


def recording(room, body):
    run = Path(room) / "run"
    run.mkdir(parents=True, exist_ok=True)
    (run / "run.yaml").write_text(body)
    return run


def proposed(statement, kind="REQ"):
    return [(1, statement, None, kind)]


with tempfile.TemporaryDirectory() as room:
    check("a corpus nominating no dimension resolves none",
          plan.dimensions(nominating(room), RECORDS), {})
    check("and binds nothing, asking for no record at all",
          plan.binding(Path(room) / "absent", proposed("The product shall a."),
                       nominating(room), RECORDS), {})

with tempfile.TemporaryDirectory() as room:
    resolved = plan.dimensions(nominating(room, "platform"), RECORDS)
    check("a nominated dimension resolves to its members",
          {name: members for name, (_, members) in resolved.items()},
          {"platform": {"android", "ios"}})
    run = recording(room, "binds:\n  platform:\n    1: [android]\n")
    check("a record agreeing with the text is accepted",
          plan.binding(run, proposed("The product shall a on ${platform.android}."),
                       nominating(room, "platform"), RECORDS),
          {1: {"platform": "android"}})
    refused("a record disagreeing with the text names the dimension",
            lambda: plan.binding(
                run, proposed("The product shall a on ${platform.ios}."),
                nominating(room, "platform"), RECORDS),
            "for platform where", "ios")
    refused("a guard recorded against a dimension is refused",
            lambda: plan.binding(
                run, proposed("The build shall a.", "GUARD"),
                nominating(room, "platform"), RECORDS),
            "binds to no dimension")

with tempfile.TemporaryDirectory() as room:
    root = nominating(room, "platform", "tier")
    check("two nominated dimensions both resolve",
          sorted(plan.dimensions(root, {**RECORDS, **TIER})), ["platform", "tier"])
    run = recording(
        room, "binds:\n  platform:\n    1: [android]\n  tier:\n    1: [free]\n")
    check("a proposal agreeing on both is accepted",
          plan.binding(run, proposed(
              "The product shall a on ${platform.android} for ${tier.free}."),
              root, {**RECORDS, **TIER}),
          {1: {"platform": "android", "tier": "free"}})
    refused("and the one that disagrees is named, not the one that agrees",
            lambda: plan.binding(run, proposed(
                "The product shall a on ${platform.android} for ${tier.paid}."),
                root, {**RECORDS, **TIER}),
            "for tier where", "paid")

with tempfile.TemporaryDirectory() as room:
    root = nominating(room, "platform")
    refused("a recorded member the dimension does not define is named",
            lambda: plan.binding(
                recording(room, "binds:\n  platform:\n    1: [web]\n"),
                proposed("The product shall a."), root, RECORDS),
            "web", "does not define", "android, ios")
    refused("a dimension the record states nothing for is named",
            lambda: plan.binding(
                recording(room, "binds:\n  tier:\n    1: all\n"),
                proposed("The product shall a."), root, RECORDS),
            "records nothing for platform")

BLOCKED = held("REQ", 3) + [("REQ-10000009", block("REQ-10000009", status="draft"))] + held("GUARD", 2)
REQS = plan.partitioned(BLOCKED, [proposal(1, "The product shall x.")], 25000, 100)
check("every requirement sits in exactly one shard when a proposal names the product, "
      "and no guard does",
      sorted(uid for _, _, stated in REQS for uid, _ in stated),
      ["REQ-10000000", "REQ-10000001", "REQ-10000002", "REQ-10000009"])
truthy("a draft obligation appears in its shard as draft",
       any("- status: draft" in text for _, _, stated in REQS for uid, text in stated
           if uid == "REQ-10000009"))
check("only guards are sharded when every proposal names the build",
      [scope for _, scope, _ in plan.partitioned(
          BLOCKED, [proposal(1, "The build shall x.", "GUARD")], 25000, 100)],
      ["guards"])
check("both kinds are sharded when the run names both",
      [scope for _, scope, _ in plan.partitioned(
          BLOCKED, [proposal(1, "The product shall x."),
                    proposal(2, "The build shall y.", "GUARD")], 25000, 100)],
      ["requirements", "guards"])

BIG = ("REQ-19999999", block("REQ-19999999", "x" * 2000 + "\n"))
ALONE = plan.packed("requirements", held("REQ", 2) + [BIG] + held("GUARD", 2), 1000, 100)
check("a shard ends at the character bound, and an item past the bound stands alone",
      [len(stated) for _, stated in ALONE], [2, 1, 2])
check("a shard ends at the item bound where the items reach it before the characters",
      [len(stated) for _, stated in plan.packed("requirements", held("REQ", 25), 100000, 10)],
      [10, 10, 5])

THREE = [proposal(1, "The product shall a."), proposal(2, "The product shall b."),
         proposal(3, "The build shall c.", "GUARD")]
sibling = plan.siblings(THREE)
check("three proposals make one sibling shard stating all three",
      [uid for uid, _ in sibling[2]], ["proposal 1", "proposal 2", "proposal 3"])
check("one proposal makes no sibling shard",
      plan.siblings(THREE[:1]), None)
check("a batch holds at most the bound, filled in order",
      plan.batched([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
check("a proposal is recalled against shards of its own kind only",
      (plan.judged_by(THREE, "requirements"), plan.judged_by(THREE, "guards"),
       plan.judged_by(THREE, plan.SIBLINGS)), ([1, 2], [3], [1, 2, 3]))

DICT = plan.dictionary(RECORDS)
truthy("the dictionary states a term's word, aliases and definition",
       "archive (also archived) -- The holding state." in DICT)
truthy("and a data item by name, stating no field of any entry",
       "data platform: Where it runs. [android, ios]" in DICT and "play" not in DICT)
truthy("and a parameter with its value and unit",
       "parameter hop_limit: How far. [3] hops" in DICT)

with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    shard = held("REQ", 3)
    text = plan.recall_prompt(run, "requirements-1", 1, "requirements", 3, 9,
                              {1, 2}, THREE, "the owner said", "nothing declined",
                              DICT, plan.assembled("requirements", shard, {}))
    truthy("a recall prompt states every item of its shard",
           all(block(uid) in text for uid, _ in shard))
    truthy("and the proposals of its batch, and no other",
           "proposal 1: The product shall a." in text
           and "proposal 2: The product shall b." in text
           and "proposal 3" not in text)
    truthy("and the shape the return is cut to, admitting only the shard's identifiers",
           json.dumps(shapes.recall("requirements"), indent=1) in text
           and shapes.CITED["requirements"] in text
           and shapes.CITED["siblings"] not in text)
    truthy("and the dictionary", DICT in text)
    truthy("and neither the owner's words nor the declined list",
           "the owner said" not in text and "nothing declined" not in text)
    other = plan.recall_prompt(run, plan.SIBLINGS, 1, plan.SIBLINGS, 3, 9,
                               {1, 2, 3}, THREE, "the owner said", "nothing declined",
                               DICT, plan.assembled(plan.SIBLINGS, sibling[2], {}))
    truthy("the sibling prompt states the owner's words and the declined list",
           "the owner said" in other and "nothing declined" in other)
    truthy("and the run's proposals as the shard",
           "The run's 3 proposals" in other)

refused("a run past the agent ceiling is refused, stating the count",
        lambda: plan.ceilinged(151, 150), "151", "150", "before any prompt")
check("a run at the ceiling is not", plan.ceilinged(150, 150), None)
refused("a prompt past the line bound is refused, naming it and the remedy",
        lambda: plan.lined({"requirements-1-b1": "a\n" * 2001}, 2000),
        "requirements-1-b1", "--chars")

STORE, _ = corpus.load()
refused("a proposal the lint faults refuses the run, naming the proposal and the fault",
        lambda: plan.linted([proposal(2, "The product shall a and shall b.")], STORE),
        "proposal 2", "more than one 'shall'", "before any prompt")
refused("and a proposal the lint would refuse outright is a fault too",
        lambda: plan.linted([proposal(3, "The product shall wait ${no_such}.")], STORE),
        "proposal 3", "no_such")
check("a clean statement passes the lint",
      plan.linted([proposal(1, "The product shall record the approving user.")], STORE),
      None)

with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    (run / "run.yaml").write_text('trace:\n  1: ["undo for bulk"]\n')
    check("a trace quoting the owner's words passes",
          plan.traced(run, "I want undo for bulk export.", THREE[:1]),
          {"1": ["undo for bulk"]})
    (run / "run.yaml").write_text('trace:\n  1: ["undo for everything"]\n')
    refused("a trace quoting words the owner did not write refuses the run",
            lambda: plan.traced(run, "I want undo for bulk export.", THREE[:1]),
            "proposal 1", "undo for everything")

STATE = {
    "proposals": {"1": {"kind": "REQ", "statement": "The product shall a."},
                  "2": {"kind": "REQ", "statement": "The product shall b."}},
    "shards": {"requirements-1": {"scope": "requirements", "batch": 40,
                                  "items": ["REQ-10000000", "REQ-10000001"]}},
    "recall": {"requirements-1-b1": {"shard": "requirements-1", "batch": 1,
                                     "proposals": [1, 2]}},
    "models": {"recall": "sonnet", "judge": "opus"}, "lines": 2000, "total": 2,
}


def returned(run, label, results):
    (run / "returns" / "recall").mkdir(parents=True, exist_ok=True)
    (run / "returns" / "recall" / f"{label}.json").write_text(json.dumps(
        {"shard": "requirements-1", "batch": 1, "results": results}))


with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    returned(run, "requirements-1-b1", [{"proposal": 1, "hits": []}])
    _, _, held_back = plan.recalled(run, json.loads(json.dumps(STATE)))
    truthy("a recall return omitting a proposal the prompt carried is refused, naming it",
           held_back and "omits an entry for proposal 2" in held_back[0][1])
    returned(run, "requirements-1-b1", [
        {"proposal": 1, "hits": [{"uid": "REQ-77777777", "bearing": "same", "clause": "c"}]},
        {"proposal": 2, "hits": []}])
    _, _, held_back = plan.recalled(run, json.loads(json.dumps(STATE)))
    truthy("a return naming an item the prompt did not state is refused, naming the item",
           held_back and "names REQ-77777777, which the prompt did not state" in held_back[0][1])
    returned(run, "requirements-1-b1", [
        {"proposal": 1, "hits": [{"uid": "REQ-10000001", "bearing": "same", "clause": "c"}]},
        {"proposal": 2, "hits": []}])
    named, stopped, held_back = plan.recalled(run, json.loads(json.dumps(STATE)))
    check("a clean return names its hits per proposal",
          (named["1"], named["2"], stopped, held_back),
          ({"REQ-10000001": ["same: c"]}, {}, {}, []))
    (run / "returns" / "recall" / "requirements-1-b1.json").write_text('{"shard": "req')
    _, stopped, _ = plan.recalled(run, json.loads(json.dumps(STATE)))
    truthy("a return that stops mid-document is a stop at the output bound",
           "requirements-1" in stopped)
    (run / "returns" / "recall" / "requirements-1-b1.json").unlink()
    _, stopped, _ = plan.recalled(run, json.loads(json.dumps(STATE)))
    truthy("and so is a return that never came",
           stopped.get("requirements-1", "").endswith("returned nothing"))

with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    (run / "prompts" / "recall").mkdir(parents=True)
    (run / "returns" / "recall").mkdir(parents=True)
    (run / "workflow").mkdir()
    state = json.loads(json.dumps(STATE))
    state["proposals"] = {str(n): {"kind": "REQ", "statement": f"The product shall {n}."}
                          for n in range(1, 41)}
    state["recall"] = {"requirements-1-b1": {"shard": "requirements-1", "batch": 1,
                                             "proposals": list(range(1, 41))}}
    forty = [proposal(n, f"The product shall {n}.") for n in range(1, 41)]
    shards = [("requirements-1", "requirements", held("REQ", 2))]
    (run / "returns" / "recall" / "requirements-1-b1.json").write_text("{")
    with contextlib.redirect_stdout(io.StringIO()):
        plan.halved(run, state, {"requirements-1": "requirements-1-b1 stopped"},
                    forty, "w", "d", DICT, {}, shards, 2)
    check("a stopped return halves the shard's batch",
          state["shards"]["requirements-1"]["batch"], 20)
    check("and rebuilds the shard's prompts carrying at most the halved batch",
          sorted((label, len(spec["proposals"])) for label, spec in state["recall"].items()),
          [("requirements-1-b1", 20), ("requirements-1-b2", 20)])
    truthy("and retires the stopped return",
           not (run / "returns" / "recall" / "requirements-1-b1.json").exists()
           and (run / "prompts" / "recall" / "requirements-1-b2.md").is_file())
    state["shards"]["requirements-1"]["batch"] = 1
    refused("a shard whose batch is already one is refused with the remedy",
            lambda: plan.halved(run, state, {"requirements-1": "x stopped"}, forty,
                                "w", "d", DICT, {}, shards, 2),
            "already one", "--chars")

INDEX = plan.indexed(RECORDS)
FLOOR = plan.floor(INDEX, "REQ", "The product shall [[archive]] a [[record]].", 10)
check("the floor ranks the obligations sharing the most references with the proposal",
      FLOOR, [("REQ-10000001", ["archive", "record"]), ("REQ-10000002", ["record"])])
check("and holds at most the bound",
      plan.floor(INDEX, "REQ", "The product shall [[archive]] a [[record]].", 1),
      [("REQ-10000001", ["archive", "record"])])
check("a reference is read from a link and a parameter alike, an alias by its term",
      plan.references(INDEX[0], "Shall [archived](archive) wait ${hop_limit.default} for an [[Archived]]."),
      {"archive", "hop_limit"})

with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    blocked = [("REQ-10000001", block("REQ-10000001", "- depends_on REQ-10000002\n")),
               ("REQ-10000002", block("REQ-10000002"))]
    state = {"proposals": {"1": {"kind": "REQ", "statement": "The product shall a.",
                                 "binding": {"platform": "all of them"}},
                           "2": {"kind": "REQ", "statement": "The product shall b."}}}
    named = {"REQ-10000001": ["same: restates it"], "REQ-10000002": ["floor: shares record"],
             "proposal 2": ["overlaps: shares a clause"]}
    text = plan.judge_prompt(run, "1", state["proposals"]["1"], list(named), named,
                             state, dict(blocked), DICT)
    truthy("a judge prompt states every named item whole, with its status and edges",
           block("REQ-10000001", "- depends_on REQ-10000002\n") in text
           and block("REQ-10000002") in text)
    truthy("and what recall or the floor said of each",
           "recall said same: restates it" in text
           and "recall said floor: shares record" in text)
    truthy("and a sibling by its statement",
           "proposal 2: The product shall b." in text)
    truthy("and the dimension the owner settled",
           "platform: all of them" in text)
    truthy("and the shape", json.dumps(shapes.JUDGE, indent=1) in text)
    check("an item named for another proposal is not stated",
          block("REQ-10000002") in plan.judge_prompt(
              run, "1", state["proposals"]["1"], ["REQ-10000001"], named, state,
              dict(blocked), DICT), False)
    check("an item recall and the floor both named is stated once",
          text.count(block("REQ-10000001", "- depends_on REQ-10000002\n")), 1)

GROUPS = plan.grouped([f"REQ-{n:08d}" for n in range(55)], 45, 20)
check("fifty-five items past a bound of forty-five make three groups of at most twenty",
      [len(group) for group in GROUPS], [20, 20, 15])
check("and every item sits in exactly one group",
      sorted(uid for group in GROUPS for uid in group), [f"REQ-{n:08d}" for n in range(55)])
check("thirty items under the bound make no group", plan.grouped(["x"] * 30, 40, 20), None)

with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    (run / "returns" / "judge").mkdir(parents=True)
    (run / "returns" / "judge" / "1-g1.json").write_text(json.dumps(
        {"proposal": 1, "group": 1, "findings": [
            {"uid": "REQ-10000001", "kind": "covered_part", "clause": "shall hold",
             "reason": "the holding"}]}))
    spec = {"kind": "GUARD", "statement": "The build shall a."}
    lines, held_back = plan.group_returns(run, "1", [["REQ-10000001"], ["REQ-10000002"]])
    text = plan.final_prompt(run, "1", spec, lines, DICT)
    truthy("a final prompt states each group's findings with the clause quoted",
           '- REQ-10000001 [covered_part] clause: "shall hold" reason: the holding' in text)
    truthy("and the shape", json.dumps(shapes.JUDGE, indent=1) in text)
    check("and a group that returned nothing is refused, not quoted",
          held_back, [("1-g2", "returned nothing")])
    (run / "returns" / "judge" / "1-g2.json").write_text("{not json")
    lines, held_back = plan.group_returns(run, "1", [["REQ-10000001"], ["REQ-10000002"]])
    truthy("as is one that does not read, naming why",
           [name for name, _ in held_back] == ["1-g2"]
           and held_back[0][1].startswith("does not parse as JSON"))
    (run / "returns" / "judge" / "1-g2.json").write_text(json.dumps(
        {"proposal": 1, "group": 2, "findings": [
            {"uid": "REQ-10000001", "kind": "near", "clause": "c", "reason": "r"}]}))
    (run / "dictionary.md").write_text(DICT)
    (run / "prompts" / "final").mkdir(parents=True)
    (run / "workflow").mkdir()
    (run / plan.STATE).write_text(json.dumps({
        "proposals": {"1": spec}, "models": {"judge": "opus"}, "lines": 2000,
        "judge": {"1": {"groups": [["REQ-10000001"], ["REQ-10000002"]]}}}))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = plan.final(run)
    truthy("a group return naming an item outside its group is refused, naming the item, "
           "and the group is spawned again while its final prompt waits",
           code == 1 and "1-g2: names REQ-10000001, which the group did not state" in out.getvalue()
           and "1 final prompt(s) waiting on them" in out.getvalue()
           and not (run / "returns" / "judge" / "1-g2.json").exists()
           and [one["label"] for one in json.loads(
               (run / "workflow" / "judge.json").read_text())["prompts"]] == ["group:1-g2"])

with tempfile.TemporaryDirectory() as room:
    run = Path(room)
    (run / "verdicts").mkdir()
    (run / "declined.md").write_text("Archiving, which the owner was only wondering about.\n")
    (run / plan.STATE).write_text(json.dumps({
        "proposals": {"1": {"kind": "REQ", "statement": "The product shall a.",
                            "trace": ["undo for bulk"]}},
        "judge": {"1": {"groups": None}}, "named": {"1": {}}}))
    (run / "verdicts" / "1.json").write_text(json.dumps(
        {"proposal": 1, "covered_by": [{"uids": ["REQ-10000001"], "covers": "whole",
                                        "reason": "restates it"}],
         "conflicts": [], "relations": [], "nearest": [], "values": [], "words": [],
         "faults": [], "questions": []}))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        plan.describe(run)
    truthy("the description quotes the passage each proposal traces to",
           "“undo for bulk”" in out.getvalue())
    truthy("and each item the verdict names with the verdict and its reason",
           "- covered whole by REQ-10000001: restates it" in out.getvalue())
    truthy("and the declined list",
           "Archiving, which the owner was only wondering about." in out.getvalue())
    (run / "verdicts" / "1.json").write_text("{not json")
    refused("a verdict that does not read is refused rather than rendered",
            lambda: plan.describe(run), "proposal 1's verdict does not parse")
    (run / "verdicts" / "1.json").unlink()
    refused("as is one not yet written",
            lambda: plan.describe(run), "proposal 1's verdict returned nothing")

with tempfile.TemporaryDirectory() as room:
    run = Path(room) / "run"
    (run / "proposals").mkdir(parents=True)
    (run / "words.md").write_text(
        "I want the approving user recorded, and the build should refuse a run "
        "whose words file holds no word.\n")
    (run / "declined.md").write_text("A question, not an obligation.\n")
    (run / "proposals" / "01.md").write_text("The product shall record the approving user.\n")
    (run / "proposals" / "02.md").write_text(
        "If the file stating the owner's words holds no word, then the build shall "
        "refuse the run.\n")
    (run / "run.yaml").write_text(
        'trace:\n  1: ["the approving user recorded"]\n'
        '  2: ["refuse a run whose words file holds no word"]\n')
    with contextlib.redirect_stdout(io.StringIO()):
        code = plan.build(run, plan.SHARD_CHARS, plan.SHARD_ITEMS)
    check("a clean run builds", code, 0)
    state = json.loads((run / plan.STATE).read_text())
    truthy("and every requirement sits in exactly one requirements shard",
           sorted(uid for name, spec in state["shards"].items()
                  if spec["scope"] == "requirements" for uid in spec["items"])
           == sorted(uid for uid, _ in plan.blocks((run / "export.md").read_text())
                     if uid.startswith("REQ-")))
    written = json.loads((run / "workflow" / "recall.json").read_text())
    spawn = written["prompts"]
    truthy("and the manifest names one recall agent per prompt, with its shape and model",
           len(spawn) == len(state["recall"])
           and all(written["shapes"][one["schema"]] == shapes.recall(
                       state["shards"][state["recall"][one["label"].split(":")[1]]["shard"]]["scope"])
                   and one["model"] == state["models"]["recall"]
                   and Path(one["path"]).is_file() for one in spawn))
    check("and states each shape once",
          len(written["shapes"]), len({spec["scope"] for spec in state["shards"].values()}))
    truthy("and the coverage prompt states the findings file as the only output, every "
           "name, and no criteria where none are carried",
           "findings file is your only output" in (run / "prompts" / "coverage.md").read_text()
           and all(f"`{name}`" in (run / "prompts" / "coverage.md").read_text()
                   for name in plan.NAMES))
    before = (run / "export.md").read_text()
    (run / "verdicts" / "1.json").write_text("{}")
    (run / "proposals" / "01.md").write_text("The product shall a and shall b.\n")
    refused("a proposal the lint faults refuses the run before anything is written",
            lambda: plan.build(run, plan.SHARD_CHARS, plan.SHARD_ITEMS),
            "proposal 1", "more than one 'shall'")
    truthy("and leaves the export and the verdicts as they were",
           (run / "export.md").read_text() == before
           and (run / "verdicts" / "1.json").read_text() == "{}")
    (run / "proposals" / "01.md").write_text("The product shall record the approving user.\n")
    (run / "proposals" / "1.md").write_text("The product shall record the approving user.\n")
    refused("two files named for one number refuse the run, naming both",
            lambda: plan.build(run, plan.SHARD_CHARS, plan.SHARD_ITEMS), "01.md", "1.md")
    (run / "proposals" / "1.md").unlink()
    (run / "words.md").write_text("  \n")
    refused("a words file holding no word refuses the run",
            lambda: plan.build(run, plan.SHARD_CHARS, plan.SHARD_ITEMS), "holds no word")

plan.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", "")
refused("an export that wrote nothing is refused rather than sharded",
        plan.exported, "wrote no corpus")

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("run builder self-test: 0 fault(s)")
sys.exit(0)
