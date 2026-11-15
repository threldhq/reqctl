---
paths:
  - "**/*.toml"
  - "**/*.json"
  - "**/*.in"
  - "**/requirements*.txt"
  - ".github/CODEOWNERS"
  - ".github/dependabot.yml"
  - ".gitignore"
---

# Files that hold no citation

A lockfile, a dependency manifest or a configuration file holds no citation of
its own, so each item whose rule it serves cites it whole (REQ-78788058):
`reqctl tag PATH --req UID`, naming no lines. Where such a file carries the
build and no guard states the rule it serves, stop and ask the owner to create
one.
