---
name: implement
description: >
  Write code against an approved requirement: read its neighbourhood through
  reqctl context, build the smallest unit that satisfies the statement, cite it
  with reqctl tag, and prove it. Use whenever the owner asks
  for behaviour to be built, changed or fixed under a requirement, and whenever
  they say implement. Not for writing or revising requirements -- that is
  elucidate -- and not for the pass a finished branch gets, which is pre-pr.
---

<!-- @req> REQ-38288492@1yCh_1wG8N-l qtmeg3 -->
# Implement

An approved statement in, cited and proven code out. The corpus is the input
and never the output: nothing here writes to the corpus.

CLAUDE.md states the rules. This is the order they run in.

## 1 -- The goal names its proof

A goal set as an outcome rather than a command -- "the export works" --
never resolves. Propose one the transcript can show instead.

## 2 -- Context, never an ID alone

`reqctl context UID [UID ...]` for every item in scope. Read all of what it
prints:

- `kind` -- `requirement` or `guard`. A requirement is satisfied in the
  product, a guard in the code that enforces it; the build cites no
  requirement, and the product cites no guard.
- `status` -- only `approved` may be implemented. A draft is a proposal, and
  code citing one fails `reqctl trace`. Stop, and ask the owner to carry it
  through `elucidate`.
- terms, parameters, and the requirements around it -- a statement that leans
  on another is not satisfied by reading one of them.
- `implementation` and `tests` -- what already cites this requirement. Extend
  that unit rather than opening a second one beside it.
- a suspect link -- the target moved and nobody has reread the pair. Stop:
  `reqctl validate` already refuses the corpus, and the owner resolves it with
  `reqctl revise UID --ack TARGET` on a requirements pull request of its own.

## 3 -- Write

The smallest unit whose behaviour satisfies the statement, and no more of it
than the statement asks. Read every acceptance criterion against it: the
verification is inspection, and a criterion the code does not meet is a
requirement not yet satisfied.

Cite it with `reqctl tag PATH --from N --to M --req UID`, over the whole
statements that satisfy it. The tool writes the stamp; never compose one.

## 4 -- Prove it

`reqctl validate`, then `reqctl trace`.

Re-stamping is not the fix for a stale pin: the statement moved under the code,
so read the code against the one that now stands, then `reqctl repin ID`.

A requirements pull request lands with its citations left behind. Clearing them
is the next pull request's work, and until it lands every other one is
refused.

Then the checks covering what you touched -- the rules under `.claude/rules/`
name them per area.

## 5 -- Hand off

`/pre-pr` before the pull request, not from here.
