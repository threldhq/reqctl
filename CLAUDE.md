# reqctl

Requirements-first, turned on itself. The governance system governs the tool
that runs it: `reqctl`, `reqportal` and the `elucidate` skill are what this
repository builds, and each is written against an approved baseline and cites
the rule that governs it.

## Audience

Claude is the only thing that reads or writes a file here. The owner opens none
of them. What reaches the owner is the pull request body, the reply in session,
and what `reqctl` prints: those are written for a person, and nothing in the
tree is. The reader is a session that starts with no memory of this repository,
so legibility is owed more here than to a colleague who remembers. It belongs in
names, structure and statement citations, each of which fails when it goes
stale, and never in prose beside the code, which cannot.

Two accounts hold the repository and there will never be a third. Claude pushes
and opens pull requests as `dill-eng`; the owner reviews, approves and merges as
`threld-dev`. That is what `CODEOWNERS` encodes by putting `@threld-dev` on `*`:
with two identities, keeping the one that writes out of the one that approves is
the entire separation.

## Priority order

When rules conflict, higher wins.

1. Correctness
2. Requirements and traceability
3. Verification
4. Minimal change
5. Succinctness
6. Simplicity
7. Maintainability

## Requirements are the gate

Every bug and every request from the owner becomes a GitHub issue before it
becomes a requirement or a fix. Search the open issues first and reuse a match.
Every pull request that follows from one names it in its body: `Closes #N` on
the one that finishes it, `Refs #N` on the rest. A pull request nothing asked
for, such as a dependency bump, names none.

Every change to what `reqctl`, `reqportal` or `elucidate` does cites a governing
approved requirement, a fix included. If none exists, stop and ask the owner to
create one.

`reqctl` is the product this repository builds, so a statement about what it
does states "the product shall" and is a `REQ`. What reqctl ships as its Claude
Code plugin, the requirements-guard hook included, is product, so its rules are
`REQ`s too. A `GUARD` states "the build shall" and is reserved for what makes
and checks reqctl rather than for reqctl itself; it is minted, approved and
baselined like a requirement, and cited at the code that enforces it.

A rule of ours is sorted as the elucidate skill sorts it (REQ-83468274), by what
depends on it and not by where it is enforced. Travel-alone is a corpus gate
reqctl runs for any repository that calls it, so its rule is a `REQ`. The
comment and help budgets and CODEOWNERS serve only this repository's own check,
so theirs are `GUARD`s. The session-start hook is wired by the repository's own
settings rather than the plugin, so it is build, and its install parity is
GUARD-93589588.

The plugin prints its session rules when a session starts and after each
compaction, and they are not repeated here: the corpus read and written through
`reqctl` alone, `reqctl context` before implementing, citing with `reqctl tag`,
re-pinning, and the corpus pull request that travels alone, after which every
other pull request is refused until the next one re-pins. A session or subagent
that does not hold them reads `plugin/hooks/session-rules.md` before working.

The hook backs two of those rules. It refuses a Read, Grep, Glob or shell
command that names a file under requirements/reqs, guards, params, terms, data
or the baseline; schemas stay readable, git's own read forms stay allowed, and a
recursive grep that names no corpus path is beyond a hook that sees only the
command text. It refuses an edit, or a shell command naming a citation, that
adds, removes or changes a citation comment (REQ-38099593); a script that writes
one without naming it is beyond it too. `reqctl trace` refuses the retired
single-line tag, a module-level mapping of them (`REQ-44164687`), and a citation
naming no stamp (`REQ-75161909`).

Claude may draft requirements, assess impact, mark one approved and cut a
baseline. All of those are proposals. **Approval is the merge**: only `main`
states what is approved, and only the owner merges.

## Goals

Work under an explicit `/goal`, a built-in the owner runs that the skills list
does not show. If none is set, propose the condition that would mean done and
let the owner set it before modifying files. Write the condition as the
transcript can show it — name the command that proves it — because the evaluator
reads the conversation and runs nothing itself. Do not widen a goal
mid-implementation — finish it, or propose a new one.

## Before writing

Read the current contents of a file before modifying it, rather than assuming
its state.

Check existing manifests before proposing a dependency, and justify it. Where two
existing patterns contradict each other, pick one, say why, and flag the other.
Do not average them.

## Changes

Touch the smallest parts of the fewest files. Write production-grade code,
strictly YAGNI: build what an approved requirement asks for, and stop there.

Output complete logic for what you are changing: no placeholder such as
`// TODO: implement`, and no eliding with `...`.

Change what the task names. Mention anything else you noticed separately, and
leave it where it is. Write succinctly — in files, in commits, and in replies to
the owner — and write what the next session must act on.

The code says what it does. Write no comments and no docstrings; what one would
have said belongs in a name, the corpus, or the commit message. The only
exception is a directive a tool reads — `zizmor: ignore`, `shellcheck disable`,
a statement citation. Those are syntax, not prose, and `.claude/rules/budgets.md`
states how CI counts them.

Do not create decision records, ADRs, or design documents. A constraint belongs
in a `REQ`, a `GUARD`, or a schema — if it did not become one of those, it does
not persist.

## Verification

Code is verified by reading it against the approved statement it cites.
`reqctl compare` names every cited region a change touches, and each is read
again.

A test may be written and run to exercise code while working, and is deleted
before commit. No test is committed, and no requirement is drafted with
`automated_test` verification. A pass is not evidence that the code does what
its statement says, of correctness or against regression, because the test and
the code come from the same understanding.

`python .github/verify.py` runs the gates: it reads the `check` job from
`.github/workflows/ci.yml` and runs the steps CI would run for this tree, so a
session runs what CI runs rather than a subset it recalled. Read what it
skipped — a step skipped for provisioning is checked only by CI.

A task is called complete only by stating what was checked: the statements the
code was read against and the gates that ran. Where only use can show it works,
ask the owner to try it. Kill background processes and delete temp files before
declaring done.

If the same command fails three times, stop. Report the command, the error, what
you tried, what you learned, and what you need. Do not attempt a fourth fix.

## Git and pull requests

Work on a branch: a commit reaches `main` only through the owner's merge. Do not
force push.

Commit at coherent milestones with conventional messages, citing the requirement
where useful: `feat(REQ-75161909): refuse an unstamped citation`.

Open a pull request when a coherent unit of work is ready, not on every push —
CI minutes are finite. Batch related work into one PR.

The owner reads the pull request, not the diff. State what changed and what was
checked; nothing the body omits is seen. The body puts nothing to the owner: a
question, a choice or a request to try something goes to them in the session.

Claude may merge a pull request that touches only code — a permission that waits
on a deliberate `CODEOWNERS` carve-out: `*` owns the repository, so a new path is
owned the moment it appears. Claude may not merge one touching an owned path;
those need the owner's approval. An owned path never gets a carve-out: that
puts `dill-eng` on both sides of its own change.

Corpus changes and implementation changes stay in separate commits and separate
pull requests. CI rejects the mixture, so the approval is looked at on its own
rather than buried beside the code written against it.

CI is the enforcement boundary. This file is not.

## Tools and subagents

Prefer a script, CLI or existing skill over doing something by hand. Do not
weaken a check, a schema, or a gate to make something pass: fix what it caught.

Use subagents when work is large, parallelisable, or would flood context — not
by default. Define each subtask, assign non-overlapping files, and state the
verification expected. Use the lowest-tier model that can do the job; ask before
using Opus or Fable.

A skill that spawns agents without naming a model has not chosen one. Choose per
agent before spawning, including inside a vendored skill.

`/design` drafts a surface to look at before it is built — worth it for an
interaction whose shape is still in question, not for one already stated. What
it returns is a sketch: a constraint that survives it belongs in a requirement,
and the canvas is not where it lives.

## Memory

Auto memory is disabled. Nothing authoritative lives in it. If a fact matters to
the correctness of this software, it belongs in the corpus or the code — not in
an agent's notes.
