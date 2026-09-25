---
paths:
  - ".github/workflows/**"
  - ".github/**/*.sh"
  - ".claude/hooks/**/*.sh"
---

# Workflows and shell

`workflow_shape.py`, `actionlint` and `zizmor --offline` read every workflow.
Run all three before pushing.

A step that only matters for part of the tree is gated on the `touched` step in
`ci.yml`, which marks what the diff reaches. A new area needs its own `mark`
line, or its steps run on every pull request.

A step that imports a dependency runs after `Install`; before it, only the
standard library is there.

A directive a tool reads -- `zizmor: ignore`, `shellcheck disable` -- is the
only comment CI allows. Run the tool with it and without it, show what the tool
refuses without it, then name the file and the exact text in
`comment_budget.ALLOWED`. An unregistered directive fails the comment budget
like any other comment.
