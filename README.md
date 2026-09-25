# reqctl

> The corpus is the only approved statement of what this tool does. This page
> orients; `reqctl --help` is the index.

A requirements system that governs itself. A corpus of numbered, stamped items
— requirements, parameters, terms and data registers — is the approved
statement of how reqctl behaves, and every unit of code that satisfies one
cites it by uid and by a digest of the statement it was written against. When a
statement changes its digest changes, so the citation goes stale loudly rather
than silently.

## Parts

- **`reqctl`** — the CLI. Mints, revises, relates, validates, traces and
  baselines the corpus, and is the only thing that touches a corpus file.
- **`reqportal`** — a single page that reads what `reqctl` emits.
- **`elucidate`** — a skill that draws statements out of what the owner says
  and proposes them for approval.

## Making a change

1. `reqctl context UID` — read the statement and what it relates to.
2. Write the code, and cite it with `reqctl tag PATH --from N --to M --req UID`.
3. `python .github/verify.py` — run what CI runs.

Approval is the merge: only `main` states what is approved.
