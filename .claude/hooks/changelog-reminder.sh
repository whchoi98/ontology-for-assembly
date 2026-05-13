#!/usr/bin/env bash
# Stop hook: emit a reminder to update CHANGELOG.md when structural project files
# were modified during this session but CHANGELOG.md wasn't touched.
#
# Reads JSON from stdin (Stop event payload). Always exits 0 — this hook only
# advises, never blocks. Output to stdout is appended to the model's view.

set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Files that, when modified, almost always warrant a CHANGELOG entry.
modified=$(git status --porcelain=v1 2>/dev/null \
  | awk '$1 ~ /^[MARC?]/{print $NF}' \
  | grep -E '^(api/routers/.+\.py|api/services/.+\.py|web/app/.+/page\.tsx|infra-cdk/lib/.+-stack\.ts|data/schemas\.py|ontology/(classes|relations|mappings)/.+)$' \
  || true)

if [[ -z "$modified" ]]; then
  exit 0
fi

# Was CHANGELOG.md also touched?
if git status --porcelain=v1 2>/dev/null | grep -qE 'CHANGELOG\.md$'; then
  exit 0
fi

# Structural files modified, CHANGELOG not — remind.
echo "[changelog-reminder] Structural files modified without a CHANGELOG.md update:"
echo "$modified" | sed 's/^/  - /'
echo "[changelog-reminder] Add an entry under [Unreleased] in CHANGELOG.md before committing."
exit 0
