#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coverage as _coverage
import shapes
from coverage import NAMES

from reqctl import corpus, validate, write

ANCHOR = re.compile(
    rf'^<a id="((?:{corpus.KINDS})-\d{{8}}|{corpus.NAME})"></a>$', re.MULTILINE)
RELATION = re.compile(rf"^- (?:{'|'.join(write.RELATIONS)}) (REQ-\d{{8}})$")
USED_BY = "- used by: "
TOKEN = re.compile(r"\$\{[^}]*\}?")
SIBLING = re.compile(r"^proposal (\d+)$")
ROLES = "challenge_roles"
BINDS = "binds"
CRITERIA = "criteria"
TRACE = "trace"
FINDINGS = "coverage.yml"
STATE = "build.json"
OBLIGATION = {"REQ": "requirements", "GUARD": "guards"}
KIND_NAME = {"REQ": "requirement", "GUARD": "guard"}
SIBLINGS = "siblings"
SHARD_CHARS = 25_000
SHARD_ITEMS = 100
PROMPT_LINES = 2000
# @req> REQ-18272120@P5XOlho5WrkH o47rwb
BOUNDS = ("recall_batch", "judge_bound", "judge_group", "floor_k",
          "agent_ceiling")
PHASES = {"recall": "medium", "judge": "high"}
MODELS = {"recall": "sonnet", "judge": "opus"}

BEARING = """A statement bears on a proposal when it states the same obligation in
other words (same), states part of it or more than it (overlaps), would be
contradicted by it or contradicts it (contradicts), is the more general
statement the proposal refines (parent), provides a capability the proposal
presupposes (prerequisite), restricts the proposal's behaviour (restricted_by),
or concerns the same behaviour closely enough that a judge should see it
(related). Sharing a noun is not bearing on. Over-inclusion of genuinely
related items is acceptable; a miss is not."""

RECALL = """You are a recall reader over one shard of a corpus of product and build
statements. This prompt states everything you are given and everything you
may cite. Read nothing else.

For EVERY proposal stated below, list every item of the shard that bears on
it. {bearing}

Return one results entry per proposal stated below, numbered as it is stated,
even when it has no hits (hits: []). Cite only the identifiers the shard
states, and never a proposal's own number; a proposal number is an
identifier only in the shard that states the run's proposals. For each hit
give a one-clause reason in clause. Set shard to "{shard}" and batch to
{batch}.

{write}

## The proposals

{proposals}
{words}
{dictionary}

## {heading}

{text}"""

SHARD = "Shard {shard}: {count} of the {total} {scope} the corpus holds, whole"
OTHERS = "The run's {count} proposals, each recalled against the others"
WRITE = """Write the result as JSON matching this shape to {out} with the Write tool,
then stop. Do not narrate.

{shape}"""
DICTIONARY = """## The dictionary: every term, parameter and data item the corpus defines

{dictionary}"""

WORDS = """
## The owner's words

{words}

## Considered and not converted, with the reason

{declined}
"""

DECIDE = """Decide, by meaning not wording:
- covered_by: items whose meaning already contains the proposal, whole or in
  part. Several may act together to cover the whole. Never report one for a
  shared noun.
- conflicts: items the proposal contradicts, including an item that obliges
  what the proposal forbids or forbids what it obliges.
- relations: the edge the proposal should carry toward an existing item:
  derives_from (a refinement, such as the same obligation under a narrower
  condition), depends_on (cannot be built before it), constrains (a condition
  on it), supersedes (replaces it).
- nearest: the up to three closest items and why each does not cover the
  proposal. Give at least one when covered_by is empty and items were named.
- values: every quantity the proposal states, with the parameter in the
  dictionary it shares a home with, or null where none does.
- words: nouns the proposal uses as terms of art, with the term in the
  dictionary that defines each, or null where none does.
- faults: ambiguous, unverifiable, compound, foreign_id,
  undetermined_outcome or inappropriate_implementation, each with its reason.
- questions: decisions your set cannot settle, phrased neutrally.
Cite only identifiers stated below."""

JUDGE = """You judge one proposed statement against the corpus items a recall pass
and a reference floor named for it. This prompt states everything you are
given. Read nothing else.

Proposal {number}: {statement}
{binding}

{decide}

{write}

{dictionary}

## The items named for this proposal, each whole with its status and the edges it carries

{items}"""

GROUP = """You judge one proposed statement against one group of the corpus items
named for it; other groups are judged elsewhere and a final judge assembles the
findings. This prompt states everything you are given. Read nothing else.

Proposal {number}: {statement}
{binding}

For each item that matters to the proposal, return one finding: covered_whole
(the item's meaning contains the whole proposal), covered_part (it contains
part of the proposal; say which part in reason), conflict (the proposal
contradicts it), derives_from, depends_on, constrains, supersedes (the edge
the proposal should carry toward it), or near (close but none of the above;
say why not). Copy the item's decisive clause verbatim into clause. Judge by
meaning, not wording. Never report a finding for a shared noun alone. Cite
only identifiers stated below. Set proposal to {number} and group to {group}.

{write}

{dictionary}

## Group {group} of the items named for this proposal, each whole with its status and the edges it carries

{items}"""

FINAL = """You are the final judge of one proposed statement. The items named for it
were too many for one reading, so group judges each read a bounded part and
returned the findings below, each with the decisive clause of its item
quoted. This prompt states everything you are given. Read nothing else.

Proposal {number}: {statement}
{binding}

{decide} Several items from different groups may act together to cover the
whole; assemble them.

{write}

{dictionary}

## The group findings

{findings}"""

BOUND = """\
{name}: {members}, which the owner settled before you were spawned. Whether it
should apply to another is not yours to raise."""

UNBOUND = """\
This proposal states a build rule, which binds to no dimension. What it binds
to is not a question about it."""

COVERAGE = """You read the owner's words back against this run's proposals and
its declined list, and name what neither accounts for. You have no tool to read
anything, so everything you judge is below.

The owner's words: {words}

Considered and not converted, with the reason: {declined}

The proposals: {proposals}
{criteria}
Write one YAML document to {found}. The only names it may state, anywhere in the
document, are {names}; one outside them fails the document whole. Its two lists
are `unclaimed` and `renamed`. An unclaimed entry quotes the owner's words
verbatim and states why neither a proposal nor the declined list accounts for the
passage; a renamed entry names the owner's word and the noun a proposal put in
its place. Every quote is checked back against the owner's words, so copy rather
than paraphrase, and write an empty list where you found nothing.

That findings file is your only output. Do not write a note per item, do not
restate the set, do not summarise before or after. Read, decide, write it, stop.
"""

CARRIES = """
A proposal's acceptance criteria state what its statement does not restate, so a
passage a criterion accounts for is claimed and not unclaimed:
{stated}
"""


def exported():
    done = subprocess.run(["reqctl", "export", "--all"],
                          capture_output=True, text=True, check=False)
    if done.returncode:
        raise SystemExit(done.stderr.strip() or "reqctl export failed")
    if not done.stdout.strip():
        raise SystemExit("reqctl export wrote no corpus")
    return done.stdout


def blocks(text):
    found = list(ANCHOR.finditer(text))
    return [(held.group(1),
             text[held.start():found[at + 1].start()
                  if at + 1 < len(found) else len(text)])
            for at, held in enumerate(found)]


def trimmed(uid, block, held, records):
    printed, lines = set(), []
    # @req> REQ-89404055@Nsbb0X-z5HuM grxatb
    for line in block.splitlines():
        found = RELATION.match(line)
        if found:
            printed.add(found.group(1))
            if found.group(1) not in held:
                continue
        elif line.startswith(USED_BY):
            inside = [one.group() for one in LINKED.finditer(line)
                      if one.group(1) in held]
            if not inside:
                continue
            line = USED_BY + ", ".join(inside)
        lines.append(line)
    # @req+ REQ-67476912@t4G-bPIouCkO 47tdge
    declared = {target for target
                in corpus.mapping(records.get(uid) or {}, "relations")
                if target.startswith("REQ-")}
    if printed != declared:
        raise SystemExit(
            f"{uid}: the export prints the relations {sorted(printed)} where "
            f"the corpus declares {sorted(declared)}. A shard is cut from what "
            "`reqctl export` renders, so a change there is a change here.")
    # @req- 47tdge
    return "\n".join(lines) + "\n"


LINKED = re.compile(r"\[[^\]]*\]\(#([^)]+)\)")


def loaded():
    store, _ = corpus.load()
    return store, {str(item.uid): corpus.raw(item)
                   for item in corpus.items(store)}


def glossary():
    return loaded()[1]


def written(out, shape):
    return WRITE.format(out=out, shape=json.dumps(shape, indent=1))


def spawn(run, folder, name, label, shape, model, effort):
    return {"label": label, "path": str(run / "prompts" / folder / f"{name}.md"),
            "out": str(run / "returns" / folder / f"{name}.json"),
            "schema": shape, "model": model, "effort": effort}


def named_item(records, kind, name):
    found = [(uid, data) for uid, data in records.items()
             if corpus.kind_of(uid, data) == kind and data.get("name") == name]
    if len(found) != 1:
        raise SystemExit(
            f"the corpus defines {'no' if not found else 'more than one'} "
            f"{kind} named {name}, and the build reads its bounds from it. "
            "Mint one first.")
    return found[0]


def parameter(records, name):
    # @req+ REQ-18272120@P5XOlho5WrkH dyeqka
    _, data = named_item(records, "parameter", name)
    held = list(corpus.entries(data) or {})
    if len(held) != 1 or not str(held[0]).isdigit():
        raise SystemExit(f"{name} states {held}, and the build is bounded by "
                         "one whole number")
    # @req- dyeqka
    return int(held[0])


def family(model):
    return model.split("-")[1] if model.startswith("claude-") else model


def roles(records):
    found = [data for uid, data in records.items()
             if corpus.kind_of(uid, data) == "data"
             and data.get("name") == ROLES]
    if len(found) > 1:
        raise SystemExit(
            f"more than one item is named {ROLES}, and which of them names "
            "the models is not the build's to decide.")
    held = dict(MODELS)
    if not found:
        return held
    entries = corpus.entries(found[0]) or {}
    fallback = (entries.get(found[0].get("default")) or {}).get("model")
    for phase in PHASES:
        stated = (entries.get(phase) or {}).get("model")
        if stated is None:
            stated = fallback
        if stated is None:
            continue
        # @req> REQ-82356895@3k-Q_tVhphjY waczui
        if not isinstance(stated, str) or not stated:
            raise SystemExit(f"{ROLES} names no model for {phase}, which the "
                             "build spawns")
        held[phase] = family(stated)
    return held


def dimensions(root, records):
    held = {}
    for name in corpus.binding_dimensions(root):
        uid, data = named_item(records, "data", name)
        # @req+ REQ-29846444@iGWqcEzs6s52 zjcgv2
        members = set(corpus.entries(data) or {})
        if not members:
            raise SystemExit(
                f"{uid} defines no member, so every proposal binds to all of "
                "them whatever its text says and the check holds nothing to "
                "anything.")
        # @req- zjcgv2
        held[name] = (uid, members)
    return held


def bound(name, uid, statement):
    held = {found.group(2).lstrip(".")
            for found in corpus.PARAM_REF.finditer(statement)
            if found.group(1) in (name, uid)}
    for found in corpus.CONCEPT_LINK.finditer(statement):
        linked, _, member = found.group(2).partition(".")
        if linked in (name, uid):
            held.add(member)
    return held


def unresolved(records, statement):
    # @req> REQ-77623729@IBqRGG8zgX39 elfpax
    held = {str(data.get("name")): set(corpus.entries(data) or {})
            | ({"default"} if data.get("default") is not None else set())
            for uid, data in records.items()
            if corpus.kind_of(uid, data) in ("parameter", "data")}
    stray = set()
    for found in corpus.PARAM_REF.finditer(statement):
        member = found.group(2).lstrip(".").split(".")[0]
        if found.group(1) not in held or (member
                                          and member not in held[found.group(1)]):
            stray.add(found.group())
    return stray


def recorded(run):
    path = run / "run.yaml"
    read = corpus.read(path) if path.is_file() else None
    return path, (read if isinstance(read, dict) else {})


def rows(path, name, said, members):
    held = {}
    for number, value in said.items():
        # @req+ REQ-83454000@2mAdg5ekGPhz 2qoccn
        if value == "all":
            chosen = set()
        elif isinstance(value, list) and value:
            chosen = {str(one) for one in value}
        else:
            raise SystemExit(
                f"{path}: {name} states {value!r} for proposal {number}. The "
                "form is a list of members, as `[<member>]`, or `all`. An "
                "empty list is not all: a statement binds to at least one "
                "member of every dimension.")
        # @req- 2qoccn
        # @req+ REQ-50522674@snwm856zApjT 6ahzuj
        stray = chosen - members
        if stray:
            raise SystemExit(
                f"{path}: proposal {number} binds to {', '.join(sorted(stray))}"
                f", which the {name} data item does not define. The members "
                f"are {', '.join(sorted(members))}, or `all`.")
        # @req- 6ahzuj
        # @req> REQ-83454000@2mAdg5ekGPhz reughj
        if str(number) in held:
            raise SystemExit(
                f"{path}: {name} records proposal {number} twice -- YAML keeps "
                "both where one key is written `3` and the other `\"3\"`, and "
                "which of them governs is not this file's to decide.")
        held[str(number)] = chosen
    return held


def settled(run, dims):
    path, read = recorded(run)
    # @req> REQ-30037092@q2bg6jcRf_YK 6bxg5g
    if not path.is_file():
        raise SystemExit(
            f"{path}: a run records the members each proposal binds to, under "
            f"`{BINDS}`, keyed by dimension and then by proposal number. "
            "Step 1 asks the owner; nothing else settles it.")
    # @req+ REQ-83454000@2mAdg5ekGPhz 2uanuo
    said = read.get(BINDS)
    if not isinstance(said, dict):
        raise SystemExit(
            f"{path}: `{BINDS}` maps each of {', '.join(sorted(dims))} to the "
            "proposal numbers and the members each binds to, as "
            "`<dimension>:` then `2: [<member>]`, or `all`.")
    # @req- 2uanuo
    held = {}
    for name, (_, members) in dims.items():
        # @req+ REQ-30037092@q2bg6jcRf_YK avbh7j
        stated = said.get(name)
        if not isinstance(stated, dict):
            raise SystemExit(
                f"{path}: `{BINDS}` records nothing for {name}, which the "
                "corpus nominates as a dimension. Its members are "
                f"{', '.join(sorted(members))}.")
        # @req- avbh7j
        held[name] = rows(path, name, stated, members)
    return held


def binding(run, held, root, records):
    dims = dimensions(root, records)
    if not dims:
        return {}
    # @req+ REQ-92272837@ytvXon0HxXUU owkvnp
    said = settled(run, dims)
    numbers = {str(number) for number, _, _, _ in held}
    for name, stated in said.items():
        unmatched = sorted(set(stated) - numbers)
        if unmatched:
            raise SystemExit(
                f"{run / 'run.yaml'} records {name} for proposal "
                f"{', '.join(unmatched)}, which the run holds no proposal for. "
                "Renumber the record, or write the proposal.")
    # @req- owkvnp
    chosen = {}
    for number, statement, _, kind in held:
        # @req+ REQ-58008138@O0-317mnnmhw usq427
        for token in TOKEN.finditer(statement):
            if not corpus.PARAM_REF.fullmatch(token.group()):
                raise SystemExit(
                    f"proposal {number} carries {token.group()}, which is not "
                    "a reference -- the form is ${name} or ${name.member}. One "
                    "that does not parse reads here as no reference at all, "
                    "which is how a statement binding to every member reads.")
        stray = unresolved(records, statement)
        if stray:
            raise SystemExit(
                f"proposal {number} carries {', '.join(sorted(stray))}, which "
                "the corpus resolves to no parameter, data item or member of "
                "one. A reference to nothing binds nothing rather than failing "
                "to parse, so it reads here as binding to every member.")
        # @req- usq427
        settled_on = {}
        for name, (uid, members) in dims.items():
            stated = said[name]
            written = bound(name, uid, statement)
            # @req> REQ-45221432@7p3Uxweu-mBn 2p6w7j
            if kind == "GUARD":
                if str(number) in stated:
                    raise SystemExit(
                        f"proposal {number} states a build rule and "
                        f"{run / 'run.yaml'} records {name} for it. A guard "
                        "binds to no dimension, so leave it out of the record "
                        "rather than recording all.")
                if written:
                    raise SystemExit(
                        f"proposal {number} states a build rule and references "
                        f"{', '.join(sorted(written))}. A guard binds to no "
                        "dimension; reword it, or state the rule as a "
                        "requirement.")
                continue
            # @req> REQ-30037092@q2bg6jcRf_YK 5nfu7e
            if str(number) not in stated:
                raise SystemExit(
                    f"proposal {number}: {run / 'run.yaml'} records no {name} "
                    "for it. Every requirement states one for every dimension, "
                    "and all is an answer rather than a silence.")
            wanted = stated[str(number)]
            # @req> REQ-16901746@GLAvhbvo-733 7yvsul
            if "" in written:
                raise SystemExit(
                    f"proposal {number} references the {name} data item "
                    "without naming a member, which states no binding. Name "
                    "the member, or reference nothing and record the proposal "
                    "as all.")
            # @req> REQ-50522674@snwm856zApjT 2rsevi
            if written - members:
                raise SystemExit(
                    f"proposal {number} references "
                    f"{', '.join(sorted(written - members))}, which the {name} "
                    "data item does not define. The members are "
                    f"{', '.join(sorted(members))}.")
            if written != wanted:
                raise SystemExit(
                    f"proposal {number}: the run records "
                    f"{', '.join(sorted(wanted)) or 'all'} for {name} where the "
                    f"statement references {', '.join(sorted(written)) or 'none'}"
                    ". A statement bound to fewer than all the members names "
                    "each in its own text; reword it, or correct the record.")
            settled_on[name] = ", ".join(sorted(wanted)) or "all of them"
        chosen[number] = settled_on
    return chosen


def obliged(statement):
    for prefix, (noun, _) in validate.SUBJECTS.items():
        if validate.SUBJECT[noun].search(statement):
            return prefix.rstrip("-")
    return None


def proposals(run):
    held, numbered = [], {}
    for path in sorted((run / "proposals").glob("*.md")):
        if not path.stem.isdigit():
            raise SystemExit(f"{path.name}: a proposal is numbered, as 01.md -- "
                             "the number is what a verdict answers")
        number = int(path.stem)
        # @req> REQ-73186885@ZZjResz6Cmzl twr3xe
        if number in numbered:
            raise SystemExit(
                f"{numbered[number]} and {path.name} are both numbered "
                f"{number}. Renumber one of them.")
        numbered[number] = path.name
        statement = " ".join(path.read_text().split())
        kind = obliged(statement)
        # @req> REQ-46098858@bag6NDybL_bp ny4y6f
        if kind is None:
            raise SystemExit(
                f"{path.name}: the statement names neither the product nor the "
                "build as the subject of its obligation. State `the product "
                "shall` or `the build shall`.")
        held.append((number, statement, path, kind))
    # @req> REQ-38776024@gWRVR1eicTsX trxd62
    if not held:
        raise SystemExit(f"{run / 'proposals'}: no proposal to challenge")
    return held


def said(run, name, missing):
    path = run / name
    if not path.is_file():
        raise SystemExit(f"{path}: {missing}")
    return " ".join(path.read_text().split())


def linted(held, store):
    # @req+ REQ-48622606@X-0rC69gV1Y4 kjkm4f
    refused = []
    for number, statement, _, kind in held:
        try:
            uid, _, _, faults = write.prepare(
                store, KIND_NAME[kind], {"text": statement}, placeholder="draft")
            faults = [fault.removeprefix(f"{uid}: ") for fault in faults]
        except corpus.ReqctlError as stop:
            faults = [str(stop)]
        if faults:
            refused.append(f"proposal {number}:\n"
                           + "\n".join(f"  {line}" for fault in faults
                                       for line in str(fault).splitlines()))
    if refused:
        raise SystemExit("the lint refuses the run before any prompt is "
                         "written. Correct each statement, then build:\n"
                         + "\n".join(refused))
    # @req- kjkm4f


def traced(run, words, held):
    path, read = recorded(run)
    traces = read.get(TRACE) or {}
    # @req> REQ-28473555@TU3p5DYcYjTU do2uo3
    if not isinstance(traces, dict):
        raise SystemExit(
            f"{path}: `{TRACE}` maps a proposal number to the passages of the "
            "owner's words it traces to, as `2: [\"undo for bulk\"]`.")
    spoken = _coverage.plain(_coverage.spoken(words))
    stated = {}
    for number, _, _, _ in held:
        # @req+ REQ-28473555@TU3p5DYcYjTU fw5ou4
        passages = traces.get(number, traces.get(str(number), []))
        if not isinstance(passages, list) or not all(
                isinstance(one, str) and one.strip() for one in passages):
            raise SystemExit(
                f"{path}: `{TRACE}` states {passages!r} for proposal {number}. "
                "The form is a list of passages quoted from the owner's words.")
        # @req- fw5ou4
        # @req> REQ-83939497@SjYhKgxzDeHv rfwtjo
        for passage in passages:
            if not _coverage.quoted(spoken, _coverage.spoken(passage)):
                raise SystemExit(
                    f"proposal {number} traces to {passage!r}, which the "
                    "owner's words do not hold. Quote what they wrote, or "
                    "decline the proposal.")
        stated[str(number)] = [" ".join(one.split()) for one in passages]
    return stated


def stated(run):
    path, read = recorded(run)
    held = read.get(CRITERIA)
    if held is None:
        return {}
    # @req+ REQ-37767588@_49nE3poGyAr viljjd
    if not isinstance(held, dict):
        raise SystemExit(
            f"{path}: `{CRITERIA}` maps a proposal number to the criteria it "
            "carries, as `2: [\"given a run | when it runs | then it holds\"]`. "
            "A proposal carrying none is left out rather than written empty.")
    carried = {}
    for number, value in held.items():
        if not isinstance(value, list) or not all(
                isinstance(one, str) for one in value):
            raise SystemExit(
                f"{path}: `{CRITERIA}` states {value!r} for proposal {number}. "
                "The form is a list of `given | when | then` strings.")
        carried[str(number)] = list(value)
    # @req- viljjd
    return carried


def packed(name, held, chars, items):
    # @req+ REQ-39970698@FZfYp4uj2nAi s5jtgy
    shards, holding, weight = [], [], 0
    for uid, block in held:
        # @req> REQ-43761464@pFlii3nabPOT n7x4xq
        if holding and (weight + len(block) > chars or len(holding) >= items):
            shards.append(holding)
            holding, weight = [], 0
        holding.append((uid, block))
        weight += len(block)
    if holding:
        shards.append(holding)
    # @req- s5jtgy
    return [(f"{name}-{at}", stated) for at, stated in enumerate(shards, 1)]


def partitioned(blocked, held, chars, items):
    # @req+ REQ-90454282@Hn_cCdBHt6FC yp35nb
    kinds = {kind for _, _, _, kind in held}
    shards = []
    for prefix, scope in OBLIGATION.items():
        if prefix not in kinds:
            continue
        block = [(uid, text) for uid, text in blocked
                 if uid.startswith(f"{prefix}-")]
        shards += [(name, scope, stated)
                   for name, stated in packed(scope, block, chars, items)]
    # @req- yp35nb
    return shards


def siblings(held):
    # @req+ REQ-83103011@wwcaVYzdMPrF 6po76w
    if len(held) < 2:
        return None
    return (SIBLINGS, SIBLINGS, [(f"proposal {number}",
                                  f"proposal {number}: {statement}\n")
                                 for number, statement, _, _ in held])
    # @req- 6po76w


def batched(numbers, batch):
    # @req+ REQ-94426583@robFmbw2ht7I eefhta
    # @req> REQ-32866040@hD5N5WdHBdwH f2uvmw
    return [numbers[at:at + batch] for at in range(0, len(numbers), batch)]
    # @req- eefhta


def judged_by(held, scope):
    return [number for number, _, _, kind in held
            if scope == SIBLINGS or OBLIGATION[kind] == scope]


def dictionary(records):
    lines = []
    # @req> REQ-48772986@j61eJ4j4pPTF 4xoc6j
    for uid, data in sorted(records.items()):
        kind = corpus.kind_of(uid, data)
        if kind == "term":
            fields = corpus.term_fields(data)
            aliases = ", ".join(str(one) for one in fields.get("aliases") or [])
            lines.append(f"- term {uid}: {corpus.term_word(data)}"
                         + (f" (also {aliases})" if aliases else "")
                         + f" -- {' '.join(str(fields.get('definition') or '').split())}")
        elif kind in ("parameter", "data"):
            keys = ", ".join(str(key) for key in corpus.entries(data) or {})
            unit = f" {data['unit']}" if data.get("unit") else ""
            lines.append(f"- {kind} {data.get('name')}: "
                         f"{' '.join(str(data.get('text') or '').split())}"
                         + (f" [{keys}]{unit}" if keys else ""))
    return "\n".join(lines) + "\n"


def assembled(scope, block, records):
    names = {uid for uid, _ in block}
    if scope == SIBLINGS:
        return "".join(text for _, text in block)
    return "".join(trimmed(uid, text, names, records) for uid, text in block)


def recall_prompt(run, name, batch, scope, count, total, numbers, held, words,
                  declined, dictionary_text, shard_text):
    out = run / "returns" / "recall" / f"{name}-b{batch}.json"
    listed = "".join(f"proposal {number}: {statement}\n\n"
                     for number, statement, _, _ in held if number in numbers)
    # @req+ REQ-18405752@9yj8huqrivwP et2jhv
    # @req+ REQ-29895268@qcT1AKt_5NgM cq5zif
    # @req> REQ-22034470@2jjDM1f9OESw oodadq
    return RECALL.format(
        bearing=BEARING, shard=name, batch=batch,
        write=written(out, shapes.recall(scope)), proposals=listed,
        words=WORDS.format(words=words, declined=declined)
        if scope == SIBLINGS else "",
        dictionary=DICTIONARY.format(dictionary=dictionary_text),
        heading=(OTHERS.format(count=count) if scope == SIBLINGS
                 else SHARD.format(shard=name, count=count, total=total,
                                   scope=scope)),
        text=shard_text)
    # @req- cq5zif
    # @req- et2jhv


def ceilinged(count, ceiling):
    # @req> REQ-48148587@rCLPkcgXvhNj aky7xw
    if count > ceiling:
        raise SystemExit(
            f"the run would spawn {count} agents, past the ceiling of "
            f"{ceiling}, and is refused before any prompt is written. Split "
            "the run, or raise the ceiling with the owner.")


def lined(prompts, lines):
    # @req+ REQ-80951798@Yv9lsMtU3XdI ro36h4
    over = sorted(f"{name} at {body.count(chr(10)) + 1}"
                  for name, body in prompts.items()
                  if body.count("\n") + 1 > lines)
    if over:
        raise SystemExit(
            f"{', '.join(over)}: a prompt holds at most {lines} lines. Build "
            "again with a smaller --chars.")
    # @req- ro36h4


def retire(run, text):
    # @req+ REQ-40238953@RUP3vKC4vR8r 7jdcpl
    where = run / "export.md"
    changed = where.is_file() and where.read_text() != text
    corpus.atomic_write(where, text)
    # @req- 7jdcpl
    if not changed:
        return []
    gone = sorted((run / "verdicts").glob("*.json"))
    for stale in gone:
        stale.unlink(missing_ok=True)
    return [stale.name for stale in gone]


def cleared(run):
    # @req+ REQ-95375719@-TYbW5JhiwAf ey5733
    findings = run / FINDINGS
    findings.unlink(missing_ok=True)
    # @req- ey5733
    return findings


def coverage(run, words, declined, held, carried):
    found = run / FINDINGS
    written = "".join(
        f"\n\nproposal {number}: {statement}" for number, statement, _, _ in held)
    lines = "".join(
        f"\n  proposal {number}: {one}"
        for number, _, _, _ in held
        for one in carried.get(str(number), ()))
    where = run / "prompts" / "coverage.md"
    # @req+ REQ-47744588@l3MLCZUPXuDZ a7rnsw
    # @req+ REQ-80500447@lQdaRnU0TPd1 omzjq4
    # @req> REQ-24569953@LsZU4Go81cg8 ssc6p2
    where.write_text(COVERAGE.format(
        words=words, declined=declined, proposals=written,
        criteria=CARRIES.format(stated=lines) if lines else "", found=found,
        names=", ".join(f"`{name}`" for name in NAMES)))
    # @req- omzjq4
    # @req- a7rnsw
    return where


def manifest(run, name, prompts):
    held, listed = {}, []
    for one in prompts:
        shape = next((key for key, value in held.items() if value == one["schema"]),
                     None)
        if shape is None:
            shape = f"shape-{len(held) + 1}"
            held[shape] = one["schema"]
        listed.append({**one, "schema": shape})
    where = run / "workflow" / f"{name}.json"
    where.write_text(json.dumps({"shapes": held, "prompts": listed}, indent=1)
                     + "\n")
    return where


def state(run):
    path = run / STATE
    # @req> REQ-32019340@Ce9zMv1R_f5m fctrpm
    if not path.is_file():
        raise SystemExit(f"{path}: the run was not built; run `plan.py build` "
                         "first")
    return json.loads(path.read_text())


def saved(run, held):
    (run / STATE).write_text(json.dumps(held, indent=1) + "\n")


def recall_prompts(run, held, state_held, shards, only, words, declined,
                   dictionary_text, records, total):
    prompts, spawned, texts = {}, [], {}
    for name, scope, block in shards:
        if only is not None and name not in only:
            continue
        texts[name] = assembled(scope, block, records)
        batch = state_held["shards"][name]["batch"]
        for at, chunk in enumerate(batched(judged_by(held, scope), batch), 1):
            label = f"{name}-b{at}"
            prompts[label] = recall_prompt(
                run, name, at, scope, len(block), total, set(chunk), held,
                words, declined, dictionary_text, texts[name])
            spawned.append(spawn(run, "recall", label, f"recall:{label}",
                                 shapes.recall(scope),
                                 state_held["models"]["recall"],
                                 PHASES["recall"]))
            state_held["recall"][label] = {"shard": name, "batch": at,
                                          "proposals": chunk}
    return prompts, spawned, texts


def build(run, chars, items, lines=PROMPT_LINES):
    # @req+ REQ-54959279@JYltFTa20G1- rwweso
    # @req> REQ-36523706@AaQoopUwKA6G 7e7svw
    if chars < 1 or items < 1 or lines < 1:
        raise SystemExit(f"--chars {chars} --items {items} --lines {lines}: a "
                         "shard holds at least one character and one item, and "
                         "the remedy for a shard too large is a smaller bound, "
                         "never none")
    words = said(run, "words.md", "the owner's words are the whole input, and "
                 "an agent judging a proposal without them cannot tell an "
                 "obligation nobody asked for from one they did")
    # @req> REQ-70526308@h3RVqifTiwTs o6st3y
    if not words:
        raise SystemExit(
            f"{run / 'words.md'}: the file stating the owner's words holds no "
            "word.")
    declined = (said(run, "declined.md", "") if (run / "declined.md").is_file()
                else "nothing was declined in this run")
    held = proposals(run)
    store, records = loaded()
    bounds = {name: parameter(records, name) for name in BOUNDS}
    models = roles(records)
    settled_on = binding(run, held, corpus.find_root(), records)
    traces = traced(run, words, held)
    carried = stated(run)
    linted(held, store)
    exported_text = exported()
    blocked = blocks(exported_text)
    # @req> REQ-40454564@MDvNhD0ynluV kostqz
    shards = partitioned(blocked, held, chars, items)
    sibling = siblings(held)
    if sibling is not None:
        shards.append(sibling)
    batch = bounds["recall_batch"]
    counted = sum(len(batched(judged_by(held, scope), batch))
                  for _, scope, _ in shards) + len(held)
    ceilinged(counted, bounds["agent_ceiling"])

    state_held = {
        "bounds": bounds, "models": models, "lines": lines,
        "proposals": {str(number): {"kind": kind, "statement": statement,
                                    "path": str(path),
                                    "binding": settled_on.get(number),
                                    "trace": traces.get(str(number), [])}
                      for number, statement, path, kind in held},
        "shards": {name: {"scope": scope, "items": [uid for uid, _ in block],
                          "batch": batch}
                   for name, scope, block in shards},
        "recall": {}, "judge": {}, "named": {},
    }
    dictionary_text = dictionary(records)
    prompts, spawned, texts = recall_prompts(
        run, held, state_held, shards, None, words, declined, dictionary_text,
        records, len(blocked))
    lined(prompts, lines)

    for folder in ("prompts/recall", "prompts/judge", "prompts/final",
                   "returns/recall", "returns/judge", "returns/final",
                   "verdicts", "workflow"):
        (run / folder).mkdir(parents=True, exist_ok=True)
    for stale in list((run / "prompts" / "recall").glob("*.md")) + list(
            (run / "returns" / "recall").glob("*.json")):
        stale.unlink()
    for name, body in prompts.items():
        (run / "prompts" / "recall" / f"{name}.md").write_text(body)
    (run / "shards").mkdir(exist_ok=True)
    for name, text in texts.items():
        (run / "shards" / f"{name}.md").write_text(text)
    (run / "dictionary.md").write_text(dictionary_text)
    saved(run, state_held)
    where = manifest(run, "recall", spawned)
    coverage(run, words, declined, held, carried)
    cleared(run)
    retired = retire(run, exported_text)
    for name in retired:
        print(f"retired {name}: the export it was judged against has moved")
    # @req> REQ-16868696@GYtmXbCQKILu js66h5
    print(f"{len(held)} proposal(s) over {len(shards)} shard(s) in batches of "
          f"{batch}: {len(spawned)} recall agent(s), then one judge each")
    print(f"  spawn     {where}")
    print(f"  prompts   {run / 'prompts' / 'recall'}/<shard>-b<n>.md")
    print(f"  coverage  {run / 'prompts' / 'coverage.md'}, read back once the "
          "answers are in")
    return 0
    # @req- rwweso


def read_return(path, shape):
    if not path.is_file():
        return None, "returned nothing"
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as broken:
        return None, f"does not parse as JSON: {broken}"
    found = sorted(Draft202012Validator(shape).iter_errors(data), key=str)
    if found:
        where = "/".join(str(part) for part in found[0].absolute_path) or "root"
        return None, f"schema: {where}: {found[0].message}"
    return data, None


def recalled(run, state_held):
    named = {str(number): {} for number in state_held["proposals"]}
    stopped, refused = {}, []
    for label, spec in sorted(state_held["recall"].items()):
        path = run / "returns" / "recall" / f"{label}.json"
        data, why = read_return(path, shapes.recall(
            state_held["shards"][spec["shard"]]["scope"]))
        if data is None:
            stopped[spec["shard"]] = f"{label} {why}"
            continue
        # @req+ REQ-25592483@a0gpRdyEWB-1 vamoo7
        stated = {str(one) for one in spec["proposals"]}
        seen = {str(entry["proposal"]) for entry in data["results"]}
        faults = [f"omits an entry for proposal {number}"
                  for number in sorted(stated - seen, key=int)]
        faults += [f"answers proposal {number}, which the prompt did not carry"
                   for number in sorted(seen - stated)]
        held = set(state_held["shards"][spec["shard"]]["items"])
        for entry in data["results"]:
            for hit in entry["hits"]:
                # @req+ REQ-94538693@Q40c2VogCp5E 4xyeq2
                if hit["uid"] not in held:
                    faults.append(f"names {hit['uid']}, which the prompt did "
                                  "not state")
                elif hit["uid"] == f"proposal {entry['proposal']}":
                    faults.append(f"names proposal {entry['proposal']} as "
                                  "bearing on itself")
                # @req- 4xyeq2
        if faults:
            refused.append((label, faults))
            continue
        # @req- vamoo7
        for entry in data["results"]:
            number = str(entry["proposal"])
            if number not in stated:
                continue
            for hit in entry["hits"]:
                named[number].setdefault(hit["uid"], []).append(
                    f"{hit['bearing']}: {hit['clause']}")
    return named, stopped, refused


def halved(run, state_held, stopped, held, words, declined, dictionary_text,
           records, shards, total):
    # @req+ REQ-19832934@CAEeElFyXNOg moar22
    for name, why in sorted(stopped.items()):
        batch = state_held["shards"][name]["batch"]
        # @req> REQ-33633053@4xh96ub1a3EH mrzj65
        if batch < 2:
            raise SystemExit(
                f"{why}, and its batch is already one proposal, so the shard "
                "is too large for one reading. Build again with a smaller "
                "--chars.")
        state_held["shards"][name]["batch"] = (batch + 1) // 2
        for label in [one for one, spec in state_held["recall"].items()
                      if spec["shard"] == name]:
            del state_held["recall"][label]
            (run / "prompts" / "recall" / f"{label}.md").unlink(missing_ok=True)
            (run / "returns" / "recall" / f"{label}.json").unlink(missing_ok=True)
    prompts, spawned, _ = recall_prompts(
        run, held, state_held, shards, set(stopped), words, declined,
        dictionary_text, records, total)
    lined(prompts, state_held["lines"])
    for name, body in prompts.items():
        (run / "prompts" / "recall" / f"{name}.md").write_text(body)
    saved(run, state_held)
    where = manifest(run, "recall", spawned)
    # @req- moar22
    # @req+ REQ-82676674@FK_7la2Hg_XC vpqdb6
    for name, why in sorted(stopped.items()):
        print(f"{why}: {name} is rebuilt in batches of "
              f"{state_held['shards'][name]['batch']}")
    print(f"{len(spawned)} recall agent(s) to spawn again: {where}")
    # @req- vpqdb6


def indexed(records):
    words, carried = {}, {}
    for uid, data in records.items():
        kind = corpus.kind_of(uid, data)
        if kind == "term":
            for word in validate._term_words(data):
                words[word.casefold()] = corpus.name_of(uid, data)
        elif kind in ("requirement", "guard"):
            carried[uid] = {corpus.split_address(address)[0]
                            for address in corpus.references(data)
                            + corpus.concept_references(data)}
    return words, carried


def references(words, statement):
    held = set()
    for found in write.WIKI_LINK.finditer(statement):
        held.add(words.get(found.group(1).casefold(), found.group(1)))
    for found in corpus.CONCEPT_LINK.finditer(statement):
        held.add(found.group(2).partition(".")[0])
    for found in corpus.PARAM_REF.finditer(statement):
        held.add(found.group(1))
    return held


def floor(index, kind, statement, k):
    # @req+ REQ-80191784@V7PNDDWSGYuy f4rqof
    words, carried = index
    wanted = references(words, statement)
    ranked = []
    for uid, refs in carried.items():
        if not uid.startswith(f"{kind}-"):
            continue
        shared = sorted(wanted & refs)
        if shared:
            ranked.append((-len(shared), uid, shared))
    return [(uid, shared) for _, uid, shared in sorted(ranked)[:k]]
    # @req- f4rqof


def stated_items(state_held, text, names, named):
    lines = []
    for uid in names:
        reasons = "".join(f"  recall said {line}\n" for line in named.get(uid, []))
        found = SIBLING.match(uid)
        if found:
            other = state_held["proposals"][found.group(1)]
            lines.append(f"{uid}: {other['statement']}\n{reasons}\n")
        else:
            lines.append(text[uid] + reasons + "\n")
    return "".join(lines)


def binding_text(spec):
    held = spec.get("binding")
    if held is None:
        return ""
    if spec["kind"] == "GUARD":
        return UNBOUND
    return "\n".join(BOUND.format(name=name, members=members)
                      for name, members in sorted(held.items()))


def judge_prompt(run, number, spec, names, named, state_held, text,
                 dictionary_text):
    out = run / "returns" / "judge" / f"{number}.json"
    # @req> REQ-30631052@upW72WeLPoHT jyes6a
    return JUDGE.format(
        number=number, statement=spec["statement"], binding=binding_text(spec),
        decide=DECIDE, write=written(out, shapes.JUDGE),
        dictionary=DICTIONARY.format(dictionary=dictionary_text),
        items=stated_items(state_held, text, names, named)
        or "(nothing was named for this proposal)\n")


def grouped(names, bound_at, group):
    # @req+ REQ-48762557@LXnAEs9b0lwa 5f3ye7
    if len(names) <= bound_at:
        return None
    return [names[at:at + group] for at in range(0, len(names), group)]
    # @req- 5f3ye7


def group_prompt(run, number, spec, at, names, named, state_held, text,
                 dictionary_text):
    out = run / "returns" / "judge" / f"{number}-g{at}.json"
    return GROUP.format(
        number=number, statement=spec["statement"], binding=binding_text(spec),
        group=at, write=written(out, shapes.GROUP),
        dictionary=DICTIONARY.format(dictionary=dictionary_text),
        items=stated_items(state_held, text, names, named))


def judge(run):
    state_held = state(run)
    held = [(int(number), spec["statement"], Path(spec["path"]), spec["kind"])
            for number, spec in sorted(state_held["proposals"].items(),
                                       key=lambda pair: int(pair[0]))]
    records = glossary()
    words = said(run, "words.md", "the owner's words are gone; build again")
    declined = (said(run, "declined.md", "") if (run / "declined.md").is_file()
                else "nothing was declined in this run")
    dictionary_text = (run / "dictionary.md").read_text()
    blocked = blocks((run / "export.md").read_text())
    text = dict(blocked)
    named, stopped, refused = recalled(run, state_held)
    if stopped:
        shards = [(name, spec["scope"],
                   [(uid, text.get(uid, "")) for uid in spec["items"]]
                   if spec["scope"] != SIBLINGS else siblings(held)[2])
                  for name, spec in state_held["shards"].items()]
        halved(run, state_held, stopped, held, words, declined, dictionary_text,
               records, shards, len(blocked))
        return 1
    # @req> REQ-82676674@FK_7la2Hg_XC fzv4pc
    if refused:
        spawned = []
        for label, faults in refused:
            print(f"{label}:")
            for fault in faults:
                print(f"  {fault}")
            (run / "returns" / "recall" / f"{label}.json").unlink(missing_ok=True)
            scope = state_held["shards"][state_held["recall"][label]["shard"]]["scope"]
            spawned.append(spawn(run, "recall", label, f"recall:{label}",
                                 shapes.recall(scope),
                                 state_held["models"]["recall"],
                                 PHASES["recall"]))
        print(f"{len(spawned)} recall agent(s) to spawn again: "
              f"{manifest(run, 'recall', spawned)}")
        return 1

    bounds = state_held["bounds"]
    index = indexed(records)
    plans = {}
    for number, spec in state_held["proposals"].items():
        floored = floor(index, spec["kind"], spec["statement"],
                        bounds["floor_k"])
        for uid, shared in floored:
            named[number].setdefault(uid, []).append(
                "floor: shares " + ", ".join(shared))
        names = sorted(named[number], key=lambda uid: (SIBLING.match(uid) is not None, uid))
        plans[number] = (names, grouped(names, bounds["judge_bound"],
                                        bounds["judge_group"]))
    counted = len(state_held["recall"]) + sum(
        1 if groups is None else len(groups) + 1
        for _, groups in plans.values())
    ceilinged(counted, bounds["agent_ceiling"])

    prompts, spawned = {}, []
    for number, (names, groups) in plans.items():
        spec = state_held["proposals"][number]
        state_held["named"][number] = {uid: named[number][uid] for uid in names}
        model = state_held["models"]["judge"]
        if groups is None:
            prompts[f"{number}"] = judge_prompt(
                run, number, spec, names, named[number], state_held, text,
                dictionary_text)
            state_held["judge"][number] = {"groups": None}
            spawned.append(spawn(run, "judge", number, f"judge:{number}",
                                 shapes.JUDGE, model, PHASES["judge"]))
            continue
        state_held["judge"][number] = {"groups": groups}
        for at, group in enumerate(groups, 1):
            prompts[f"{number}-g{at}"] = group_prompt(
                run, number, spec, at, group, named[number], state_held,
                text, dictionary_text)
            spawned.append(spawn(run, "judge", f"{number}-g{at}",
                                 f"group:{number}-g{at}", shapes.GROUP, model,
                                 PHASES["judge"]))
    lined(prompts, state_held["lines"])
    for stale in list((run / "prompts" / "judge").glob("*.md")) + list(
            (run / "returns" / "judge").glob("*.json")):
        stale.unlink()
    for name, body in prompts.items():
        (run / "prompts" / "judge" / f"{name}.md").write_text(body)
    saved(run, state_held)
    where = manifest(run, "judge", spawned)
    # @req+ REQ-18337665@WgqhACOIS9SM 5zcmh2
    split = sum(1 for _, groups in plans.values() if groups is not None)
    print(f"{len(plans)} proposal(s): {len(spawned)} judge agent(s), "
          f"{split} split into groups with a final judge to follow")
    for number, (names, groups) in sorted(plans.items(), key=lambda p: int(p[0])):
        print(f"  proposal {number}: {len(names)} item(s)"
              + (f" in {len(groups)} group(s)" if groups else ""))
    # @req- 5zcmh2
    print(f"  spawn     {where}")
    return 0


def group_returns(run, number, groups):
    lines, refused = [], []
    for at, group in enumerate(groups, 1):
        path = run / "returns" / "judge" / f"{number}-g{at}.json"
        data, why = read_return(path, shapes.GROUP)
        # @req> REQ-46162234@7Wvh6guc-Moy 4e2mbt
        if data is None:
            refused.append((f"{number}-g{at}", why))
            continue
        # @req+ REQ-26720462@_I_YaKWEsG65 fdqj6u
        foreign = sorted({finding["uid"] for finding in data["findings"]
                          if finding["uid"] not in group})
        if foreign:
            refused.append((f"{number}-g{at}", (f"names {', '.join(foreign)}, "
                                                "which the group did not state")))
            continue
        # @req- fdqj6u
        for finding in data["findings"]:
            lines.append(f"- {finding['uid']} [{finding['kind']}] clause: "
                         f"\"{finding['clause']}\" reason: {finding['reason']}")
        if not data["findings"]:
            lines.append(f"- group {at} returned no finding")
    return lines, refused


def final_prompt(run, number, spec, lines, dictionary_text):
    out = run / "returns" / "final" / f"{number}.json"
    # @req> REQ-68873467@8njvorO8kPuj 4eflcn
    return FINAL.format(
        number=number, statement=spec["statement"], binding=binding_text(spec),
        decide=DECIDE, write=written(out, shapes.JUDGE),
        dictionary=DICTIONARY.format(dictionary=dictionary_text),
        findings="\n".join(lines))


def final(run):
    state_held = state(run)
    dictionary_text = (run / "dictionary.md").read_text()
    model = state_held["models"]["judge"]
    prompts, spawned, again, waiting = {}, [], [], 0
    for number, spec in state_held["judge"].items():
        if spec["groups"] is None:
            continue
        lines, refused = group_returns(run, number, spec["groups"])
        # @req> REQ-82676674@FK_7la2Hg_XC fnjvuz
        for name, why in refused:
            print(f"{name}: {why}")
            (run / "returns" / "judge" / f"{name}.json").unlink(missing_ok=True)
            again.append(spawn(run, "judge", name, f"group:{name}",
                               shapes.GROUP, model, PHASES["judge"]))
        if refused:
            waiting += 1
            continue
        prompts[number] = final_prompt(
            run, number, state_held["proposals"][number], lines,
            dictionary_text)
        spawned.append(spawn(run, "final", number, f"final:{number}",
                             shapes.JUDGE, model, PHASES["judge"]))
    # @req> REQ-20121033@ilM5nhktsDvF zqtqps
    # @req> REQ-82676674@FK_7la2Hg_XC ukzxgc
    if again:
        print(f"{len(again)} group judge(s) to spawn again, {waiting} final "
              f"prompt(s) waiting on them: {manifest(run, 'judge', again)}")
        return 1
    # @req> REQ-56479390@PonL-ZUUzxq6 buupgw
    if not prompts:
        print("no proposal was split into groups; nothing to assemble")
        return 0
    lined(prompts, state_held["lines"])
    for name, body in prompts.items():
        (run / "prompts" / "final" / f"{name}.md").write_text(body)
    where = manifest(run, "final", spawned)
    # @req> REQ-56479390@PonL-ZUUzxq6 oapzeo
    print(f"{len(spawned)} final judge(s) to spawn: {where}")
    return 0


def describe(run):
    # @req+ REQ-21373303@o72_uf6TKpor qzk6eu
    state_held = state(run)
    declined = (said(run, "declined.md", "") if (run / "declined.md").is_file()
                else "")
    lines = []
    for number, spec in sorted(state_held["proposals"].items(),
                               key=lambda pair: int(pair[0])):
        path = run / "verdicts" / f"{number}.json"
        verdict, why = read_return(path, shapes.JUDGE)
        # @req> REQ-32019340@Ce9zMv1R_f5m zmwc5n
        if verdict is None:
            raise SystemExit(f"{path}: proposal {number}'s verdict {why}; run "
                             "`verdicts.py` once the judges return")
        lines.append(f"### proposal {number}\n\n{spec['statement']}\n")
        # @req> REQ-36901100@tEyoD1WQpj_b 4flmpq
        if not spec["trace"]:
            raise SystemExit(f"proposal {number} traces to no passage of the "
                             "owner's words; record its `trace` in run.yaml")
        lines.append("Traces to: " + "; ".join(f"“{one}”"
                                               for one in spec["trace"]) + "\n")
        for entry in verdict["covered_by"]:
            lines.append(f"- covered {entry['covers']} by "
                         f"{', '.join(entry['uids'])}: {entry['reason']}")
        for entry in verdict["conflicts"]:
            lines.append(f"- conflicts with {entry['uid']}: {entry['reason']}")
        for entry in verdict["relations"]:
            lines.append(f"- {entry['kind']} {entry['target']}: {entry['reason']}")
        for entry in verdict["nearest"]:
            lines.append(f"- nearest {entry['uid']}: {entry['why_not']}")
        for entry in verdict["values"]:
            lines.append(f"- value {entry['value']}: "
                         f"{entry['belongs_with'] or 'no home'}, {entry['reason']}")
        for entry in verdict["words"]:
            lines.append(f"- word {entry['word']}: "
                         f"{entry['defined_by'] or 'no term'}, {entry['reason']}")
        for entry in verdict["faults"]:
            lines.append(f"- fault {entry['fault']}: {entry['reason']}")
        for question in verdict["questions"]:
            lines.append(f"- question: {question}")
        lines.append("")
    lines.append("### declined\n")
    lines.append(declined or "Nothing was declined in this run.")
    print("\n".join(lines))
    # @req- qzk6eu
    return 0


def main(argv=None):
    parsed = argparse.ArgumentParser()
    sub = parsed.add_subparsers(dest="command", required=True)

    made = sub.add_parser("build")
    made.add_argument("--run", required=True, metavar="DIR")
    made.add_argument("--chars", type=int, default=SHARD_CHARS)
    made.add_argument("--items", type=int, default=SHARD_ITEMS)
    made.add_argument("--lines", type=int, default=PROMPT_LINES)
    made.set_defaults(handler=lambda args: build(Path(args.run), args.chars,
                                                 args.items, args.lines))
    for name, handler in (("judge", judge), ("final", final),
                          ("describe", describe)):
        step = sub.add_parser(name)
        step.add_argument("--run", required=True, metavar="DIR")
        step.set_defaults(handler=lambda args, handler=handler: handler(
            Path(args.run)))

    args = parsed.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (corpus.ReqctlError, OSError) as unreadable:
        sys.exit(f"{Path(__file__).name}: {unreadable}")
