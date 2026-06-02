#!/usr/bin/env bash
# Hook 파일 존재·권한·등록 검증.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# 환경에서 헬퍼 import 실패 시 자체 정의 (sub-shell 호환)
type pass >/dev/null 2>&1 || pass() { echo "ok - $1"; }
type fail >/dev/null 2>&1 || fail() { echo "not ok - $1"; [ "${2:-}" ] && echo "  # $2"; }

# ─── hook 파일 존재 ────────────────────────────────────────────────────────
for hook in .claude/hooks/scrub-secrets.sh .claude/hooks/changelog-reminder.sh; do
  if [ -f "$hook" ]; then pass "hook exists: $hook"
  else fail "hook missing: $hook"
  fi
  if [ -x "$hook" ]; then pass "hook executable: $hook"
  else fail "hook not executable: $hook"
  fi
done

# ─── settings.json 등록 확인 ─────────────────────────────────────────────
if [ -f .claude/settings.json ]; then
  if grep -q "scrub-secrets" .claude/settings.json; then
    pass "settings.json: scrub-secrets registered"
  else fail "settings.json: scrub-secrets not registered"
  fi
  if grep -q "changelog-reminder" .claude/settings.json; then
    pass "settings.json: changelog-reminder registered"
  else fail "settings.json: changelog-reminder not registered"
  fi
else
  fail "settings.json missing"
fi

# ─── secret pattern smoke test ────────────────────────────────────────────
if [ -f .claude/hooks/scrub-secrets.sh ]; then
  if grep -qE "AKIA|ASIA|sk-|private[_-]?key|BEGIN.*PRIVATE" .claude/hooks/scrub-secrets.sh; then
    pass "scrub-secrets: scans common credential patterns"
  else fail "scrub-secrets: missing credential pattern coverage"
  fi
fi
