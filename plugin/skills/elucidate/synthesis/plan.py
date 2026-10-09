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

from reqctl import corpus, settings, validate, write

ANCHOR = re.compile(
    rf'^<a id="((?:{corpus.KINDS})-\d{{8}}|{corpus.NAME})"></a>$', re.MULTILINE)
RELATION = re.compile(rf"^- (?:{'|'.join(write.RELATIONS)}) (REQ-\d{{8}})$")
USED_BY = "- used by: "
TOKEN = re.compile(r"\$\{[^}]*\}?")
SIBLING = re.compile(r"^proposal (\d+)$")
PLUGIN = Path(".claude-plugin") / "plugin.json"
BINDS = "binds"
CRITERIA = "criteria"
TRACE = "trace"
FINDINGS = "coverage.yml"
STATE = "build.json"
REVIEWED = "review.json"
REMOVED = "removed.json"
DECLINED = "declined_practices"
OBLIGATION = {"REQ": "requirements", "GUARD": "guards"}
KIND_NAME = {"REQ": "requirement", "GUARD": "guard"}
SIBLINGS = "siblings"
SHARD_CHARS = 25_000
SHARD_ITEMS = 100
PROMPT_LINES = 2000
STATED = "stated.json"
CHALLENGERS = ("coverage", "recall", "judge")

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
# @req> REQ-36422345@O-3IKmoFSYSG ghenbw
WRITE = """Write the result as JSON matching this shape to {out} with the Write tool,
then return exactly what you wrote. Do not narrate.

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

# @req> REQ-36422345@O-3IKmoFSYSG aw3cqu
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
restate the set, do not summarise before or after. Once it is written, return
exactly what you wrote in it.
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
    # @req> REQ-89404055@_nDL-mGj_X7w grxatb
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
    # @req+ REQ-67476912@Qne_JotHDdnY 47tdge
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


def spawn(run, folder, name, label, shape, held):
    return {"label": label, "path": str(run / "prompts" / folder / f"{name}.md"),
            "out": str(run / "returns" / folder / f"{name}.json"),
            "schema": shape, **held}


def inline(label, prompt, shape, kind, held):
    return {"label": label, "prompt": prompt, "schema": shape, "agent": kind,
            **held}


def registered(name):
    plugin = Path(sys.argv[0]).absolute().parents[3] / PLUGIN
    if not plugin.is_file():
        return name
    return f"{read_json(plugin)['name']}:{name}"


def named_item(records, name):
    found = [(uid, data) for uid, data in records.items()
             if corpus.kind_of(uid, data) == "data" and data.get("name") == name]
    # @req> REQ-68855089@GA2RLpoitDV5 t6wldu
    if len(found) != 1:
        raise SystemExit(
            f"the corpus defines {'no' if not found else 'more than one'} "
            f"data item named {name}. Mint one first.")
    return found[0]


def agent(name, held):
    model, effort = (held[name].get(field) for field in ("model", "effort"))
    # @req> REQ-96661837@HbvreaRTySWH hz4zip
    if bool(model) != bool(effort):
        raise SystemExit(f"elucidate_agents' {name} entry states a model "
                         "without an effort, or an effort without a model; "
                         "state both")
    # @req> REQ-82356895@juJepJj5Wt1K yj46qn
    if not isinstance(model, str) or not settings.PINNED.fullmatch(model):
        raise SystemExit(f"elucidate_agents' {name} entry names its model as "
                         f"{model!r}, which is not a pinned model ID such as "
                         "claude-opus-5-5")
    return {"model": model, "effort": effort}


def read_json(path):
    # @req+ REQ-29234402@b5_8tR6bNR44 vvxruf
    try:
        held = json.loads(corpus.read_text(path))
    except (ValueError, RecursionError) as broken:
        raise corpus.ReqctlError(f"{path}: not JSON -- {broken}") from broken
    if not isinstance(held, dict):
        raise corpus.ReqctlError(f"{path}: holds {type(held).__name__}, not the "
                                 "JSON object the run writes")
    return held
    # @req- vvxruf


def used(run):
    path = run / STATED
    return read_json(path) if path.is_file() else {}


def configured(run, uses):
    where, overrides = settings.read(corpus.find_root())
    taken = {key: value for key, value in overrides.items()
             if key.startswith(uses)}
    # @req> REQ-75041625@fdufkvO5WYz7 rx7gce
    for key, value in sorted(taken.items()):
        print(f"{key}: {json.dumps(value)}, stated by {where}")
    # @req+ REQ-41970990@LllsbvPcoF0q 6rmd3o
    kept = {key: held for key, held in used(run).items()
            if not key.startswith(uses)}
    corpus.atomic_write(run / STATED, json.dumps(
        kept | {key: {"value": value, "file": where}
                for key, value in taken.items()}, indent=1) + "\n")
    # @req- 6rmd3o
    return overrides


def dimensions(root, records):
    held = {}
    for name in corpus.binding_dimensions(root):
        uid, data = named_item(records, name)
        # @req+ REQ-29846444@V-kcyDuwiOZS zjcgv2
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
    # @req> REQ-77623729@vjmOfyXPn_43 elfpax
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
        # @req+ REQ-83454000@CAS-4S3kCWy5 2qoccn
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
        # @req+ REQ-50522674@MIzqcKrm_Ge8 6ahzuj
        stray = chosen - members
        if stray:
            raise SystemExit(
                f"{path}: proposal {number} binds to {', '.join(sorted(stray))}"
                f", which the {name} data item does not define. The members "
                f"are {', '.join(sorted(members))}, or `all`.")
        # @req- 6ahzuj
        # @req> REQ-83454000@CAS-4S3kCWy5 reughj
        if str(number) in held:
            raise SystemExit(
                f"{path}: {name} records proposal {number} twice -- YAML keeps "
                "both where one key is written `3` and the other `\"3\"`, and "
                "which of them governs is not this file's to decide.")
        held[str(number)] = chosen
    return held


def settled(run, dims):
    path, read = recorded(run)
    # @req> REQ-30037092@wJeLHn0mRAOm 6bxg5g
    if not path.is_file():
        raise SystemExit(
            f"{path}: a run records the members each proposal binds to, under "
            f"`{BINDS}`, keyed by dimension and then by proposal number. "
            "Step 1 asks the owner; nothing else settles it.")
    # @req+ REQ-83454000@CAS-4S3kCWy5 2uanuo
    said = read.get(BINDS)
    if not isinstance(said, dict):
        raise SystemExit(
            f"{path}: `{BINDS}` maps each of {', '.join(sorted(dims))} to the "
            "proposal numbers and the members each binds to, as "
            "`<dimension>:` then `2: [<member>]`, or `all`.")
    # @req- 2uanuo
    held = {}
    for name, (_, members) in dims.items():
        # @req+ REQ-30037092@wJeLHn0mRAOm avbh7j
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
    # @req> REQ-73044308@nYsIcKmI8XV_ 6sk2ng
    if not dims:
        return {}
    # @req+ REQ-92272837@JyGx2T7SRoWI owkvnp
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
        # @req+ REQ-58008138@PXcNItNpUpth usq427
        for token in TOKEN.finditer(statement):
            if not corpus.PARAM_REF.fullmatch(token.group()):
                raise SystemExit(
                    f"proposal {number} carries {token.group()}, which is not "
                    "a reference -- the form is ${name} or ${name.member}. One "
                    "that does not parse reads here as no reference at all, "
                    "which is how a statement binding to every member reads.")
        stray = unresolved(records, statement)
        if stray:
            named = {corpus.PARAM_REF.fullmatch(ref).group(1) for ref in stray}
            raise SystemExit(
                f"proposal {number} carries {', '.join(sorted(stray))}, which "
                "the corpus resolves to no parameter, data item or member of "
                "one. A reference to nothing binds nothing rather than failing "
                "to parse, so it reads here as binding to every member."
                + "".join(f" The {name} members are {', '.join(sorted(members))}."
                          for name, (_, members) in sorted(dims.items())
                          if name in named))
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
            # @req> REQ-30037092@wJeLHn0mRAOm 5nfu7e
            if str(number) not in stated:
                raise SystemExit(
                    f"proposal {number}: {run / 'run.yaml'} records no {name} "
                    "for it. Every requirement states one for every dimension, "
                    "and all is an answer rather than a silence.")
            wanted = stated[str(number)]
            # @req> REQ-16901746@96PSBu5QPVOP 7yvsul
            if "" in written:
                raise SystemExit(
                    f"proposal {number} references the {name} data item "
                    "without naming a member, which states no binding. Name "
                    "the member, or reference nothing and record the proposal "
                    "as all.")
            # @req> REQ-50522674@MIzqcKrm_Ge8 2rsevi
            # @req+ REQ-54045696@m7842dVOG3jf f57qfn
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
            # @req- f57qfn
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
        # @req> REQ-73186885@Q7CKwi3s629S twr3xe
        if number in numbered:
            raise SystemExit(
                f"{numbered[number]} and {path.name} are both numbered "
                f"{number}. Renumber one of them.")
        numbered[number] = path.name
        statement = " ".join(path.read_text().split())
        kind = obliged(statement)
        # @req> REQ-46098858@EClgM52w1AQK ny4y6f
        if kind is None:
            raise SystemExit(
                f"{path.name}: the statement names neither the product nor the "
                "build as the subject of its obligation. State `the product "
                "shall` or `the build shall`.")
        held.append((number, statement, path, kind))
    # @req> REQ-38776024@Lk5rVncqrTqU trxd62
    if not held:
        raise SystemExit(f"{run / 'proposals'}: no proposal to challenge")
    return held


def said(run, name, missing):
    path = run / name
    if not path.is_file():
        raise SystemExit(f"{path}: {missing}")
    return " ".join(path.read_text().split())


def linted(held, store):
    # @req+ REQ-48622606@TQRC6NoGNrgi kjkm4f
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


def keyed(path, name, record, held):
    numbers = {str(number) for number, _, _, _ in held}
    keys = {}
    for key, value in record.items():
        # @req> REQ-52230032@ZV7FwJtFuqi3 hnvgee
        # @req> REQ-38877821@Rf8VoUrZ9-27 kn326i
        if str(key) in keys:
            raise SystemExit(
                f"{path}: `{name}` records proposal {key} twice, once written "
                f"{key} and once \"{key}\". Keep one of them.")
        # @req> REQ-71318073@StYqTfNyHE39 scbfuj
        # @req> REQ-30554264@6JOa752EzDE9 bjxcpn
        if str(key) not in numbers:
            raise SystemExit(
                f"{path}: `{name}` records {key!r}, which names no proposal the "
                "run holds. Renumber the record, or write the proposal.")
        keys[str(key)] = value
    return keys


def traced(run, words, held):
    path, read = recorded(run)
    # @req+ REQ-66894246@1OH-VnSwvnpy rc5ai4
    traces = {} if read.get(TRACE) is None else read[TRACE]
    # @req> REQ-28473555@fDR67hlkVPAc do2uo3
    if not isinstance(traces, dict):
        raise SystemExit(
            f"{path}: `{TRACE}` maps a proposal number to the passages of the "
            "owner's words it traces to, as `2: [\"undo for bulk\"]`.")
    # @req- rc5ai4
    traces = keyed(path, TRACE, traces, held)
    spoken = _coverage.plain(_coverage.spoken(words))
    stated = {}
    for number, _, _, _ in held:
        # @req+ REQ-28473555@fDR67hlkVPAc fw5ou4
        passages = traces.get(str(number), [])
        if not isinstance(passages, list) or not all(
                isinstance(one, str) and one.strip() for one in passages):
            raise SystemExit(
                f"{path}: `{TRACE}` states {passages!r} for proposal {number}. "
                "The form is a list of passages quoted from the owner's words.")
        # @req- fw5ou4
        # @req> REQ-83939497@o4e6KsfHMIgp rfwtjo
        for passage in passages:
            if not _coverage.quoted(spoken, _coverage.spoken(passage)):
                raise SystemExit(
                    f"proposal {number} traces to {passage!r}, which the "
                    "owner's words do not hold. Quote what they wrote, or "
                    "decline the proposal.")
        stated[str(number)] = [" ".join(one.split()) for one in passages]
    return stated


def stated(run, held_proposals):
    path, read = recorded(run)
    held = read.get(CRITERIA)
    if held is None:
        return {}
    # @req+ REQ-37767588@63pbAfEkzoHI viljjd
    # @req> REQ-17236422@y4j5vrrt22rY pz52iy
    if not isinstance(held, dict):
        raise SystemExit(
            f"{path}: `{CRITERIA}` maps a proposal number to the criteria it "
            "carries, as `2: [\"given a run | when it runs | then it holds\"]`. "
            "A proposal carrying none is left out rather than written empty.")
    carried = {}
    for number, value in keyed(path, CRITERIA, held, held_proposals).items():
        if not isinstance(value, list) or not all(
                isinstance(one, str) for one in value):
            raise SystemExit(
                f"{path}: `{CRITERIA}` states {value!r} for proposal {number}. "
                "The form is a list of `given | when | then` strings.")
        carried[number] = list(value)
    # @req- viljjd
    return carried


def packed(name, held, chars, items):
    # @req+ REQ-39970698@jhE5HIT5u-ty s5jtgy
    shards, holding, weight = [], [], 0
    for uid, block in held:
        # @req> REQ-43761464@FjNB-AZH1A0m n7x4xq
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
    # @req+ REQ-90454282@M0OdZ2RxH5qS yp35nb
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
    # @req+ REQ-83103011@x2ejel0K651Z 6po76w
    if len(held) < 2:
        return None
    return (SIBLINGS, SIBLINGS, [(f"proposal {number}",
                                  f"proposal {number}: {statement}\n")
                                 for number, statement, _, _ in held])
    # @req- 6po76w


def batched(numbers, batch):
    # @req+ REQ-94426583@8JHtrZp73dHb eefhta
    # @req> REQ-32866040@hbsvPKXBNujz f2uvmw
    return [numbers[at:at + batch] for at in range(0, len(numbers), batch)]
    # @req- eefhta


def judged_by(held, scope):
    return [number for number, _, _, kind in held
            if scope == SIBLINGS or OBLIGATION[kind] == scope]


def dictionary(records):
    lines = []
    # @req> REQ-48772986@_O1niNys_-pl 4xoc6j
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
    # @req+ REQ-18405752@FCxc3x0E2EZU et2jhv
    # @req+ REQ-29895268@XzYj6vWL1dPl cq5zif
    # @req> REQ-22034470@UtTX-sX116Fw oodadq
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
    # @req> REQ-48148587@wA7bmyxqWF2Z aky7xw
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


def against(run, number):
    return "".join(path.read_text() for path in sorted(
        (run / "prompts" / "judge").glob(f"{number}*.md"))
        if path.stem.partition("-g")[0] == number)


def owner(spawned):
    return spawned["label"].partition(":")[2].partition("-g")[0]


def cleared(run):
    # @req+ REQ-95375719@-TYbW5JhiwAf ey5733
    findings = run / FINDINGS
    corpus.remove(findings, missing_ok=True)
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
    # @req+ REQ-47744588@ZrmtfTL6RUOL a7rnsw
    # @req+ REQ-80500447@cWHS2ihd6kMV omzjq4
    # @req> REQ-24569953@LsZU4Go81cg8 ssc6p2
    return COVERAGE.format(
        words=words, declined=declined, proposals=written,
        criteria=CARRIES.format(stated=lines) if lines else "", found=found,
        names=", ".join(f"`{name}`" for name in NAMES))
    # @req- omzjq4
    # @req- a7rnsw


def manifested(run, name):
    return run / "workflow" / f"{name}.json"


def manifest(run, name, prompts):
    held, listed = {}, []
    for one in prompts:
        shape = next((key for key, value in held.items() if value == one["schema"]),
                     None)
        if shape is None:
            shape = f"shape-{len(held) + 1}"
            held[shape] = one["schema"]
        listed.append({**one, "schema": shape})
    where = manifested(run, name)
    corpus.atomic_write(where, json.dumps({"shapes": held, "prompts": listed},
                                          indent=1) + "\n")
    return where


def state(run):
    path = run / STATE
    # @req> REQ-32019340@Ce9zMv1R_f5m fctrpm
    if not path.is_file():
        raise SystemExit(f"{path}: the run was not built; run `plan.py build` "
                         "first")
    return read_json(path)


def saved(run, held):
    corpus.atomic_write(run / STATE, json.dumps(held, indent=1) + "\n")


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
            # @req> REQ-23060027@zeNeSryv-0-1 6y5rvz
            spawned.append(spawn(run, "recall", label, f"recall:{label}",
                                 shapes.recall(scope),
                                 state_held["agents"]["recall"]))
            state_held["recall"][label] = {"shard": name, "batch": at,
                                          "proposals": chunk}
    return prompts, spawned, texts


def build(run, chars, items, lines=PROMPT_LINES):
    # @req+ REQ-54959279@L0m_T7xUklMM rwweso
    # @req> REQ-36523706@OK4q4pOlvZRH 7e7svw
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
    # @req+ REQ-40447106@_7d9O2HDnoPr zmbxny
    # @req+ REQ-75041625@fdufkvO5WYz7 of23ld
    overrides = configured(run, ("challenge_bounds.", *(
        f"{settings.AGENTS}.{name}." for name in CHALLENGERS)))
    bounds = settings.quantities(overrides, "challenge_bounds")
    crew = settings.table(overrides, settings.AGENTS)
    # @req- of23ld
    # @req- zmbxny
    # @req> REQ-23060027@zeNeSryv-0-1 dxtamn
    agents = {name: agent(name, crew) for name in CHALLENGERS}
    settled_on = binding(run, held, corpus.find_root(), records)
    traces = traced(run, words, held)
    carried = stated(run, held)
    linted(held, store)
    exported_text = exported()
    blocked = blocks(exported_text)
    # @req> REQ-40454564@7Yw4h6spRiXB kostqz
    shards = partitioned(blocked, held, chars, items)
    sibling = siblings(held)
    if sibling is not None:
        shards.append(sibling)
    counted = sum(len(batched(judged_by(held, scope), bounds["recall_batch"]))
                  for _, scope, _ in shards) + len(held)
    ceilinged(counted, bounds["agent_ceiling"])

    state_held = {
        "agents": agents, "bounds": bounds, "lines": lines,
        "proposals": {str(number): {"kind": kind, "statement": statement,
                                    "path": str(path),
                                    "binding": settled_on.get(number),
                                    "trace": traces.get(str(number), [])}
                      for number, statement, path, kind in held},
        "shards": {name: {"scope": scope, "items": [uid for uid, _ in block],
                          "batch": bounds["recall_batch"]}
                   for name, scope, block in shards},
        "recall": {}, "judge": {}, "named": {},
    }
    dictionary_text = dictionary(records)
    prompts, spawned, texts = recall_prompts(
        run, held, state_held, shards, None, words, declined, dictionary_text,
        records, len(blocked))
    lined(prompts, lines)

    # @req> REQ-81667762@82D0B66GuW3u ef2rgh
    for folder in ("prompts/recall", "prompts/judge", "prompts/final",
                   "returns/recall", "returns/judge", "returns/final",
                   "verdicts", "workflow"):
        corpus.make_folder(run / folder)
    for stale in list((run / "prompts" / "recall").glob("*.md")) + list(
            (run / "returns" / "recall").glob("*.json")):
        corpus.remove(stale)
    for name, body in prompts.items():
        corpus.atomic_write(run / "prompts" / "recall" / f"{name}.md", body)
    for name, text in texts.items():
        corpus.atomic_write(run / "shards" / f"{name}.md", text)
    corpus.atomic_write(run / "dictionary.md", dictionary_text)
    saved(run, state_held)
    where = manifest(run, "recall", spawned)
    asked = coverage(run, words, declined, held, carried)
    # @req> REQ-23060027@zeNeSryv-0-1 ukljdu
    reading = manifest(run, "coverage", [inline(
        "coverage", asked, shapes.COVERAGE, registered("coverage"),
        agents["coverage"])])
    cleared(run)
    corpus.atomic_write(run / "export.md", exported_text)
    # @req> REQ-16868696@xXhoCmAQTytn js66h5
    print(f"{len(held)} proposal(s) over {len(shards)} shard(s) in batches of "
          f"{bounds['recall_batch']}: {len(spawned)} recall agent(s), then one "
          "judge each")
    print(f"  spawn     {where}")
    print(f"  prompts   {run / 'prompts' / 'recall'}/<shard>-b<n>.md")
    # @req> REQ-23060027@zeNeSryv-0-1 citfb2
    print(f"  coverage  {reading}, spawned once the answers are in")
    return 0
    # @req- rwweso


def read_return(path, shape):
    if not path.is_file():
        return None, "returned nothing"
    try:
        data = json.loads(path.read_text())
    except (ValueError, RecursionError) as broken:
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
        # @req+ REQ-25592483@hyAvD5E-8sMd vamoo7
        stated = {str(one) for one in spec["proposals"]}
        seen = {str(entry["proposal"]) for entry in data["results"]}
        faults = [f"omits an entry for proposal {number}"
                  for number in sorted(stated - seen, key=int)]
        faults += [f"answers proposal {number}, which the prompt did not carry"
                   for number in sorted(seen - stated)]
        held = set(state_held["shards"][spec["shard"]]["items"])
        for entry in data["results"]:
            for hit in entry["hits"]:
                # @req+ REQ-94538693@JZejoa-2lHXV 4xyeq2
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
    # @req+ REQ-19832934@Mk7Pla2kkx3i moar22
    for name, why in sorted(stopped.items()):
        batch = state_held["shards"][name]["batch"]
        # @req> REQ-33633053@mo4XdZGYpUJ5 mrzj65
        if batch < 2:
            raise SystemExit(
                f"{why}, and its batch is already one proposal, so the shard "
                "is too large for one reading. Build again with a smaller "
                "--chars.")
        state_held["shards"][name]["batch"] = (batch + 1) // 2
        for label in [one for one, spec in state_held["recall"].items()
                      if spec["shard"] == name]:
            del state_held["recall"][label]
            corpus.remove(run / "prompts" / "recall" / f"{label}.md",
                          missing_ok=True)
            corpus.remove(run / "returns" / "recall" / f"{label}.json",
                          missing_ok=True)
    prompts, spawned, _ = recall_prompts(
        run, held, state_held, shards, set(stopped), words, declined,
        dictionary_text, records, total)
    lined(prompts, state_held["lines"])
    for name, body in prompts.items():
        corpus.atomic_write(run / "prompts" / "recall" / f"{name}.md", body)
    saved(run, state_held)
    where = manifest(run, "recall", spawned)
    # @req- moar22
    # @req+ REQ-82676674@r-c5TnDW5gbD vpqdb6
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
    # @req+ REQ-80191784@ahIlNt8S6BrF f4rqof
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
    # @req> REQ-30631052@xqJkQgCU4pW_ jyes6a
    return JUDGE.format(
        number=number, statement=spec["statement"], binding=binding_text(spec),
        decide=DECIDE, write=written(out, shapes.JUDGE),
        dictionary=DICTIONARY.format(dictionary=dictionary_text),
        items=stated_items(state_held, text, names, named)
        or "(nothing was named for this proposal)\n")


def grouped(names, bound_at, group):
    # @req+ REQ-48762557@jm9fn2mpwhml 5f3ye7
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
    # @req> REQ-82676674@r-c5TnDW5gbD fzv4pc
    if refused:
        spawned = []
        for label, faults in refused:
            print(f"{label}:")
            for fault in faults:
                print(f"  {fault}")
            corpus.remove(run / "returns" / "recall" / f"{label}.json",
                          missing_ok=True)
            scope = state_held["shards"][state_held["recall"][label]["shard"]]["scope"]
            # @req> REQ-23060027@zeNeSryv-0-1 spkcng
            spawned.append(spawn(run, "recall", label, f"recall:{label}",
                                 shapes.recall(scope),
                                 state_held["agents"]["recall"]))
        print(f"{len(spawned)} recall agent(s) to spawn again: "
              f"{manifest(run, 'recall', spawned)}")
        return 1

    index = indexed(records)
    # @req> REQ-40447106@_7d9O2HDnoPr ksolp2
    bounds = state_held["bounds"]
    plans = {}
    for number, spec in state_held["proposals"].items():
        floored = floor(index, spec["kind"], spec["statement"], bounds["floor_k"])
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
        # @req> REQ-23060027@zeNeSryv-0-1 tpcwue
        judging = state_held["agents"]["judge"]
        if groups is None:
            prompts[f"{number}"] = judge_prompt(
                run, number, spec, names, named[number], state_held, text,
                dictionary_text)
            state_held["judge"][number] = {"groups": None}
            spawned.append(spawn(run, "judge", number, f"judge:{number}",
                                 shapes.JUDGE, judging))
            continue
        state_held["judge"][number] = {"groups": groups}
        for at, group in enumerate(groups, 1):
            prompts[f"{number}-g{at}"] = group_prompt(
                run, number, spec, at, group, named[number], state_held,
                text, dictionary_text)
            spawned.append(spawn(run, "judge", f"{number}-g{at}",
                                 f"group:{number}-g{at}", shapes.GROUP,
                                 judging))
    lined(prompts, state_held["lines"])
    for stale in list((run / "prompts" / "judge").glob("*.md")) + list(
            (run / "returns" / "judge").glob("*.json")) + list(
            (run / "returns" / "final").glob("*.json")):
        corpus.remove(stale)
    for name, body in prompts.items():
        corpus.atomic_write(run / "prompts" / "judge" / f"{name}.md", body)
    # @req+ REQ-42199988@RmH4Z1Ifs4oQ nfg7dv
    standing = set()
    for verdict in sorted((run / "verdicts").glob("*.json")):
        number, judged_against = verdict.stem, verdict.with_suffix(".prompt")
        if number not in plans:
            why = "the run no longer holds proposal " + number
        elif (judged_against.is_file()
                and judged_against.read_text() == against(run, number)
                and read_return(verdict, shapes.JUDGE)[0] is not None):
            standing.add(number)
            state_held["judge"][number]["stands"] = True
            continue
        else:
            why = "the prompt it was judged against has moved"
        corpus.remove(verdict)
        corpus.remove(judged_against, missing_ok=True)
        print(f"retired {verdict.name}: {why}")
    spawned = [one for one in spawned if owner(one) not in standing]
    # @req- nfg7dv
    saved(run, state_held)
    where = manifest(run, "judge", spawned)
    # @req+ REQ-18337665@j18ypL2DSMhn 5zcmh2
    split = sum(1 for _, groups in plans.values() if groups is not None)
    print(f"{len(plans)} proposal(s): {len(spawned)} judge agent(s), "
          f"{split} split into groups with a final judge to follow, "
          f"{len(standing)} verdict(s) standing")
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
        # @req+ REQ-26720462@C-3RqWsFVbDL fdqj6u
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
    # @req> REQ-68873467@3-Wc7R2vtu7- 4eflcn
    return FINAL.format(
        number=number, statement=spec["statement"], binding=binding_text(spec),
        decide=DECIDE, write=written(out, shapes.JUDGE),
        dictionary=DICTIONARY.format(dictionary=dictionary_text),
        findings="\n".join(lines))


def final(run):
    state_held = state(run)
    dictionary_text = (run / "dictionary.md").read_text()
    # @req> REQ-23060027@zeNeSryv-0-1 pxmf5e
    judging = state_held["agents"]["judge"]
    prompts, spawned, again, waiting = {}, [], [], 0
    for number, spec in state_held["judge"].items():
        # @req> REQ-42199988@RmH4Z1Ifs4oQ cu4vz2
        if spec["groups"] is None or spec.get("stands"):
            continue
        lines, refused = group_returns(run, number, spec["groups"])
        # @req> REQ-82676674@r-c5TnDW5gbD fnjvuz
        for name, why in refused:
            print(f"{name}: {why}")
            corpus.remove(run / "returns" / "judge" / f"{name}.json",
                          missing_ok=True)
            again.append(spawn(run, "judge", name, f"group:{name}",
                               shapes.GROUP, judging))
        if refused:
            waiting += 1
            continue
        prompts[number] = final_prompt(
            run, number, state_held["proposals"][number], lines,
            dictionary_text)
        spawned.append(spawn(run, "final", number, f"final:{number}",
                             shapes.JUDGE, judging))
    # @req> REQ-20121033@iowcBoRYOX0g zqtqps
    # @req> REQ-82676674@r-c5TnDW5gbD ukzxgc
    if again:
        print(f"{len(again)} group judge(s) to spawn again, {waiting} final "
              f"prompt(s) waiting on them: {manifest(run, 'judge', again)}")
        return 1
    # @req> REQ-56479390@CzOsA-KyXyrW buupgw
    if not prompts:
        print("no proposal was split into groups; nothing to assemble")
        return 0
    lined(prompts, state_held["lines"])
    for name, body in prompts.items():
        corpus.atomic_write(run / "prompts" / "final" / f"{name}.md", body)
    where = manifest(run, "final", spawned)
    # @req> REQ-56479390@CzOsA-KyXyrW oapzeo
    print(f"{len(spawned)} final judge(s) to spawn: {where}")
    return 0


def describe(run):
    # @req+ REQ-21373303@Y7R6bZxRXU-G qzk6eu
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
        # @req> REQ-36901100@Mr5MaJ4j9RRr 4flmpq
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
    # @req+ REQ-20454019@BJxxS0ixzdXK vxerce
    lines += (([declined] if declined else []) + declined_practices(run)
              or ["Nothing was declined in this run."])
    # @req- vxerce
    # @req+ REQ-41970990@LllsbvPcoF0q 6vslgs
    overrides = used(run)
    if overrides:
        lines += ["", "### settings", ""] + [
            f"- {key}: {json.dumps(held['value'])}, stated by {held['file']}"
            for key, held in sorted(overrides.items())]
    # @req- 6vslgs
    print("\n".join(lines))
    # @req- qzk6eu
    return 0


# @req> REQ-51975077@c_HnzFhrYbl_ z6krrc
def removed(run):
    path = run / REMOVED
    if not path.is_file():
        return []
    held, why = read_return(path, shapes.REVIEW)
    if held is None:
        raise SystemExit(f"{path}: the practices removed on the owner's answer "
                         f"{why}")
    return held["practices"]


def declined_practices(run):
    # @req+ REQ-20454019@BJxxS0ixzdXK mkqci7
    path, read = recorded(run)
    numbers = read.get(DECLINED) or []
    if not isinstance(numbers, list):
        raise SystemExit(f"{path}: `{DECLINED}` states {numbers!r}. The form "
                         "is a list of the review's practice numbers, as "
                         "`[1, 3]`.")
    # @req> REQ-51975077@c_HnzFhrYbl_ px3ye3
    held = removed(run)
    review, why = read_return(run / REVIEWED, shapes.REVIEW)
    if numbers and review is None:
        raise SystemExit(f"{path}: `{DECLINED}` names practices, and "
                         f"{run / REVIEWED} {why}")
    for number in numbers:
        if type(number) is not int or not 1 <= number <= len(review["practices"]):
            raise SystemExit(f"{path}: `{DECLINED}` names {number!r}; the review "
                             f"holds practices 1 to {len(review['practices'])}")
        held.append(review["practices"][number - 1])
    return [f"- a practice of the best-in-class review, declined: "
            f"{practice['practice']} ({', '.join(practice['leaders'])})"
            for practice in held]
    # @req- mkqci7


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
    # @req+ REQ-29234402@b5_8tR6bNR44 ownlqe
    try:
        # @req> REQ-24406170@ffuKefeAdU7p yny6rh
        sys.exit(corpus.atomically(main))
    except (corpus.ReqctlError, OSError, UnicodeError) as unreadable:
        sys.exit(f"{Path(__file__).name}: " + " ".join(str(unreadable).split()))
    except SystemExit as stop:
        if isinstance(stop.code, str):
            sys.exit(f"{Path(__file__).name}: " + " ".join(stop.code.split()))
        raise
    # @req- ownlqe
