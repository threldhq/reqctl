---
paths:
  - "reqctl/**"
  - "plugin/**"
  - ".github/**"
  - ".claude/hooks/**"
---

# Comment and help budgets

A directive that belongs to one file is named in `comment_budget.ALLOWED`
against that file; a citation belongs wherever the code it governs is, so the
budget reads it by shape instead and counts it as nothing. CI holds the count of
what is left at zero and refuses a file type it has no rule for.

Prose inside a string is invisible to that guard, so argparse `help=` and
`description=` are counted by their own budget in `ci.yml`. What survives it is
`reqctl`'s, which a session reads through `reqctl --help` rather than the whole
of `cli.py`. A script nothing hand-drives carries none: its caller states the
arguments.
