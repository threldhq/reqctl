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

<!-- @req+ REQ-19000493@GHvudq2uuiq1 a2mxuq -->
Before writing new code rather than extending code that already cites the
requirement, have a best-in-class check made of the third-party code that can
be reused for it.
<!-- @req- a2mxuq -->

<!-- @req+ REQ-32544293@2UJDijTDH1KJ khjpxx -->
Before extending code that already cites the requirement with a behaviour that
code does not have, have a best-in-class check made of the third-party code
that can be reused for that behaviour. A change that adds no behaviour needs no
check.
<!-- @req- khjpxx -->

<!-- @req+ REQ-46594931@M3uiWv_NWuJ_ axory4 -->
Spawn the best-in-class agent to make the check, with a prompt naming each of
the selection criteria: adoption, correctness record, licence and maintenance.
Build that prompt, then spawn the agent with one call of the Workflow tool,
`scriptPath` at the `workflow.js` beside the manifest the command names and
`args` holding the contents of that manifest:

```bash
python3 ${CLAUDE_SKILL_DIR}/../elucidate/synthesis/review.py weigh --run .elucidate/<run> --code "<the code to be written>"
```
<!-- @req- axory4 -->

<!-- @req+ REQ-38347678@QT6-FMODBgab ze536s -->
The check records, for each library and each example it weighs, the sources it
rests on and its standing against each of the selection criteria.
<!-- @req- ze536s -->

<!-- @req+ REQ-59435809@bHuMKX1_pkbz h4lkss -->
The check states whether an existing library should be used instead of writing
the code.
<!-- @req- h4lkss -->

<!-- @req+ REQ-48503136@eNAb4jIZahbK bwg3gk -->
Write no code for which a best-in-class check is required until the product has
passed that check:

```bash
python3 ${CLAUDE_SKILL_DIR}/../elucidate/synthesis/review.py weighed --run .elucidate/<run>
```

Where every fault over which it refuses the check is a transient failure, put a
question to the owner, and write that code only once they have answered that it
be written without a passed check.
<!-- @req- bwg3gk -->

<!-- @req+ REQ-45597762@a3hLC2ska6w_ dcm7k3 -->
The body of the pull request carrying the code states the summary the product
prints for the passed best-in-class check, or the owner's answer that the code
be written without a passed check.
<!-- @req- dcm7k3 -->

<!-- @req+ REQ-45217924@ari9LDpV6zFm muvf2i -->
Where the check states that an existing library should be used, add that
library as a dependency rather than writing the code.
<!-- @req- muvf2i -->

<!-- @req+ REQ-15108485@EkqTZa-9MGOY w2l4ri -->
Add a dependency only where its licence resolves to one of the SPDX identifiers
of the copyable licences below.
<!-- @req- w2l4ri -->

<!-- @req+ REQ-22202465@9t-83q3xJ4ip ant226 -->
Resolve the licence of each file you would copy from the SPDX licence
identifier the file states, else from the licence file in the nearest folder
above the file that holds one: a licence file nearer than the repository's root
one is the one that counts.
<!-- @req- ant226 -->

<!-- @req+ REQ-42211986@pTHWhTqWKc3j mgrqlm -->
Copy a file's code, unchanged or adapted, only where two things hold: the
file's licence resolves to one of these SPDX identifiers,
<!-- @req> copyable_licences@ns-krxMVBL57 kagdws -->
MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, 0BSD;
and the receiving repository's licence is one that licence's code may be copied
into:
the file's own licence, or Apache-2.0.
Where the file's licence is copyleft, weak copyleft included, the receiving
repository's licence is neither of those, or the file states no SPDX licence
identifier and no folder above it holds a licence file, copy none of it and
write your own code from the idea.
<!-- @req- mgrqlm -->

<!-- @req+ REQ-87714849@0xyTYSwdPQW5 a2jztj -->
Where a copied file's licence is Apache-2.0 and the repository holding the file
holds a NOTICE file, carry the attribution notices of that NOTICE file into the
third-party notices file.
<!-- @req- a2jztj -->

<!-- @req+ REQ-36108971@NoDvOdAAqqbz xr4cbg -->
Record each copy in `THIRD_PARTY_NOTICES.md` at the repository's root, creating
it if the repository holds no third-party notices file, and otherwise in the one
it holds: the source repository, the commit, the file, the full text of the
licence and the path the copy takes. No comment in the copied code names its
source.
<!-- @req- xr4cbg -->

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

<!-- @req+ REQ-34984028@9K2_3Vg-ud_i vc4i2s -->
Cover the code that decides a clause or acceptance criterion of the item
cited, or, for a parameter, a data item or one of its entries, the code stating
its value -- where a data item's entries are stated in one place and read in
another, the place stating them -- and every line that code names, directly or
through what those lines name, that no citation digest takes in. A Python
citation's digest takes in each function, class and constant of the code base its
lines name, a JavaScript citation's each function and const, let or var binding
declared at the top level of the same file, and a TypeScript citation's those and
each enum declared there, and what those name in turn, so those get no citation
of their own; JavaScript or TypeScript in another file, and code in any other
language, that the lines name is cited too.
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
