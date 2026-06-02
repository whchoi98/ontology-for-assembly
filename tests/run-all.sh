#!/usr/bin/env bash
# Harness validation 테스트 runner — TAP-style 출력.
#
# 두 종류 테스트 실행:
# 1. tests/hooks/      — Claude Code hook 동작 (secret scan·changelog reminder 등)
# 2. tests/structure/  — 프로젝트 구조 (CLAUDE.md sections, manifest, file presence)
#
# Python pytest는 별도 — `make test` 또는 `pytest tests/test_*.py`로 실행.
#
# Usage: bash tests/run-all.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ─── TAP-style 헬퍼 ────────────────────────────────────────────────────────
TESTS_RUN=0
TESTS_PASS=0
TESTS_FAIL=0

# shellcheck disable=SC2034
TAP_PLAN=0  # plan 모드는 미사용 (running tally)

pass() { TESTS_RUN=$((TESTS_RUN+1)); TESTS_PASS=$((TESTS_PASS+1)); echo "ok $TESTS_RUN - $1"; }
fail() { TESTS_RUN=$((TESTS_RUN+1)); TESTS_FAIL=$((TESTS_FAIL+1)); echo "not ok $TESTS_RUN - $1"; [ "${2:-}" ] && echo "  # $2"; }

assert_file_exists() {
  if [ -f "$1" ]; then pass "$2: file exists ($1)"
  else fail "$2: file missing" "$1"
  fi
}
assert_executable() {
  if [ -x "$1" ]; then pass "$2: executable"
  else fail "$2: not executable" "$1"
  fi
}
assert_contains() {
  if grep -q "$2" "$1" 2>/dev/null; then pass "$3"
  else fail "$3" "expected pattern '$2' in $1"
  fi
}
assert_not_contains() {
  if ! grep -q "$2" "$1" 2>/dev/null; then pass "$3"
  else fail "$3" "unexpected pattern '$2' in $1"
  fi
}

# Export 헬퍼 functions to subshells
export -f pass fail assert_file_exists assert_executable assert_contains assert_not_contains
export TESTS_RUN TESTS_PASS TESTS_FAIL

# ─── 실행 ───────────────────────────────────────────────────────────────────
echo "1..N  # running harness tests..."
echo ""

# 각 sub-suite는 자체 counter 가지지만 출력만 — exit code는 합산.
for suite in tests/hooks/test-*.sh tests/structure/test-*.sh; do
  [ -f "$suite" ] || continue
  echo "# --- $suite ---"
  bash "$suite" || true
  echo ""
done

# ─── 요약 ───────────────────────────────────────────────────────────────────
echo "# === Summary ==="
echo "# tests: $TESTS_RUN, pass: $TESTS_PASS, fail: $TESTS_FAIL"

[ "$TESTS_FAIL" -eq 0 ]
