---
name: pre-pr
description: >
  The quality pass a branch gets before it becomes a pull request: the CI gates
  run locally, then succinctness, silent failure and comments. Use before
  opening any pull request that carries code -- a requirements pull request
  runs elucidate's own three checks instead -- and whenever the owner says
  pre-pr.
---

<!-- @req> REQ-38288492@1yCh_1wG8N-l twgacs -->
# Pre-PR

The branch is finished. This is the last pass before CI is the only thing
still checking it.

Run the steps in order and fix what each one finds before starting the next.
A finding you defer is a finding CI catches on a paid runner, or does not catch
at all.

Step 3 uses a plugin agent. If it will not resolve, **stop and ask the
owner** -- do not substitute a different agent.

Every agent in this pass has tool access that could write, whatever its own
prompt says it will do. Record `git status` and `git rev-parse HEAD` before
each step and compare both after: a clean tree alone says nothing, because it
is equally what a committed change leaves behind. What an agent left is its own
doing and not a finding -- revert it and read the report. Neither check reaches
an ignored path or anything outside the repository, and worktree isolation is
not the answer either: the worktree came up on the repository's head rather
than the branch under review, so the agent would read the wrong code.

## 1 -- Gates

First: every behavioural change on the branch cites its governing approved
requirement -- run `reqctl trace`, then read the diff for changes carrying no
`@req` tag. What builds the system cites none -- see CLAUDE.md. A change with
no governing requirement stops the pass; ask the owner to create one.

<!-- @req+ REQ-61212158@EISsRx_ntdvz bd2fgi -->
`python .github/verify.py`, where the repository carries it: it reads every
step of the `check` job from `.github/workflows/ci.yml` and runs the ones CI
would run for this tree, resolving the base-ref expression and computing the
`touched` outputs first. Where it carries none, run each step its CI
workflows state, copied from those files. Never retype the steps from memory:
they are more than a session recalls, and recalling them is how a run reports
green having invoked the wrong thing.
<!-- @req- bd2fgi -->

Read what it skipped. Every skip states its reason, and one of them --
provisioning, or a tool absent here -- means that step is only checked by CI.

Then run the tests this branch adds or changes five times, not once. A test
that passes on timing passes the first run too, and the suite will not tell
you which kind you wrote. If one cannot be made repeatable, say so in the
pull request rather than leaving a later run to surface it.

A pull request that lands red has wasted a runner and the owner's attention.

## 2 -- Succinctness

`/simplify` over the branch diff.

Succinctness outranks simplicity and maintainability. Reject any suggestion
that buys clarity with more code, more names, or more indirection -- that is
the trade most simplifiers are tuned to make.

## 3 -- Silent failure

The `pr-review-toolkit:silent-failure-hunter` agent over the branch diff.
Sonnet.

`reqctl` and the write-guard are gates. A gate that returns allowed when it
errors is worse than no gate, and nothing else in this pass looks for that.

## 4 -- Comments

<!-- @req+ REQ-61212158@EISsRx_ntdvz w4p2zx -->
`python .github/guards/comment_budget.py --max 0`, where the repository
carries it; where it does not, this step has nothing to run.
<!-- @req- w4p2zx -->

The count is zero and the guard holds it, so there is no judgement left to
make and no agent to run. It fails on a comment, a docstring, or a file type it
has no rule for. A directive a tool reads is exempt only once it is named in
`comment_budget.ALLOWED` and the tool has been run both ways to show what it
refuses without it.

## 5 -- Open it

Only once 1 to 4 are clean. Any commit after the pass means running the pass
again.

Say in the pull request what each step changed. A step that found nothing is
worth one line -- it tells the owner the pass ran.
