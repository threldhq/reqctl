---
# @req+ REQ-38288492@4l6tMNjp19tH 3dxf7n
name: pre-pr
description: >
  The quality pass a branch gets before it becomes a pull request: the CI gates
  run locally, then succinctness, silent failure and comments. Use before
  opening any pull request that carries code -- a requirements pull request
  runs reqctl validate and reqctl baseline --check instead -- and whenever the
  owner says pre-pr.
# @req- 3dxf7n
---

<!-- @req> REQ-38288492@4l6tMNjp19tH twgacs -->
# Pre-PR

<!-- @req> REQ-76006040@TkSC3b2dW_YS fz5nx6 -->
Run the steps of the pass in the order this skill gives them.

<!-- @req> REQ-82829976@GA6KvnJAa1jt xh5md3 -->
Fix what a step finds before starting the next step.

<!-- @req+ REQ-21326520@Xe7THRpwH02F f4rorg -->
Where an agent the pass names does not resolve, stop the pass and put a
question for the owner; never run a different agent in its place.
<!-- @req- f4rorg -->

<!-- @req+ REQ-24229583@UrNzYDzLB7cC imqndm -->
Before each step that runs an agent, record the output of `git status` and the
commit HEAD names (`git rev-parse HEAD`).
<!-- @req- imqndm -->

<!-- @req+ REQ-97146077@4hRJH8jQmcjj 5i3pez -->
After each step that runs an agent, compare both with what was recorded before
that step.
<!-- @req- 5i3pez -->

<!-- @req+ REQ-83623105@AeUsg7xQ9X_V 6nhtiz -->
Set aside what an agent left -- `git reset --soft` to the commit recorded
before the step, then `git stash` -- rather than taking it as a finding.
<!-- @req- 6nhtiz -->

<!-- @req+ REQ-52512923@Yft4Zq-0-DMZ abvyex -->
Run `reqctl trace` and read the branch's diff for each behavioural change. On
finding one no approved requirement governs, stop the pass and put a question
for the owner asking that one be created.
<!-- @req- abvyex -->

<!-- @req+ REQ-33819161@O5VukwcHBX9h f7v7yc -->
Code enforcing a rule of the build cites the approved `GUARD` stating that
rule; cite what is missing with `reqctl tag` before going on. Where no guard
states the rule, stop the pass and ask the owner to create one.
<!-- @req- f7v7yc -->

<!-- @req+ REQ-78788058@k3hmt9gXlpDt ec6fz5 -->
A lockfile, a dependency manifest or a configuration file the branch changes is
held whole by the `GUARD` whose rule it serves -- `reqctl tag PATH --req UID`,
naming no lines -- before going on. Where no guard states that rule, stop the
pass and ask the owner to create one.
<!-- @req- ec6fz5 -->

<!-- @req+ REQ-34984028@TZ0U0-vLTqkz j6i32e -->
Cover the code that decides a clause or acceptance criterion of the item
cited, or, for a parameter, a data item or one of its entries, the code stating
its value -- where a data item's entries are stated in one place and read in
another, the place stating them -- and every line that code names, directly or
through what those lines name, that no citation digest takes in. A Python
citation's digest takes in each function, class and constant of the code base its
lines name, and what those name in turn, so those get no citation of their own;
code in any other language that the lines name is cited too.
<!-- @req- j6i32e -->

<!-- @req+ REQ-61212158@EISsRx_ntdvz bd2fgi -->
`python .github/verify.py`, where the repository carries it: it reads every
step of the `check` job from `.github/workflows/ci.yml` and runs the ones CI
would run for this tree, resolving the base-ref expression and computing the
`touched` outputs first. Where it carries none, run each step its CI
workflows state, copied from those files. Never retype the steps from memory:
they are more than a session recalls, and recalling them is how a run reports
green having invoked the wrong thing.
<!-- @req- bd2fgi -->

<!-- @req> REQ-50194960@i3SEmJi1QYT5 kqwkzf -->
Read each step the gates skipped, with the reason stated for it.

<!-- @req+ REQ-86092196@9J9t699MENdr 3iyp7h -->
Take a step the gates skipped for provisioning, or for a tool absent from the
session, as checked only by CI.
<!-- @req- 3iyp7h -->

<!-- @req+ REQ-54304000@TEvCMLPewLpu nd77dd -->
State in the pull request each step the gates skipped and the reason stated for
it.
<!-- @req- nd77dd -->

<!-- @req> REQ-28817717@8Xdz-kSb63h1 rf66iu -->
Run `/simplify` over the branch's diff.

<!-- @req> REQ-95204218@9MzEJ54_1PzP uqkkgl -->
Rank succinctness above simplicity and maintainability.

<!-- @req> REQ-80081791@-tGzsJetLhFp r3gd6k -->
Reject a suggestion of `/simplify` that adds code, names or indirection.

<!-- @req+ pre_pr_agents.silent_failure_hunter@g1C5-8nPZF5R hqp6ec -->
<!-- @req+ REQ-89802309@scSvke1X3gFa zuhffx -->
Run the `pr-review-toolkit:silent-failure-hunter` agent over the branch's diff
<!-- @req- hqp6ec -->
on `claude-sonnet-5-5`.
<!-- @req- zuhffx -->

<!-- @req+ REQ-61212158@EISsRx_ntdvz w4p2zx -->
`python .github/guards/comment_budget.py --max 0`, where the repository
carries it; where it does not, this step has nothing to run.
<!-- @req- w4p2zx -->

<!-- @req+ REQ-57899112@64ONbe8G-1dz 7kivsv -->
Open the pull request only once every step of the pass before it is clean: a
step is clean once every finding it made is fixed.
<!-- @req- 7kivsv -->

<!-- @req> REQ-89729325@YaLqg2PAK0fr bti6bz -->
Run the pass again after any commit made on the branch once the pass has run.

<!-- @req> REQ-90962130@o5kc67OEz0fP kh3pdd -->
State in the pull request what each step of the pass changed.

<!-- @req+ REQ-30003319@t1NWLDK_ppH5 n6qbmv -->
State in the pull request, of a step of the pass that found nothing, that it
ran.
<!-- @req- n6qbmv -->

<!-- @req+ REQ-51001407@CLFQHU6-XTzd hbi4d7 -->
List in the pull request every requirement, guard, parameter and data item
`reqctl compare` names -- the data item for a citation of one of its entries --
each with what reading the code citing it against the item found; where it
names none, say that none was touched.
<!-- @req- hbi4d7 -->

<!-- @req+ REQ-16376491@pLH6qM9Dx4wh zvf5ke -->
Where reading code a statement citation covers finds that the code does not
satisfy the item the citation names, put a question for the owner: change the
code, or revise the item. Write no pull request body before the owner answers.
Where that item is deprecated, ask nothing, and remove the citation with
`reqctl untag ID`.
<!-- @req- zvf5ke -->
