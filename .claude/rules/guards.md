---
paths:
  - ".github/guards/**"
  - ".github/tests/**"
  - ".claude/hooks/**/*.py"
  - ".claude/skills/elucidate/**/*.py"
  - ".github/*.py"
---

# Guard messages

A message states the fault, and the remedy where the fault does not imply one.
It is read by the session that has to clear it, so it names what to change, not
what to understand. It does not state why the rule exists: that asserts
something about a system outside this repository, and a test can only prove the
words are present, never that they are true.

Assert every message by its words in the guard's self-test, then mutate the
message and watch the test fail. A message no test asserts is prose nothing
catches going stale.

Each area runs its own self-test, named as `ci.yml` names it: the hook
(Requirements guard self-test, Hook exits are explicit decisions, Session
start installs what CI installs), the elucidate scripts (Elucidate synthesis
self-tests), `travel_alone` and `verify` (Travel-alone guard self-test, CI
gating self-test).
