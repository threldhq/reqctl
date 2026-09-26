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

Every change to what `reqctl`, `reqportal` or `elucidate` does must cite a
governing approved requirement. If none exists, **stop** and ask the owner to
create one. No exceptions, including fixes.

`reqctl` is the product this repository builds, so a statement about what it
does states "the product shall" and is a `REQ`. What reqctl ships as its Claude
Code plugin, the requirements-guard hook included, is product, so its rules are
`REQ`s too. A `GUARD` states "the build shall" and is reserved for what makes
and checks reqctl rather than for reqctl itself; it is minted, approved and
baselined like a requirement, and cited at the code that enforces it.

What carries the build rather than stating a rule of ours -- dependency pins, CI
wiring, lockfiles -- is governed by the gates in CI. The CI mechanics --
workflow shape, the comment and help budgets, lockfile checks, CODEOWNERS,
travel-alone -- are build, and a rule of ours lifted out of one is a `GUARD`.
The session-start hook is wired by the repository's own settings rather than
the plugin, so it is build, and its install parity is GUARD-93589588. A
third-party ruleset -- `ruff`, `mypy`, `actionlint` -- states no rule of ours to
lift, and stays code; a rule of ours configured into one is still ours.

`reqctl` is the only way the corpus is touched. Never hand-edit an item or
baseline file, never read one except through `reqctl`, and never reach one with
`sed`, a redirect, or a script. The hook refuses a Read, Grep, Glob or shell
command that names a file under requirements/reqs, guards, params, terms, data
or the baseline; schemas stay readable, git's own read forms stay allowed, and a
recursive grep that names no corpus path is beyond a hook that sees only the
command text.

Claude may draft requirements, assess impact, mark one approved and cut a
baseline. All of those are proposals. **Approval is the merge**: only `main`
states what is approved, and only the owner merges.

A pull request carrying a corpus change must carry nothing else. CI rejects the
mixture, so the approval is looked at on its own rather than buried beside the
code written against it.

A corpus pull request lands with the code still pinned to the statements it
superseded, so `main` goes red on the citations guard and every other pull
request is refused until a following one re-pins. That following pull request is
the next work in the repository, ahead of whatever else is open. `implement`
states how to do it: read the code against the statement that now stands, then
re-pin.

Run `reqctl context UID [UID ...]` before implementing. Never implement from an
ID alone.

`reqctl --help` is the index of what reqctl can do. `reqctl list
[requirement|guard|parameter|term|data]` names what the corpus holds -- the
glossary, the parameters -- without reading all of it. `reqctl export` prints
the corpus at large, approved only unless `--all` adds everything else, as
markdown unless `reqctl --json` asks for the records.

Cite implementation with `reqctl tag PATH --from N --to M --req UID` over the
smallest region whose behaviour satisfies the requirement. It writes one comment
over a single code statement and a pair of comments over more, pinned to the
statement as it stands, so no stamp is ever composed or pasted. Do not cite helpers or
incidental code. A stale citation is re-pinned by reading the code against the
statement that now stands, then `reqctl repin ID`; one that no longer governs
goes with `reqctl untag ID`, and a region that moved is untagged and cited again.
The hook refuses an edit, or a shell command naming a citation, that adds,
removes or changes a citation comment (REQ-38099593); a script that writes one
without naming it is beyond a hook that sees only the command text.

A statement citation is the only form `reqctl trace` accepts: it refuses the
retired single-line tag and a module-level mapping of them (`REQ-44164687`), and
a citation naming no stamp (`REQ-75161909`).

## Goals

`/goal` is a built-in command the owner runs. Built-ins are absent from the
session's skills list, which holds skills only — so ask the owner to set a goal
rather than reading the command as missing.

Work under an explicit `/goal`. If none is set, propose the condition that would
mean done and let the owner set it before modifying files. Write the condition
as the transcript can show it — name the command that proves it — because the
evaluator reads the conversation and runs nothing itself. Do not widen a goal
mid-implementation — finish it, or propose a new one.

## Before writing

Read the current contents of a file before modifying it. Never assume state.

Check existing manifests before proposing a dependency, and justify it.

Where two existing patterns contradict each other, pick one, say why, and flag
the other. Do not average them.

## Changes

Touch the smallest parts of the fewest files.

Write production-grade code, strictly YAGNI: build what an approved requirement
asks for, and stop there.

Never write placeholders — no `// TODO: implement`, no eliding with `...`.
Output complete logic for what you are changing.

Change what the task names. Mention anything else you noticed separately, and
leave it where it is.

Write succinctly — in files, in commits, and in replies to the owner. Write what
the next session must act on.

The code says what it does. Write no comments and no docstrings; what one would
have said belongs in a name, the corpus, or the commit message.

The only exception is a directive a tool reads — `zizmor: ignore`, `shellcheck
disable`, a statement citation. Those are syntax, not prose. A
directive that belongs to one file is named in `comment_budget.ALLOWED` against
that file; a citation belongs wherever the code it governs is, so the budget
reads it by shape instead and counts it as nothing. CI holds the count of what
is left at zero and refuses a file type it has no rule for.

Prose inside a string is invisible to that guard, so argparse `help=` and
`description=` are counted by their own budget in `ci.yml`. What survives it is
`reqctl`'s, which a session reads through `reqctl --help` rather than the whole
of `cli.py`. A script nothing hand-drives carries none: its caller states the
arguments.

Do not create decision records, ADRs, or design documents. A constraint belongs
in a `REQ`, a `GUARD`, or a schema — if it did not become one of those, it does
not persist.

## Verification

Code is verified by reading it against the approved statement it cites.
`reqctl compare` names every cited region a change touches, and each is read
again.

A test may be written and run to exercise code while working, and is deleted
before commit. No test is committed, and no requirement is drafted with
`automated_test` verification. A pass is never offered as evidence that the code
does what its statement says, of correctness or against regression, because the
test and the code come from the same understanding.

`python .github/verify.py` runs the gates: it reads the `check` job from
`.github/workflows/ci.yml` and runs the steps CI would run for this tree, so a
session runs what CI runs rather than a subset it recalled. Read what it
skipped — a step skipped for provisioning is checked only by CI.

A task is called complete only by stating what was checked: the statements the
code was read against and the gates that ran. Where only use can show it works,
ask the owner to try it.

Kill background processes and delete temp files before declaring done.

If the same command fails three times, stop. Report the command, the error, what
you tried, what you learned, and what you need. Do not attempt a fourth fix.

## Git and pull requests

Work on a branch. Never commit to `main`. Never force push.

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
pull requests.

CI is the enforcement boundary. This file is not.

## Tools and subagents

Prefer a script or CLI over doing something by hand. Prefer an existing skill or
tool over improvising.

Never weaken a check, a schema, or a gate to make something pass.

A guard that refuses a character asks Unicode what that character is. A list of
codepoints is a guard that admits the next one.

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
