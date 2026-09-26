# Working a reqctl corpus

The corpus under `requirements/` is read and written only through `reqctl`. Never
edit an item or the baseline by hand, never read one except through `reqctl`, and
never reach one with `sed`, a redirect or a script.

`reqctl --help` lists what reqctl can do, `reqctl list` names what the corpus
holds, and `reqctl export` prints it.

Every change to what the product does cites a governing approved requirement. If
none exists, stop and ask the owner to create one.

Before implementing, run `reqctl context UID` for every requirement in scope and
read all it prints. Never implement from an ID alone, and never implement a
draft.

Cite the code that satisfies a requirement with
`reqctl tag PATH --from N --to M --req UID`, over the smallest region whose
behaviour satisfies it. Never compose or paste a citation. Once the code is read
against the statement that now stands, re-pin a stale citation with
`reqctl repin ID`; remove one that no longer governs with `reqctl untag ID`.

Verify code by reading it against the statement it cites: `reqctl compare` names
the cited regions a change touches, and `reqctl trace` must pass.

Drafting a requirement, marking one approved and cutting a baseline are
proposals. Approval is the merge, and only the owner merges. A pull request that
changes the corpus changes nothing else.

Commit the corpus, then run `reqctl baseline --generate`, then commit the
baseline. A baseline holding an unresolved merge is regenerated with
`reqctl baseline --generate`, never merged by hand. Run `reqctl validate` and
`reqctl baseline --check` before pushing a corpus change.
