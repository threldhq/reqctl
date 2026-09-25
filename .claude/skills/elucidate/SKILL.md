---
name: elucidate
description: >
  Take one idea or a bulk list of ideas from the owner and carry them to a pull
  request proposing requirements: convert them to EARS statements, challenge the
  result, reconcile against the approved corpus, create, approve and baseline.
  Use whenever the owner offers ideas, features, wants, or rough intentions to be
  turned into requirements -- including a single sentence, and including hedged
  thinking-out-loud ("thinking the export should...", "I'd like undo for...")
  -- and whenever they say elucidate. Not for running reqctl operations on their
  own -- cutting a baseline, revising or querying the corpus -- with no new idea
  in hand.
---

<!-- @req> REQ-38288492@1yCh_1wG8N-l wtuxki -->
# Elucidate

Ideas in, a requirements pull request out. Nothing here approves anything: the
merge is the approval, and only the owner merges.

```
1  convert     the owner's words become EARS statements   inline, no subagent
2  challenge   recall over every shard, then one judge each   agents by the corpus's roles
3  approve     reqctl, then the pull request              owner reviews and merges
```

This file says only what is not already said elsewhere. EARS shape, the
schema, parameter references and relations are enforced by `reqctl validate`,
which prints the five forms when a statement misses the shape. Atomicity,
verifiability and no-rationale are stated in
`requirements/schemas/requirement.schema.yaml` as prose -- the drafter's to
check, not validate's. Read them there.

A run leaves its state under `.elucidate/<run>/`, never committed. You write
`words.md`, `declined.md` and `proposals/NN.md`, each proposal its own file
holding its statement and nothing else, numbered because the number is what a
verdict answers -- the whole file is the statement, so a heading or a criterion
written there becomes part of it. `run.yaml` holds what the corpus settled,
what step 1 deferred to step 2's report, the questions asked with the owner's
answers, and three maps keyed by proposal number, each read by a script rather
than a reader, so it parses as YAML or `plan.py build` refuses: `binds`,
`criteria` and `trace`. `binds` is keyed by dimension first and then by
proposal number, and a corpus nominating no dimension needs no `binds` at
all. A proposal's criteria are a list of `given | when |
then` strings, and its trace a list of passages quoted from the owner's words;
a proposal carrying no criteria is left out of that map rather than written
empty. `synthesis/plan.py` writes the rest -- `export.md`, `shards/`,
`dictionary.md`, `prompts/`, `build.json`, `workflow/` -- and the agents fill
`returns/`, which the scripts read into `verdicts/`. The directory is made
fresh at the start of a run and goes at the end, so an abandoned one is never
inherited.

## 1 -- Convert

Run this yourself. Do not spawn an agent: the owner's words are already here,
and so is the owner.

Their words are the whole input. Not the README -- it describes an aspiration
and carries no approval, so feeding it in authors requirements against a second
statement of what is true. The approved corpus is the only legitimate
background, it enters at step 2, and while it is empty the correct amount of
background is none. The glossary is the exception: run `reqctl list term` before
drafting, and `reqctl context` the ones your statements lean on. It is names,
aliases and definitions, never obligations, so it cannot author a statement --
and without it a word the corpus already fixes is proposed again as a new one.

Needing more context is not a reason to go and find it. It means you have
produced a question for the owner.

Size the job first. While the owner could settle the whole result in one
sitting, convert it whole. Past that, classify every line instead, propose the
slices, and convert nothing until the owner picks one. Half a file converted,
with nothing said about the half that was dropped, reads as complete.

Write one EARS statement per obligation, with acceptance criteria where they add
something the statement does not already say. Then:

- **Do not invent.** Every statement traces to a phrase the owner wrote, their
  answers to your questions included. A gap
  in what they said -- a missing delete, unstated error handling, nothing about
  retention -- is out of scope, or it is a question. It is never a statement you
  supply. One nobody asked for enters the corpus looking exactly like one they
  did.
- **Keep their nouns.** If they said "note", do not write "document". One thing
  with two names is a question, not a choice you make.
- **Sort product from build.** A requirement governs what the software does and
  states "the product shall": here that software is `reqctl`, `reqportal` and
  the `elucidate` scripts. What builds or checks them -- the hooks, pins, CI
  wiring, lockfiles -- is a `GUARD` and states "the build shall".
  `reqctl validate` refuses either subject under the other kind, so the sort is
  made before minting, not after. The line is what the software does against
  what builds and checks it, not functional against quality: a latency or
  security obligation is still product. When you cannot tell, ask.
  A rule of ours that a gate enforces and a test holds is a guard, and
  `CLAUDE.md` sets that bar. A third-party ruleset states no rule of ours to
  lift, and stays code; a rule of ours configured into one is still ours.
  A guard relates only to guards, so a build rule that seems to lean on a
  product statement is two rules, not one.
- **A value is a parameter; a record is a data item.** The entry key settles it:
  a parameter's key *is* the value, typed by `--value-type` and carrying
  `--unit` -- `30` is the thirty, `utc` is the fallback zone. A data item's key
  is a handle and the facts live in its fields -- `primary_disk` is not a
  value, it names one. Shape does not decide this and neither does who controls
  the thing: both kinds hold lists, and either may record something outside our
  gift.
- **A bare number is a parameter.** A limit, a timeout, a threshold: name it and
  mint it at step 3 rather than writing it into the prose. Say what it measures,
  not only its value -- step 2 needs the concept to tell a shared budget from two
  numbers that happen to match. A count a reader would say aloud -- one type,
  both organisations -- is written as a word and governs nothing.

- **A set of words is a data item; a set of quantities is a parameter.**
  Providers, formats, view types are words: mint one `DATA` --
  `reqctl new data --name export_formats --entry json --entry markdown` -- and
  reference it. Thresholds that move together are quantities: mint one `PARAM`
  whose value is an array, `--value "[10, 20]" --value-type count`, exactly as
  a lone threshold. `.github/guards/taxonomy.py` states the line and refuses
  the wrong side of it, so it is not restated here.
  Either way it is one named place, versioned, and adding a member re-reviews
  everything stated against it. Do not spell the members out inside a
  statement, and do not mint a requirement per option. Each member is an
  entry: `--default` names the one `${name.default}` selects, and
  `revise --entry MEMBER --set definition=...` gives a member its own
  meaning, so a statement may cite one member -- `${name.member}` --
  without binding the rest.
- **A named record is a data item.** Formats, colours, settings --
  records that are values, not obligations: mint one `DATA` per
  subject with `reqctl new data --name ... --entry handle`, then
  `revise --entry handle --set field=value`. A field may hold a reference
  or a list of them, and it binds exactly as prose does. Another party's own
  word for a corpus item goes in the value with the term linked; a field
  name alone binds nothing. A data field
  records a fact; the obligation about it stays a statement -- a field
  that restates a requirement is a second obligation free to drift.
- **A requirement binds to every dimension the corpus nominates; a guard binds
  to none.** A dimension is a data item whose schema marks it as one, and a
  repository may nominate none, one or several. Where it nominates none, there
  is no binding to read and nothing to ask. Otherwise read which members the
  owner's words name for each, and put your reading to them in the questions
  message as a single question with a table: the proposal, the dimension, the
  members you read it as binding to or `all`, and the phrase that rests on. A
  requirement bound to fewer than all of them references each in its own text --
  `${<dimension>.<member>}` -- exactly as any set member is cited; all of them is
  no reference at all. That is why the answer is recorded as well as written:
  nothing in an unannotated statement tells a binding the owner settled from one
  nobody was asked about. Record it under `binds` in `run.yaml`, keyed by
  dimension; a guard is left out of that record altogether.
- **A word the corpus does not define is a term.** Where the owner's words lean
  on a noun whose meaning the statement assumes -- core record type, inline
  link, archived record -- propose a `TERM` alongside the statements and link it
  at step 3. A word whose meaning a requirement already fixes is not a term.
- **A reference is a relation, never a string.** Where the source names its own
  clauses -- `BD-CAP-001`, an issue key, a section number -- that identifier
  does not enter the statement, the criteria or the rationale. Reword to name
  the behaviour, and carry the reference as a `reqctl relate` edge at step 3.
  The corpus names requirements `REQ-NNNNNNNN` and nothing else: a foreign id is
  a second way to name a thing, pointing at a document that will drift, and it
  validates cleanly so nobody finds it later. When the referenced clause has no
  counterpart in the corpus, ask the owner -- name any corpus item that matches
  it by meaning as a candidate, and never resolve the reference by guessing.
- **Say what you did not convert, and why** -- a question they were asking
  themselves, another way of saying a line you already took, or nothing to do
  with the software. Turning a musing into a `shall` makes it an obligation
  nobody chose. Keep that list: step 2 gives it to every agent so settled ground
  is not re-raised, and step 3 puts it in the pull request, where it is the only
  durable trace of what was considered and declined.
- **Account for every phrase.** Read the statements and the declined list back
  against the owner's words, and name what neither claims. An idea that
  produced nothing leaves nothing behind to notice it by. What is unclaimed
  becomes a statement, a declined line, or a question. You cannot be the only
  one who reads this back: the context that dropped a phrase is the context
  that would have to notice, and a wrong statement is challenged where a
  missing one is not. One `coverage` agent reads the three back once the
  answers are in, and it gets nothing else -- the corpus would only tell it
  what to raise elsewhere. Its prompt carries the owner's words, the declined
  list and every proposal in full, since the agent has no tool to read them.
  Ask it for one YAML document holding two lists:
  `unclaimed`, each entry a `quote` of the owner's words and why neither the
  statements nor the declined list account for it; and `renamed`, each entry the
  `owner` word and the noun a statement put in its place. Those names --
  `unclaimed`, `renamed`, `quote`, `owner`, `reason`, `statement`, `proposal`
  -- are what the check reads, and a document stating any other fails whole.
  `python3 ${CLAUDE_SKILL_DIR}/synthesis/coverage.py --words FILE --found FILE`
  checks every passage it quotes back against the owner's words and refuses the
  findings whole where one is not theirs: an invented omission reaches the owner
  as an established fact, and a check nobody can see you skip is one you skip.
  What survives joins the questions.

Ask now only what stops a statement being written: a word that could mean two
things, one thing the owner named twice, a line that may not be the product's at
all. The members each requirement binds to are the standing exception -- asked
every batch carrying one, because the answer is unrecoverable from a statement
that names none. A guards-only batch asks nothing here, and neither does a
corpus nominating no dimension: the corpus fixes the answer at none, so there
is no reading to put. What changes how
something is minted rather than what it obliges -- whether a quantity is
governed, whether a noun becomes a term, where a value belongs -- is settled at
step 3 and waits for the message step 2 sends. One interruption a batch, not
two.

**Answer before asking.** `reqctl context`, `list` and `export` are yours to
run first, and a rule this file already states is applied, not asked. What the
corpus settles is recorded with the evidence that settled it and never reaches
the owner as a question.

What survives groups by the decision it turns on, not the statement that raised
it: one question per decision. Ask them in one message, numbered, ordered by
what they block. Never the question picker, never one at a time. Each carries
what hangs on it, what is undecided, what the corpus already says, the
alternatives stated evenly, and your reading of them, marked as yours.
Disagreeing stays as easy as agreeing: the owner's first look must not be a
yes/no on a choice already made.

Feed the answers back and convert again.

<!-- @req+ REQ-13684791@_iUnF2f3QtDP msg57t -->
## 2 -- Challenge

```bash
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py build --run .elucidate/<run>
```

It reads what you wrote -- the owner's words, the declined list, the numbered
proposals, and `run.yaml` with its `binds`, `criteria` and `trace` maps --
and writes the prompts the agents read.

Spawning is one call of the Workflow tool with `scriptPath` at
`${CLAUDE_SKILL_DIR}/workflow.js` and `args` holding the contents of the
manifest named. Each agent reads its prompt, writes its return, and nothing
else. Each step that names a manifest is followed by a spawn and the next step
waits on it: run `judge` only once the spawn has returned.

```bash
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py judge --run DIR     # recall returns in, judge prompts out
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py final --run DIR     # only where a proposal was split into groups
python3 ${CLAUDE_SKILL_DIR}/synthesis/verdicts.py --run DIR       # returns in, verdicts/NN.json out, findings reported
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py describe --run DIR  # the pull request section
```

Read that report, not the returns.

The coverage agent is spawned from the prompt `build` named, once the answers
are in, and `python3 ${CLAUDE_SKILL_DIR}/synthesis/coverage.py --words FILE
--found FILE` checks every quote back against the owner's words.

A value or a word a verdict flagged, a conflict with an approved statement, a
part cover whose parts may account for the whole, and every question take the
same route: answered against the corpus first, then put to the owner as one
message. Duplication between the run's own statements is yours to confirm,
before anything is minted, from the verdicts naming another proposal.

Changing what this step asks, or what it gives an agent, is measured rather
than argued: `python3 ${CLAUDE_SKILL_DIR}/harness/probe.py` mints probes the
corpus itself labels and scores what a run returns. Run it before and after.

Wait for the owner. This is the last point before the corpus changes.
<!-- @req- msg57t -->

## 3 -- Approve

Only what the owner settled:

```bash
reqctl new term --term "..." --alias "..." --definition "..."
reqctl new parameter --text "..." --name ... --value ... --value-type ... [--default MEMBER]
reqctl new data --name ... --entry handle [--entry another]
reqctl new requirement --text "... [[the words]] ... \${param_name} ... \${param_name.member}." \
    --criterion 'a [[package]] is submitted | a [[manager]] approves it | it is recorded'
reqctl new guard --text "The build shall ..." \
    --criterion 'a lockfile install | --require-hashes is absent | the build refuses'
reqctl revise REQ-NNNNNNNN --ack param_name --ack the_word
reqctl revise the_word --status approved
reqctl revise REQ-NNNNNNNN --status approved
reqctl validate
git add requirements && git commit    # the items, before the baseline
reqctl baseline --generate
git add requirements && git commit    # the manifest
```

`[[word]]`, `[other words](word)` and `${name...}` are authoring forms:
`reqctl` resolves them as it writes and stores UIDs and addresses, so a
rename never silently retargets what was stored. A name that resolves to
nothing, or to more than one item, is refused at the point of writing. A
criterion's three slots carry the clauses without their labels -- reqctl writes
the given, when and then. `validate` reads a criterion as prose, so a term
named in one is linked there like anywhere else.

The order matters: `baseline --generate` records HEAD as the commit whose
corpus the baseline states, so generated over an uncommitted corpus the
manifest points at a tree that lacks its own items.

Relations run from the new statement toward what already exists, and the choice
comes from the source's own shape. A refinement of an existing requirement
`derives_from` it -- a sub-clause under a parent is the common case. A clause
the source states as a condition on the parent `constrains` it. Reserve
`depends_on` for what cannot be built first. A new statement that replaces
the existing one outright `supersedes` it.

Referencing a parameter is the whole binding, and so is linking a term: a fresh
reference or link reads as SUSPECT until `revise --ack` pins it, and a fresh
requirement-to-requirement relation until the same `reqctl relate` runs a second
time. Approve a term before the run ends rather than after; it then polices the
whole corpus, so a statement this run never touched can start failing for want
of a link; `reqctl context` on the draft term names those statements and counts
them, and the owner decides against that number rather than against the hazard
described. Put each one to the owner as its own revision. Revising an approved
term's definition makes every statement linking it suspect, exactly as a
parameter's value does. Anything the owner did not call ready stays `draft` and
carries no baseline change.

Before opening the pull request, read back what was wired: `reqctl context` each
new UID, and compare the edges, the parameter references and the term links
against what the challenge found and the owner settled. An edge named in a
verdict and never created fails silently, and so does a value the owner agreed
to share that was minted twice -- nothing validates recall. Wire what the
read-back finds missing, or put it to the owner, before the pull request opens.

The pull request body carries step 1's declined list and any UNJUDGED slot the
owner accepted. Nothing else durably records either, and a reader who cannot
see what was considered and dropped reads the corpus as everything that was
asked for.

An answer that settles more than this batch is a rule. Sort it as step 1 sorts
a statement and land it there: a requirement to mint, or code, a schema or a
guard. An answer left in the conversation is asked again next batch.

Marking `approved` is a proposal; it becomes true when the owner merges. Run
`reqctl validate` and `reqctl baseline --check` before pushing.

## Never

- Never let anything but `reqctl` touch the corpus.
- Never carry code into the requirements pull request; CI rejects the mixture.
- Never merge it.
- Never invent a mode for bulk; step 1 sizes the job.
