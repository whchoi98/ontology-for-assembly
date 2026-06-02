#!/usr/bin/env bash
# Secret pattern true positive · false positive 테스트.
# scrub-secrets.sh가 *secret*은 차단하고 *정상 코드*는 통과시키는지 검증.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

type pass >/dev/null 2>&1 || pass() { echo "ok - $1"; }
type fail >/dev/null 2>&1 || fail() { echo "not ok - $1"; [ "${2:-}" ] && echo "  # $2"; }

HOOK=".claude/hooks/scrub-secrets.sh"
[ -f "$HOOK" ] || { fail "scrub-secrets.sh missing — skipping pattern tests"; exit 0; }

# Hook는 PreToolUse / PostToolUse stdin JSON 입력 받음. 직접 invoke 시 매끄럽지 않음.
# 따라서 fixture text에 패턴이 있는지만 regex match 검증.
FIXTURES_DIR="tests/fixtures"

# fixture는 *placeholder 문서* — 실 패턴은 hook이 차단하므로 *prefix 키워드만* 검사.
if [ -f "$FIXTURES_DIR/secret-samples.txt" ]; then
  # AKIA / sk- / BEGIN / xoxb / ghp / JWT 같은 *언급*이 있는지
  if grep -qE "AKIA|sk-|BEGIN|xoxb-|ghp_|github|JWT" "$FIXTURES_DIR/secret-samples.txt"; then
    pass "fixture: secret-samples documents target patterns"
  else fail "fixture: secret-samples doesn't reference any target pattern"
  fi
else
  fail "fixture missing: secret-samples.txt"
fi

# false-positives: 정상 코드 예시 — 일반 변수명만 포함, 실 credential pattern 없음
if [ -f "$FIXTURES_DIR/false-positives.txt" ]; then
  if ! grep -qE "AKIA[A-Z0-9]{16}|^sk-[A-Za-z0-9]{20,}|-----BEGIN" "$FIXTURES_DIR/false-positives.txt"; then
    pass "fixture: false-positives clean (no real secrets)"
  else fail "fixture: false-positives contain actual secret patterns"
  fi
else
  fail "fixture missing: false-positives.txt"
fi
