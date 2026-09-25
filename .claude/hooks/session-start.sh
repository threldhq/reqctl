#!/bin/bash
set -euo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
venv="$root/.venv"
cd "$root"

"$venv/bin/python" -c "" 2>/dev/null || python3 -m venv --clear "$venv"

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  line="export PATH=\"$venv/bin:\$PATH\""
  grep -qxF "$line" "$CLAUDE_ENV_FILE" 2>/dev/null || echo "$line" >> "$CLAUDE_ENV_FILE"
fi

"$venv/bin/pip" install --quiet --disable-pip-version-check --require-hashes \
  -r reqctl/requirements-lock.txt \
  -r reqctl/requirements-dev-lock.txt
"$venv/bin/pip" install --quiet --disable-pip-version-check \
  -e reqctl --no-deps --no-build-isolation

.github/install-gitleaks.sh "$venv/bin" \
  || echo "session-start: gitleaks unavailable" >&2

"$venv/bin/reqctl" validate

"$venv/bin/reqctl" baseline --check 2>&1 || true

PATH="$venv/bin:$PATH" SETTLING=false \
  "$venv/bin/python" .github/guards/citations.py 2>&1 || true

"$venv/bin/reqctl" list term
"$venv/bin/reqctl" list parameter
"$venv/bin/reqctl" list data

reqs=$("$venv/bin/reqctl" list requirement | wc -l)
guards=$("$venv/bin/reqctl" list guard | wc -l)
echo "$reqs requirements and $guards guards are not listed here: search with" \
     "reqctl list requirement or reqctl list guard, read one with reqctl context UID"
