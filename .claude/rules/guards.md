---
paths:
  - ".github/guards/**"
  - ".claude/hooks/**/*.py"
  - ".claude/skills/elucidate/**/*.py"
  - ".github/*.py"
---

# Guard messages

A message states the fault, and the remedy where the fault does not imply one.
It is read by the session that has to clear it, so it names what to change, not
what to understand. It does not state why the rule exists: that asserts
something about a system outside this repository, which reading this one cannot
confirm.
