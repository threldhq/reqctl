#!/bin/bash
set -euo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
venv="$root/.venv"
cd "$root"

"$venv/bin/python" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 13))' 2>/dev/null \
  || python3.13 -m venv --clear "$venv"

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  line="export PATH=\"$venv/bin:\$PATH\""
  grep -qxF "$line" "$CLAUDE_ENV_FILE" 2>/dev/null || echo "$line" >> "$CLAUDE_ENV_FILE"
fi

installed="$venv/session-start.installed"
wanted=$({ cat reqctl/requirements-lock.txt reqctl/requirements-dev-lock.txt reqctl/pyproject.toml
           "$venv/bin/python" -c 'import sys; print(sys.version)'; } | sha256sum)
if [ "$(cat "$installed" 2>/dev/null)" != "$wanted" ]; then
  "$venv/bin/pip" install --quiet --disable-pip-version-check --require-hashes \
    -r reqctl/requirements-lock.txt \
    -r reqctl/requirements-dev-lock.txt
  "$venv/bin/pip" install --quiet --disable-pip-version-check \
    -e reqctl --no-deps --no-build-isolation
  echo "$wanted" > "$installed"
fi

.github/install-gitleaks.sh "$venv/bin" \
  || echo "session-start: gitleaks unavailable" >&2

git remote set-head origin --auto \
  || echo "session-start: cannot read origin's default branch" >&2

state=$({ git ls-files -s
          git diff HEAD
          git ls-files -z --others --exclude-standard | xargs -0 -r git hash-object --
          git ls-files --others --exclude-standard
          git rev-parse -q --verify refs/remotes/origin/HEAD || true; } | sha256sum | cut -d' ' -f1)
replays="$venv/session-start.replays"
if [ -f "$replays/$state" ]; then
  cat "$replays/$state"
  exit 0
fi

held=$(mktemp)
{
  "$venv/bin/reqctl" validate

  "$venv/bin/reqctl" baseline --check 2>&1 || true

  PATH="$venv/bin:$PATH" "$venv/bin/python" .github/guards/citations.py 2>&1 || true

  "$venv/bin/reqctl" list term
  "$venv/bin/reqctl" list parameter
  "$venv/bin/reqctl" list data

  reqs=$("$venv/bin/reqctl" list requirement | wc -l)
  guards=$("$venv/bin/reqctl" list guard | wc -l)
  echo "$reqs requirements and $guards guards are not listed here: search with" \
       "reqctl list requirement or reqctl list guard, read one with reqctl context UID"
} | tee "$held"
rm -rf "$replays"
mkdir -p "$replays"
mv "$held" "$replays/$state"
