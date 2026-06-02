#!/usr/bin/env bash
# 프로젝트 구조 검증 — CLAUDE.md 섹션·핵심 파일·multi-runtime 구조.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

type pass >/dev/null 2>&1 || pass() { echo "ok - $1"; }
type fail >/dev/null 2>&1 || fail() { echo "not ok - $1"; [ "${2:-}" ] && echo "  # $2"; }

# ─── 핵심 파일 ─────────────────────────────────────────────────────────────
for f in CLAUDE.md README.md SECURITY.md CHANGELOG.md Makefile requirements.txt \
         .claude/settings.json .gitignore .env.example .editorconfig; do
  if [ -f "$f" ]; then pass "file exists: $f"
  else fail "file missing: $f"
  fi
done

# ─── CLAUDE.md 섹션 ────────────────────────────────────────────────────────
if [ -f CLAUDE.md ]; then
  for section in "## Project" "## Tech Stack" "## Project Structure" "## Conventions" "## Auto-Sync Rules"; do
    if grep -qF "$section" CLAUDE.md; then
      pass "CLAUDE.md: section '$section'"
    else fail "CLAUDE.md: missing section '$section'"
    fi
  done
fi

# ─── multi-runtime: Python + Node.js ────────────────────────────────────
if [ -f requirements.txt ]; then pass "Python: requirements.txt present"; else fail "Python: requirements.txt missing"; fi
if [ -f web/package.json ]; then pass "Node.js: web/package.json present"; else fail "Node.js: web/package.json missing"; fi
if [ -d api ] && [ -f api/main.py ]; then pass "Python API entry: api/main.py"; else fail "Python API entry missing"; fi
if [ -d web/app ]; then pass "Next.js App Router: web/app/"; else fail "web/app/ missing"; fi

# ─── ADR (Architecture Decision Records) ─────────────────────────────────
ADR_COUNT=$(find docs/decisions -name "*.md" -not -name ".template.md" 2>/dev/null | wc -l)
if [ "$ADR_COUNT" -ge 1 ]; then pass "ADR count: $ADR_COUNT (>=1)"; else fail "no ADRs found"; fi

# ─── infra (CDK) ────────────────────────────────────────────────────────
if [ -d infra-cdk ] && [ -f infra-cdk/bin/assembly.ts ]; then
  pass "CDK entry: infra-cdk/bin/assembly.ts"
else
  fail "CDK entry missing (infra-cdk/bin/assembly.ts)"
fi

# ─── module CLAUDE.md ────────────────────────────────────────────────────
for mod in api web; do
  if [ -f "$mod/CLAUDE.md" ]; then pass "module CLAUDE.md: $mod/"
  else fail "module CLAUDE.md missing: $mod/"
  fi
done
