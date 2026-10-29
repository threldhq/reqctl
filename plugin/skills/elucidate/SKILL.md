---
# @req+ REQ-38288492@4l6tMNjp19tH yjwycv
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
# @req- yjwycv
---

<!-- @req> REQ-38288492@4l6tMNjp19tH wtuxki -->
# Elucidate

<!-- @req+ REQ-49297047@5j4PCY73F1LX rbmt6r -->
Take an item you mark approved as a proposal: it becomes approved only when the
owner merges the pull request carrying it. Never merge it yourself.
<!-- @req- rbmt6r -->

<!-- @req+ REQ-12222066@fbTfN4X4xFUs bzkv6x -->
<!-- @req+ REQ-89642091@-fsID3Q5hG8u 7wkwzy -->
No further step runs while a question you put the owner is unanswered. Post the
questions, then end your turn; under a goal, where that does not wait, collect
the answers with the question picker.
<!-- @req- 7wkwzy -->
<!-- @req- bzkv6x -->

<!-- @req> REQ-74528435@6hc4etfLg9tf 5sqb7k -->
Check that each statement you draft states one obligation.

<!-- @req> REQ-48887455@HRtyA7Vh2Xd7 smpwex -->
Check that each statement you draft is verifiable.

<!-- @req> REQ-69237286@ho327CpmtXUF 4nzx6k -->
Check that each statement you draft states no rationale.

<!-- @req> REQ-92674491@VG2-gdcODaVI rlz4ip -->
Keep a run's state under `.elucidate/<run>/`, and commit none of it.

<!-- @req> REQ-38395778@8sr-4VrWTB5O lqmjpa -->
Make the run's folder fresh at the start of the run.

<!-- @req> REQ-85868511@4puZsdbIJhfn z2jboh -->
Remove the run's folder at the end of the run.

<!-- @req+ REQ-28473555@fDR67hlkVPAc nfgbkj -->
<!-- @req+ REQ-37767588@63pbAfEkzoHI 3ynzdw -->
<!-- @req+ REQ-30554264@6JOa752EzDE9 foloxt -->
<!-- @req+ REQ-38877821@Rf8VoUrZ9-27 kwkxs3 -->
<!-- @req+ REQ-52230032@ZV7FwJtFuqi3 txcb4s -->
<!-- @req+ REQ-71318073@StYqTfNyHE39 qvkmhg -->
<!-- @req+ REQ-73186885@Q7CKwi3s629S hxcryb -->
<!-- @req+ REQ-56866805@ub8Wdi_A6dm_ 6yrcop -->
<!-- @req+ REQ-52114263@85vP2wA4G2MR hfxzn5 -->
You write `words.md`, `declined.md` and `proposals/NN.md`, each proposal its
own file holding its statement and nothing else, numbered because the number is
what a verdict answers -- the whole file is the statement, so a heading or a
criterion written there becomes part of it. `run.yaml` holds what the corpus settled,
what step 1 deferred to step 2's report, the questions asked with the owner's
answers, and three maps keyed by proposal number, each read by a script rather
than a reader, so it parses as YAML or `plan.py build` refuses: `binds`,
`criteria` and `trace`. `binds` is keyed by dimension first and then by
proposal number, and a corpus nominating no dimension needs no `binds` at
all. A proposal's criteria are a list of `given | when |
then` strings, and its trace a list of passages quoted from the owner's words;
a proposal carrying no criteria is left out of that map rather than written
empty. `run.yaml` also holds `declined_practices`, the numbers of the review's
practices the owner declined, and `answers`, keyed by proposal number and
then by each question its verdict raises, exactly as the verdict words it: the
owner's answer as `owner: ANSWER`, what settled it as `corpus: [{uid: UID,
clause: QUOTE}]`, each clause quoted from the item it names, or `declined:
true` where it names no contradiction with an approved item. `plan.py
describe` refuses a question recorded none of these ways. `synthesis/review.py`
writes the review's manifest, prompt and all, into `workflow/`, and the
review agent writes
`review.json`. `synthesis/plan.py` writes the rest
-- `export.md`, `shards/`, `dictionary.md`, `prompts/`, `build.json`,
`workflow/` -- and the agents fill `returns/`, which the scripts read into
`verdicts/`.
<!-- @req- hfxzn5 -->
<!-- @req- 6yrcop -->
<!-- @req- hxcryb -->
<!-- @req- qvkmhg -->
<!-- @req- txcb4s -->
<!-- @req- kwkxs3 -->
<!-- @req- foloxt -->
<!-- @req- 3ynzdw -->
<!-- @req- nfgbkj -->

<!-- @req+ REQ-61616834@ocFeB1JGP518 q34cuz -->
## 1 -- Convert

Convert them yourself: the owner's words are already here, and so is the owner.
The one agent this step spawns makes the best-in-class review, and drafts
nothing.
<!-- @req- q34cuz -->

<!-- @req> REQ-67566291@gxQ9gY4t9fkV x36cts -->
Run `reqctl list term` before drafting a statement.

<!-- @req> REQ-50337439@4xcRTPWSVz_D 4vulur -->
Run `reqctl context` on each term a statement you draft leans on.

<!-- @req> REQ-42935523@AScfCOLEPzJs 3r3rfc -->
Size the job before converting the owner's words.

<!-- @req+ REQ-22147729@xCxlqNEbnOjn onlsgo -->
While the owner could settle the result in one sitting, convert their words
whole.
<!-- @req- onlsgo -->

<!-- @req> REQ-61952013@_qXMtY79bXaY zigyzu -->
Where they could not, classify every line of their words and propose slices.

<!-- @req> REQ-53548386@9ewKWI2C3pvg tze5ch -->
Where you have proposed slices, convert nothing until the owner picks one.

<!-- @req> REQ-58574937@24h-tVxiP0ac kddpjw -->
Write one EARS statement per obligation.

<!-- @req+ REQ-39846612@2Mj3sAXgqLsd 3pg3as -->
Write acceptance criteria only where they add something the statement does not
state.
<!-- @req- 3pg3as -->

<!-- @req+ REQ-52311403@I-l2MAHHBoPD xpi6sb -->
- **Do not invent.** Trace every statement you draft to a phrase of the owner's
  words, their answers to your questions included.
<!-- @req- xpi6sb -->
<!-- @req+ REQ-91396370@iU1U5SolIsUq mdxpos -->
- Take a gap in their words -- a missing delete, unstated error handling,
  nothing about retention -- as out of scope or as a question, never as a
  statement you supply.
<!-- @req- mdxpos -->
<!-- @req> REQ-22446216@0AZBqrish1Gl kvkdvh -->
- **Keep their nouns.** If they said "note", do not write "document".
<!-- @req> REQ-93308558@f3O1EaKam327 f66w2o -->
- Put one thing the owner names two ways to them as a question.
<!-- @req+ REQ-83468274@0xeqDjC8CkiL dsbvv7 -->
<!-- @req+ REQ-85764802@N7tHuybyVI0x nvqukv -->
- **Sort product from build.** A rule a behaviour of the governed software
  depends on is a requirement and states "the product shall", even where only
  one repository runs that behaviour today. A rule only the repository's own
  check depends on is a `GUARD` and states "the build shall". A rule both
  depend on is one of each: a requirement for the behaviour and a guard for the
  repository's wiring. Where a rule is enforced -- a hook, a gate, a CI step --
  does not sort it, and neither does functional against quality: a latency or
  security obligation a behaviour depends on is product. `reqctl validate`
  refuses either subject under the other kind, so the sort is made before
  minting, not after. When you cannot tell, ask. A third-party ruleset states
  no rule of ours to lift, and stays code; a rule of ours configured into one
  is still ours. A guard relates only to guards, so a build rule that seems to
  lean on a product statement is two rules, not one.
<!-- @req- nvqukv -->
<!-- @req- dsbvv7 -->
<!-- @req+ REQ-79715634@W0ZctNofFGC8 ktu5yd -->
- **A lone value is a parameter; a record is a data item.** The entry key settles it:
  a parameter's key *is* the value, typed by `--value-type` and carrying
  `--unit` -- `30` is the thirty, `utc` is the fallback zone. A data item's key
  is a handle and the facts live in its fields -- `primary_disk` is not a
  value, it names one. Shape does not decide this and neither does who controls
  the thing: both kinds hold lists, and either may record something outside our
  gift.
- **A bare number is a parameter until it shares a subject.** A limit, a
  timeout, a threshold: name it and mint it at step 3 rather than writing it
  into the prose. Say what it measures, not only its value -- step 2 needs the
  concept to tell a shared budget from two numbers that happen to match.
  Values that bound or describe the same behaviour or the same thing -- a
  review's fetch limits, each agent's model and effort -- are entries of one
  data item, never a parameter each: `revise review_limits --new-entry page_bytes
  --set quantity=5242880 --set unit=bytes --set definition=...`, referenced as
  `${review_limits.page_bytes.quantity}`. A value whose subject the corpus
  already holds a data item for is a new entry of that item. A count a reader
  would say aloud -- one type, both organisations -- is written as a word and
  governs nothing.

<!-- @req+ REQ-39992377@fcd_dP7gzFbL rovgdr -->
- **A set of words is a data item; one quantity's tiers are a parameter.**
  Providers, formats, view types are words: mint one `DATA` --
  `reqctl new data --name export_formats --entry json --entry markdown` -- and
  reference it. The tiers of one threshold move together as one quantity:
  mint one `PARAM` whose value is an array, `--value "[10, 20]" --value-type
  count`, exactly as a lone threshold. `.github/guards/taxonomy.py` states the
  line and refuses the wrong side of it, so it is not restated here.
  Either way it is one named place, versioned, and adding a member re-reviews
  everything stated against it. Do not spell the members out inside a
  statement, and do not mint a requirement per option. Each member is an
  entry: `--default` names the one `${name.default}` selects, and
  `revise --entry MEMBER --set definition=...` gives a member its own
  meaning, so a statement may cite one member -- `${name.member}` --
  without binding the rest.
<!-- @req- rovgdr -->
<!-- @req- ktu5yd -->
<!-- @req+ REQ-56316426@AiecCcNDFXxE uz57co -->
- **A named record is a data item.** Mint a named record that is a value
  rather than an obligation -- a format, a colour, a setting -- as a data item:
  one `DATA` per subject with `reqctl new data --name ... --entry handle`, then
  `revise --entry handle --set field=value`.
<!-- @req- uz57co -->
<!-- @req+ REQ-76604940@SEVyiDrbH-Ez haz6te -->
- A field may hold a reference or a list of them, and it binds exactly as prose
  does.
<!-- @req- haz6te -->
<!-- @req+ REQ-31592505@2C7Za06pRzA2 y5fdsb -->
- Another party's own word for a corpus item goes in the value with the term
  linked; a field name alone binds nothing.
<!-- @req- y5fdsb -->
<!-- @req+ REQ-91815676@Offk2nI3tA46 6zn5ko -->
- State an obligation about the fact a data field records as a statement, not
  as a field.
<!-- @req- 6zn5ko -->
<!-- @req+ REQ-79247272@2opCGt3Oo2j5 tktbtb -->
- **A requirement binds to every dimension the corpus nominates.** Where the
  corpus nominates a binding dimension, put your reading of the members each
  requirement binds to as one question with a table: the proposal, the
  dimension, the members or `all`, and the phrase the reading rests on.
<!-- @req- tktbtb -->
<!-- @req+ REQ-16901746@96PSBu5QPVOP ubxafo -->
<!-- @req+ REQ-50522674@MIzqcKrm_Ge8 dgpvod -->
<!-- @req+ REQ-54045696@m7842dVOG3jf b6tc2n -->
<!-- @req+ REQ-58008138@PXcNItNpUpth ellpg6 -->
<!-- @req+ REQ-83454000@CAS-4S3kCWy5 r73vzz -->
<!-- @req+ REQ-92272837@JyGx2T7SRoWI seqxjn -->
- A dimension is a data item whose schema marks it as one. A requirement bound
  to fewer than all of them references each in its own text --
  `${<dimension>.<member>}` -- exactly as any set member is cited; all of them
  is no reference at all. Record the answer under `binds` in `run.yaml`, keyed by
  dimension; a guard is left out of that record altogether.
<!-- @req- seqxjn -->
<!-- @req- r73vzz -->
<!-- @req- ellpg6 -->
<!-- @req- b6tc2n -->
<!-- @req- dgpvod -->
<!-- @req- ubxafo -->
<!-- @req+ REQ-41886534@JmbW9JKfpv0S bmelsc -->
- **A word the corpus does not define is a term.** Propose a `TERM` for a noun
  the owner's words lean on that the corpus does not define -- core record
  type, inline link, archived record -- and link it at step 3.
<!-- @req- bmelsc -->
<!-- @req> REQ-25342064@03F4MB7WoW5r t6vyxg -->
- Propose no term for a word a requirement already fixes.
<!-- @req+ REQ-19727912@Y0AjFgd5opvT 6qvjun -->
- **A reference is a relation, never a string.** Keep an identifier a source
  uses for its own clauses -- `BD-CAP-001`, an issue key, a section number --
  out of the statement, the criteria and the rationale.
<!-- @req- 6qvjun -->
<!-- @req+ REQ-93964176@AH9x2CxZXnH7 acbflg -->
- Carry a reference a source makes to its own clause as a `reqctl relate` edge
  at step 3.
<!-- @req- acbflg -->
<!-- @req+ REQ-32064058@7TMCWJrPa7YC 4q27tc -->
- Where the referenced clause has no counterpart in the corpus, put a question
  to the owner naming any corpus item that matches it by meaning.
<!-- @req- 4q27tc -->
<!-- @req+ REQ-21373303@Y7R6bZxRXU-G a52wiq -->
- **Say what you did not convert, and why** -- a question they were asking
  themselves, another way of saying a line you already took, or nothing to do
  with the software. Turning a musing into a `shall` makes it an obligation
  nobody chose. Keep that list: step 2 gives it to every agent so settled ground
  is not re-raised, and step 3 puts it in the pull request, where it is the only
  durable trace of what was considered and declined.
<!-- @req- a52wiq -->
<!-- @req+ REQ-16470467@izHEOkHX4UMq wcy3ri -->
- **Account for every phrase.** Read the statements and the declined list back
  against the owner's words, and name each passage neither claims.
<!-- @req- wcy3ri -->
<!-- @req> REQ-40537695@PLuueYnG4nWk ldzdyo -->
- Make each passage neither claims a statement, a declined line, or a question.
<!-- @req+ REQ-12032769@1Km3PLqZHCDu jbjaix -->
<!-- @req+ REQ-26693396@t2DC4anz7B5V hou53s -->
<!-- @req+ REQ-41361856@4UOkrz1niMIl iy6s45 -->
<!-- @req+ REQ-13591264@tle-mDzkWdnR 4dvrrr -->
<!-- @req+ REQ-24569953@LsZU4Go81cg8 kflapp -->
<!-- @req+ REQ-27370034@uYfNuf6k4Q_h qccqlw -->
<!-- @req+ REQ-47744588@ZrmtfTL6RUOL ngdu53 -->
<!-- @req+ REQ-80500447@cWHS2ihd6kMV mcj75j -->
<!-- @req+ REQ-47857051@6HlsaLluC2pn n4lqaw -->
- One `coverage` agent reads the three back once the answers are in, and it
  gets nothing else. Its prompt carries the owner's words, the declined
  list and every proposal in full, since the agent has no tool to read them.
  Ask it for one YAML document holding two lists:
  `unclaimed`, each entry a `quote` of the owner's words and why neither the
  statements nor the declined list account for it; and `renamed`, each entry the
  `owner` word and the noun a statement put in its place. Those names --
  `unclaimed`, `renamed`, `quote`, `owner`, `reason`, `statement`, `proposal`
  -- are what the check reads, and a document stating any other fails whole.
  `python3 ${CLAUDE_SKILL_DIR}/synthesis/coverage.py --words FILE --found FILE`
  checks every passage it quotes back against the owner's words and refuses the
  findings whole where one is not theirs. What survives joins the questions.
<!-- @req- n4lqaw -->
<!-- @req- mcj75j -->
<!-- @req- ngdu53 -->
<!-- @req- qccqlw -->
<!-- @req- kflapp -->
<!-- @req- 4dvrrr -->
<!-- @req- iy6s45 -->
<!-- @req- hou53s -->
<!-- @req- jbjaix -->

<!-- @req+ REQ-82432523@dA6MI5WknAH4 drprho -->
**Make the best-in-class review before any question.** The first time you
convert a run's words, build the review's prompt:

<!-- @req+ REQ-13684791@C0Dl1DhCdIyB dyekvt -->
```bash
python3 ${CLAUDE_SKILL_DIR}/synthesis/review.py build --run .elucidate/<run>
```

<!-- @req+ REQ-61616834@ocFeB1JGP518 oit5jj -->
It states the owner's words, the field of the governed software -- the
`governed_field` parameter where the corpus states one -- and the repository's
README where there is one, and names the manifest that spawns the review's
<!-- @req+ REQ-61212158@EISsRx_ntdvz cehbym -->
agent. Spawn it with one call of the Workflow tool, `scriptPath` at the
`workflow.js` beside that manifest and `args` holding the contents of that
manifest, then check what the agent wrote:
<!-- @req- cehbym -->
<!-- @req- oit5jj -->

```bash
python3 ${CLAUDE_SKILL_DIR}/synthesis/review.py check --run .elucidate/<run>
```
<!-- @req- dyekvt -->

<!-- @req+ REQ-46711731@rqojAeSdcYOn 4avail -->
The check fetches every page the review cites. It refuses the review where a
practice names no source or a page cannot be read or does not hold the passage
quoted from it, and names the way to clear the refusal: follow it. Where every
fault is a transient failure, it names a question for the owner instead: put it
to them, and take the step their answer names.
<!-- @req- 4avail -->

A review that passes is the run's review; nothing later in the run makes
another. Each of its practices records its fit to the project, assessed against
the README, or null where there is no README.
<!-- @req- drprho -->

<!-- @req+ REQ-90096667@PunOebgQZAD6 cbcn57 -->
Where the corpus states no field and there is no README, `build` refuses: ask
the owner for the field of the governed software, then build again with
`--field` holding their answer.
<!-- @req- cbcn57 -->

<!-- @req+ REQ-17957103@ay-QXJ4CLPhD 6skxee -->
Before the challenge, ask only what stops a statement being written: a word that
could mean two things, one thing the owner named twice, a line that may not be
the product's at all.
<!-- @req- 6skxee -->

<!-- @req+ REQ-26166529@PhrDTHw0Uh6n pd3laq -->
Hold a question on how something is minted -- whether a quantity is governed,
whether a noun becomes a term, where a value belongs -- until the message step 2
sends.
<!-- @req- pd3laq -->

<!-- @req+ REQ-70471287@0VcnpvVZEGUG mqesje -->
**Answer before asking.** Run `reqctl context`, `list` or `export` before
putting a question to the owner.
<!-- @req- mqesje -->

<!-- @req+ REQ-19683247@T7qo0bGkc-af 7ysreo -->
Record what the corpus settles with the evidence that settled it, and put no
question to the owner on it.
<!-- @req- 7ysreo -->

<!-- @req> REQ-96727187@XOW9w6F1G1-D tqst2c -->
Put your questions in one message, numbered and ordered by what they block.

<!-- @req+ REQ-96989080@k9EgxRzPEyxt 7c6z2g -->
State with each question what hangs on it, what is undecided, what the corpus
says, the alternatives stated evenly, and your own reading, marked as yours.
<!-- @req- 7c6z2g -->

<!-- @req> REQ-44823271@AviNJLM07SOZ v2tnmd -->
State the review's summary in that message, as `check` prints it.

<!-- @req+ REQ-58598892@Ac8QPjjAwTy9 25edfl -->
Put the table `check` prints to the owner as one question: they adopt or
decline each practice in it, and each row carries the review's recommendation.
<!-- @req- 25edfl -->

<!-- @req+ REQ-21927376@QwR1cNzGEntf kmfcsp -->
For each idea a practice the review recommends adopting bears on, that practice
is the idea's default answer. Take its fit to the project from the review,
assessed against the README at the project root, then adapt it to the approved
requirements the idea touches, read with `reqctl context`. Where the review
found no README, adapt it without a fit and say in the message that no README
was found. Propose the adapted practice in the message as the idea's default
answer, and draft nothing beyond it until the owner answers. Where the adapted
practice conflicts with an approved requirement, name that requirement and put
the conflict to the owner as a question. An idea no recommended practice bears
on is converted as their words state it.
<!-- @req- kmfcsp -->

<!-- @req+ REQ-18597283@h9OoEEN62bql vb4fww -->
Every question you put the owner once the review passes carries a
recommendation drawn from the run's review:
the answer it favours and the numbered practices it rests on, or that the
review holds nothing bearing on the question. It is the review's reading,
marked as such, beside the alternatives.
<!-- @req- vb4fww -->

<!-- @req+ REQ-93075993@_Ewq27hRC5AG jt35j6 -->
An answer adopting a practice joins the owner's words with the rest of their
answers: propose the practice as the answer states it, traced to that answer.
<!-- @req- jt35j6 -->

<!-- @req+ REQ-20454019@BJxxS0ixzdXK wquver -->
Record each practice the owner declines, by its number, under
`declined_practices` in `run.yaml`; `plan.py describe` states them in the
declined list.
<!-- @req- wquver -->

<!-- @req+ REQ-80620603@d9HSssP4TTeh 32enfk -->
Defer nothing on your own. A passage of the owner's words, a practice or a
question a verdict raises that the run does not convert is declined or asked,
never set aside for a later run. Only where an answer of the owner asks that one
be deferred, record it under `deferred` in `run.yaml` as `{what: ..., answer:
QUOTE}`, the answer quoted from their words; `plan.py describe` states the list.
<!-- @req- 32enfk -->

<!-- @req> REQ-95094826@Vh-K2UxzJii4 xaa7w6 -->
Convert the owner's words again after they answer.

<!-- @req+ REQ-13684791@C0Dl1DhCdIyB msg57t -->
## 2 -- Challenge

```bash
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py build --run .elucidate/<run>
```

It reads what you wrote -- the owner's words, the declined list, the numbered
proposals, and `run.yaml` with its `binds`, `criteria` and `trace` maps --
and writes the prompts the agents read.

<!-- @req+ REQ-61212158@EISsRx_ntdvz xmrmw6 -->
Spawning is one call of the Workflow tool with `scriptPath` at the
`workflow.js` beside the manifest named and `args` holding the contents of
that manifest. Each agent reads its prompt, writes its return, and nothing
<!-- @req- xmrmw6 -->
else. Each step that names a manifest is followed by a spawn and the next step
waits on it: run `judge` only once the spawn has returned.

<!-- @req+ REQ-99682173@IOd4h42V9snI 55vtbf -->
When the owner's answers change a proposal's statement or criteria, put the
agent count, models and approximate token count the build reports for its
manifest to the owner, and wait for their answer before spawning the run's
agents again.
<!-- @req- 55vtbf -->

```bash
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py judge --run DIR     # recall returns in, judge prompts out
python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py final --run DIR     # only where a proposal was split into groups
python3 ${CLAUDE_SKILL_DIR}/synthesis/verdicts.py --run DIR       # returns in, verdicts/NN.json out, findings reported
```

Read that report, not the returns.

<!-- @req+ REQ-23060027@zeNeSryv-0-1 7pvcrn -->
The coverage agent is spawned through the workflow with the manifest `build`
names for it, once the answers are in, and
`python3 ${CLAUDE_SKILL_DIR}/synthesis/coverage.py --words FILE
--found FILE` checks every quote back against the owner's words.
<!-- @req- 7pvcrn -->

A value or a word a verdict flagged, a conflict with an approved statement, and
a part cover whose parts may account for the whole take the same route:
<!-- @req+ REQ-53412038@i8VnjjZfn-sC m2mad7 -->
answered against the corpus first, then put to the owner as one message.
A question a verdict raises takes that route only where it names a
contradiction between its proposal and an approved item. One that names none
is declined: record it as `declined: true` under `answers`, put it to no one,
<!-- @req- m2mad7 -->
and draft no proposal for it.

Duplication between the run's own statements is yours to confirm,
before anything is minted, from the verdicts naming another proposal.

Changing what this step asks, or what it gives an agent, is measured rather
than argued: `python3 ${CLAUDE_SKILL_DIR}/harness/probe.py` mints probes the
corpus itself labels and scores what a run returns. Run it before and after.

<!-- @req+ REQ-32446903@I3rgjDNBKOJC wmw3cf -->
Ask the owner which proposals to mint, in the message carrying the questions,
or in one saying the challenge raised none. Add each proposal they decline to
`declined.md` with their reason, or that they gave none. Then render the pull
request section with `python3 ${CLAUDE_SKILL_DIR}/synthesis/plan.py describe
--run DIR`. This is the last point before the corpus changes.
<!-- @req- wmw3cf -->
<!-- @req- msg57t -->

<!-- @req+ REQ-32446903@I3rgjDNBKOJC 4ar2sa -->
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
<!-- @req- 4ar2sa -->

<!-- @req> REQ-49378865@hNmMaPwVgBd8 xwvit4 -->
Commit the items you mint before running `reqctl baseline --generate`.

<!-- @req+ REQ-28700224@PBlsadvJKsKt 6n6vna -->
Where step 1 asked the owner for the field of the governed software, mint their
answer as the parameter the review reads:

```bash
reqctl new parameter --name governed_field --text "The market the governed software serves" --value "..." --value-type text
```
<!-- @req- 6n6vna -->

<!-- @req> REQ-23559711@r9BvkcpE5_rb 2yq2x6 -->
Relate a statement refining an existing requirement to it with `derives_from`.

<!-- @req+ REQ-62691725@zNnjGRBOA-oD oftv7m -->
Relate a clause the source states as a condition on a parent requirement to that
parent with `constrains`.
<!-- @req- oftv7m -->

<!-- @req+ REQ-95187450@rDrgCNPe2Kg3 mjm6lz -->
Relate a statement to another with `depends_on` only where the other cannot be
built first.
<!-- @req- mjm6lz -->

<!-- @req+ REQ-46507577@d0I3RQglsWl9 mlyghc -->
Relate a statement that replaces an existing one outright to it with
`supersedes`.
<!-- @req- mlyghc -->

<!-- @req> REQ-70659312@fh_ADqWADvRu 7kcuct -->
Pin each fresh parameter reference and term link with `reqctl revise --ack`.

<!-- @req+ REQ-43080611@5ywnJ7vkh3_i btucoz -->
Pin each fresh requirement-to-requirement relation by running the same `reqctl
relate` again.
<!-- @req- btucoz -->

<!-- @req+ REQ-42122085@d4n3zTgoPt-r 6ytpbz -->
Put each draft term's approval to the owner as its own revision, with the number
of statements it would police, as `reqctl context` on the draft term counts
them.
<!-- @req- 6ytpbz -->

<!-- @req> REQ-68178023@0bt8HD3Lfo1p 65hbqk -->
Leave `draft` each item the owner did not call ready.

<!-- @req+ REQ-48506023@q6jkawEyDH5a uacnvt -->
Before opening the pull request, read back each new item with `reqctl context`,
and compare its edges, parameter references and term links against what the
challenge found and the owner settled.
<!-- @req- uacnvt -->

<!-- @req+ REQ-76478774@efUM1GgZ0BKM tqpnkt -->
Wire what the read-back finds missing, or put it to the owner, before the pull
request opens.
<!-- @req- tqpnkt -->

<!-- @req+ REQ-21373303@Y7R6bZxRXU-G vadyl4 -->
The pull request body carries the declined list. Nothing else durably records
it, and a reader who cannot see what was considered and dropped reads the
corpus as everything that was asked for.
<!-- @req- vadyl4 -->

<!-- @req+ REQ-16858712@5JeIodp_iLA5 bh4gxa -->
Land an answer of the owner that settles more than this batch as a requirement,
code, a schema or a guard, sorted as step 1 sorts a statement.
<!-- @req- bh4gxa -->

<!-- @req> corpus_gates.corpus_validity@bBwB96MrzY7w gcz56j -->
<!-- @req> corpus_gates.baseline_match@T9FGopznhVwz uwdimw -->
Run `reqctl validate` and `reqctl baseline --check` before pushing.

<!-- @req> REQ-22704490@u7IClIQOfStA od7cth -->
<!-- @req> REQ-54260750@MTrWbA9_HZWY hcy6rk -->
Let nothing but `reqctl` touch the corpus.

<!-- @req> corpus_gates.travel_alone@OvtvltlSwqp4 tjaqrb -->
Carry no code in the requirements pull request.
