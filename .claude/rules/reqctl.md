---
paths:
  - "reqctl/**"
---

# reqctl

A fault the owner has to act on is a `ReqctlError`. `main` catches it, prints
`reqctl: <message>` to stderr and exits 1; under `--json` it becomes
`{"error": ...}`. An `OSError` or `UnicodeError` reaching `main` is stated the
same way, so the environment failing is a diagnosis rather than a crash;
anything else raised is a defect in reqctl and keeps its traceback.

A baseline file holding an unresolved merge is regenerated with `reqctl
baseline --generate`, which cuts the one that follows the baseline the default
branch carries, as any other cut does; with no default branch to follow it is
refused. It is never resolved by merging: not by hand, and not by a strategy such as `-X theirs`,
which resolves the conflicting hunk and leaves the surviving number claiming a
set it was never cut for. `check` compares the manifest against the corpus and
the number against the one it supersedes, so a merged file that happens to hold
the right items passes while the number means two different things on two
branches.

The gates: `ruff check reqctl` and `mypy --config-file reqctl/pyproject.toml
reqctl/reqctl`.

`reqctl` is the product this repository builds, so a statement about what it
does states "the product shall" and is a `REQ`. The code satisfying one cites
it with a statement citation written by `reqctl tag`. A `GUARD` states
"the build shall" and belongs to what makes and checks reqctl, not under
`reqctl/`.
