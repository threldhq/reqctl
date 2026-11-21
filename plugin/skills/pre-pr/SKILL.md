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

<!-- @req+ REQ-34984028@_psCZf8dpJ_A j6i32e -->
Cover the code that decides a clause or acceptance criterion of the item
cited, or, for a parameter, a data item or one of its entries, the code stating
its value -- where a data item's entries are stated in one place and read in
another, the place stating them -- and every line that code names directly that
no citation digest takes in. A Python citation's digest takes in each function,
class and constant of the code base its lines name, a JavaScript citation's each
function and const, let or var binding declared at the top level of the same
file, and a TypeScript citation's those and each enum declared there, so what a
digest takes in gets no citation of its own; JavaScript or TypeScript in another
file, and code in any other language, that the lines name directly is cited too.
<!-- @req- j6i32e -->

<!-- @req+ REQ-31745207@1VD3x72ROTWR hmkvrl -->
Code the deciding code names only through other code, which no citation digest
of the item takes in, is cited to the item that states what that code does, not
to each item whose cited code reaches it.
<!-- @req- hmkvrl -->

<!-- @req+ REQ-35185256@S__PTrxlMclw q3hef6 -->
Where no item states what code named only through other code does, put a
question for the owner asking for an item that states it, and write no citation
over that code before the owner answers.
<!-- @req- q3hef6 -->

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

<!-- @req+ REQ-89802309@scSvke1X3gFa zuhffx -->
<!-- @req> pre_pr_agents.silent_failure_hunter@rfHy5sm8yGhu xxldqg -->
Run the `pr-review-toolkit:silent-failure-hunter` agent over the branch's diff
on `claude-sonnet-5-5`.
<!-- @req- zuhffx -->

<!-- @req+ REQ-61212158@EISsRx_ntdvz w4p2zx -->
`python .github/guards/comment_budget.py --max 0`, where the repository
carries it; where it does not, this step has nothing to run.
<!-- @req- w4p2zx -->

<!-- @req+ REQ-18193596@I26mta6oEsfZ 5k4yld -->
Run `python3 ${CLAUDE_SKILL_DIR}/reading.py build`: it writes one prompt for
each requirement, guard, parameter and data item the branch touches, and names
each item that needs a reading.
<!-- @req- 5k4yld -->

<!-- @req+ REQ-85663008@z5Y4x8rasoxc vyfku6 -->
The reading workflows it writes hold one reading agent for each item it names
as needing a reading, and none for an item read before as satisfied from an
identical prompt: by a reading agent, or by a searching reader while every file
its reply named is unchanged. They hold none either for an item whose code the
owner accepted against an identical prompt while, where a searching reader read
the item, every file its reply named is unchanged.
<!-- @req- vyfku6 -->

<!-- @req+ REQ-17805226@pdUrFTsMz_Wx ryz5cx -->
Spawn the reading agents of the pass by running each reading workflow that the
script building their prompts, `reading.py build`, wrote for the pass: one call
of the Workflow tool for each, `scriptPath` at the file it names and no `args`.
<!-- @req- ryz5cx -->

<!-- @req> REQ-70511521@twPRafax5PKB rq2qry -->
Pass no prompt text to a reading agent yourself.

<!-- @req+ REQ-18882967@W34Ole45XgJE hutvpr -->
Run `python3 ${CLAUDE_SKILL_DIR}/reading.py take`: it takes each reading
agent's verdict with the lines that show it, and names each item that has no
verdict.
<!-- @req- hutvpr -->

<!-- @req+ REQ-12678136@0uDF0n6a2v1j qhmgbr -->
<!-- @req+ REQ-18264143@WAQF00ATdLzX beiiyk -->
With a verdict of not satisfied or cannot tell, `take` and `searched` take the
one sentence the reply gives as at issue, and print it; a reply of either
verdict without that sentence is no verdict.
<!-- @req- beiiyk -->
<!-- @req- qhmgbr -->

<!-- @req+ REQ-77379732@dFXrgstPkXaL s2kcnh -->
<!-- @req+ REQ-69173794@fzaCORJxLXi5 zuixui -->
<!-- @req+ REQ-13095275@W9v3hH4NZDqh 2qolcv -->
For each item whose reading agent returned cannot tell or no verdict, `take`
writes that reading agent's prompt into a reading workflow for a searching
reader, and names the workflow.
<!-- @req- 2qolcv -->
<!-- @req- zuixui -->
<!-- @req- s2kcnh -->

<!-- @req+ REQ-44819741@wl--3l7T9I_q biy6g6 -->
Spawn the searching readers of the pass by running each reading workflow that
`reading.py take` wrote for them: one call of the Workflow tool for each,
`scriptPath` at the file it names and no `args`.
<!-- @req- biy6g6 -->

<!-- @req+ REQ-18486982@ovAUIy1DmRVv yccjrf -->
<!-- @req+ REQ-21983975@PaeNX9-i1wlQ zaqd6h -->
Run `python3 ${CLAUDE_SKILL_DIR}/reading.py searched`: it takes each searching
reader's verdict with the lines that show it and the file each line stands in,
and names each item that has no verdict.
<!-- @req- zaqd6h -->
<!-- @req- yccjrf -->

<!-- @req+ REQ-87568267@JmZEPF8Ng69z 7l6dgd -->
<!-- @req+ REQ-18418155@kQKuNMnvZhlx n3xbym -->
A searching reader's satisfied verdict is taken only where it gives lines for
each acceptance criterion of the item and each line stands in the prompt or in
the file named for it, outside the corpus; otherwise the item has no verdict.
<!-- @req- n3xbym -->
<!-- @req- 7l6dgd -->

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
<!-- @req+ REQ-56883985@Uk2MFr8R8HUr oyxth4 -->
Where a reading agent returns not satisfied for an item, or the item's searching
reader returns not satisfied, cannot tell or no verdict -- a satisfied reply
that `searched` did not take is no verdict -- put a question for the owner:
change the code, revise the item, or accept the code as satisfying the item.
Write no pull request body before the owner answers. Ask nothing about an item
whose reading agent returned cannot tell or no verdict before its searching
reader returns, and nothing about an item whose searching reader returned
satisfied. Ask nothing about an item the pass spawned no reading agent for:
`build` names it as read before or as accepted by the owner.
<!-- @req- oyxth4 -->

Where the item a statement citation names is deprecated, ask nothing, and
remove the citation with `reqctl untag ID`.
<!-- @req- zvf5ke -->

<!-- @req+ REQ-68224602@Aebq69197_27 2tealp -->
State in that question, with a verdict of not satisfied or cannot tell, the
sentence `take` or `searched` printed as at issue with the verdict.
<!-- @req- 2tealp -->

<!-- @req+ REQ-42425794@haYtnGYRwgcG 6br7yh -->
Where the owner accepts the code as satisfying an item, run
`python3 ${CLAUDE_SKILL_DIR}/reading.py accept UID`: it records the acceptance
against the item and the prompt built for the item's reading agent, so the
acceptance counts only while that prompt is unchanged.
<!-- @req- 6br7yh -->

<!-- @req+ REQ-58972279@TE27xoNYxoQq nmtp3f -->
<!-- @req+ REQ-93326833@RQp2KSyOF_lP fzw5ve -->
Give `accept` the reason the owner gives, as `--reason "..."`: it records the
reason with the acceptance, and refuses to record an acceptance given none.
<!-- @req- fzw5ve -->
<!-- @req- nmtp3f -->

<!-- @req+ REQ-63323162@-dWXL3C-LaxX 5k3ohn -->
Run `python3 ${CLAUDE_SKILL_DIR}/reading.py stated` and put what it prints in
the pull request body: for each item the branch touches, the reading agent's
verdict with the lines that show it, the searching reader's where one was
spawned, with the lines it gave for each acceptance criterion, and the owner's
acceptance where one is recorded, also for an item this pass did not read
again.
<!-- @req- 5k3ohn -->

<!-- @req+ REQ-80563826@LhN5BKyOutx2 o43yvd -->
<!-- @req+ REQ-10332610@PHoJmeAqUqB5 r5jz5i -->
With each verdict of not satisfied or cannot tell it states the sentence taken
with the verdict, and with each acceptance the reason recorded with it.
<!-- @req- r5jz5i -->
<!-- @req- o43yvd -->

<!-- @req+ REQ-55343532@_Cx35RaHIOyc zdqpjy -->
Run `reqctl evidence` and put the evidence block in the pull request body as
it prints it.
<!-- @req- zdqpjy -->
