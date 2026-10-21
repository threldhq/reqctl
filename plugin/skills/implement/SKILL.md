---
# @req+ REQ-38288492@4l6tMNjp19tH s4a54e
name: implement
description: >
  Write code against an approved requirement: read its neighbourhood through
  reqctl context, build the smallest unit that satisfies the statement, cite it
  with reqctl tag, and prove it. Use whenever the owner asks
  for behaviour to be built, changed or fixed under a requirement, and whenever
  they say implement. Not for writing or revising requirements -- that is
  elucidate -- and not for the pass a finished branch gets, which is pre-pr.
# @req- s4a54e
---

<!-- @req> REQ-38288492@4l6tMNjp19tH qtmeg3 -->
# Implement

<!-- @req+ REQ-78565105@gNZXM5rWTIsd lkg3bt -->
Change no item of the corpus beyond the citation lists and pins that
`reqctl tag`, `reqctl repin` and `reqctl untag` write.
<!-- @req- lkg3bt -->

<!-- @req+ REQ-12624929@r4P8zcs-nCzF og7snz -->
Propose a goal whose condition names a command whose output in the transcript
shows the goal is met.
<!-- @req- og7snz -->

<!-- @req+ REQ-73872444@EbHHiAk1JPxy fbv4ew -->
Before writing code, run `reqctl context` for each item the work cites or
changes, and read all that it prints.
<!-- @req- fbv4ew -->

<!-- @req+ REQ-37860556@jW4l6gj25YSj 2fcayq -->
An item that is a draft: stop, and put a question for the owner asking that it
be carried through the elucidate skill.
<!-- @req- 2fcayq -->

<!-- @req+ REQ-92625638@mg6T2YCudWIX bkjx56 -->
An item with a suspect link: stop, and put a question for the owner asking that
the link be resolved on a requirements pull request of its own.
<!-- @req- bkjx56 -->

<!-- @req+ REQ-91999340@aXqzmdm7TRCa 4gxzve -->
Where code already cites a requirement, extend it rather than writing a second
function, class or file for that requirement.
<!-- @req- 4gxzve -->

<!-- @req+ REQ-16376491@pLH6qM9Dx4wh hr6rvl -->
Where code a statement citation covers does not satisfy the item the citation
names, put a question for the owner: change the code, or revise the item. Where
that item is deprecated, ask nothing, and remove the citation with
`reqctl untag ID`.
<!-- @req- hr6rvl -->

<!-- @req+ REQ-83654288@zCIRC3g5z-mw sesbd4 -->
Before writing new code rather than extending code that already cites the
requirement, research the code of products solving the same kind of problem,
in any field, for a best-in-class example of that code. The pull request body
names the sources read and the example chosen, or states that none could be
read.
<!-- @req- sesbd4 -->

<!-- @req+ REQ-19907797@Tp3qg0hgddNV ck3qdz -->
Write no more code than satisfies the item's statement and each of its
acceptance criteria. Read the code against each criterion: a criterion the code
does not meet is a requirement not yet satisfied.
<!-- @req- ck3qdz -->

<!-- @req+ REQ-51861325@moFDyEUEg6uH meopvo -->
Cite a requirement at the code of the product that satisfies it, and none at
code of the build that carries no behaviour of the product.
<!-- @req- meopvo -->

<!-- @req+ REQ-97447029@k0kq0OlufVGp np46an -->
Cite a guard at the code that enforces its rule of the build, and none at code
of the product that enforces no rule of the build.
<!-- @req- np46an -->

<!-- @req+ REQ-36402602@Usc_d_wlZ4Zr vuyexu -->
Write each statement citation with `reqctl tag PATH --from N --to M --req UID`
and never by hand: it covers whole code statements, and no stamp is composed.
<!-- @req- vuyexu -->

<!-- @req+ REQ-34984028@TZ0U0-vLTqkz vc4i2s -->
Cover the code that decides a clause or acceptance criterion of the item
cited, or, for a parameter, a data item or one of its entries, the code stating
its value -- where a data item's entries are stated in one place and read in
another, the place stating them -- and every line that code names, directly or
through what those lines name, that no citation digest takes in. A Python
citation's digest takes in each function, class and constant of the code base its
lines name, and what those name in turn, so those get no citation of their own;
code in any other language that the lines name is cited too.
<!-- @req- vc4i2s -->

<!-- @req+ REQ-10074279@gXZHp2too_ik vlm5uy -->
Once code is written, run `reqctl validate` and then `reqctl trace`, and run
both again after each fix until both succeed. Show their output; never assert
that they passed.
<!-- @req- vlm5uy -->

<!-- @req+ REQ-34892304@rXQfzQkFuk5E ogny6p -->
Re-pin a statement citation `reqctl trace` reports as stale only after reading
the code it covers against the statement that now stands, then `reqctl repin ID`.
<!-- @req- ogny6p -->

<!-- @req+ REQ-12794184@iYrsgIzQswhY rizcvl -->
When a merged pull request that changed the corpus has left code citing
statements it changed, re-pinning those citations is the next pull request.
<!-- @req- rizcvl -->

<!-- @req> REQ-97236037@icu11Yon0Leb jhaqo3 -->
`/pre-pr` runs after this skill and before the pull request is opened.
