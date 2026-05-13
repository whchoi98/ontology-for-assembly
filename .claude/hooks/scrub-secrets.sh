#!/usr/bin/env bash
# PreToolUse + PostToolUse hook: detect and block tool inputs/outputs containing secret patterns.
#
# Reads JSON from stdin: {"tool_name": "...", "tool_input": {...}}.
# Exit 0 = allow, exit 2 = block (with stderr message shown to the model).
#
# Patterns detected:
#   - AWS access key IDs (AKIA / ASIA prefix)
#   - aws_secret_access_key followed by a 40+ char value
#   - Private key blocks (RSA / EC / OPENSSH / DSA / PGP)
#   - JWT format (3 base64url segments)
#   - Slack tokens (xoxb / xoxp / xoxa / xoxr / xoxs)
#   - GitHub personal access tokens (ghp_*, gho_*, ghu_*, ghs_*, ghr_*)
#   - 국회 OpenAPI key 추정 패턴 (40+ char alphanumeric after "assembly_api_key")
#   - Naver API client_secret 추정 패턴

set -euo pipefail

input="$(cat)"

declare -A patterns=(
  [aws_access_key]='AKIA[0-9A-Z]{16}'
  [aws_temp_access_key]='ASIA[0-9A-Z]{16}'
  [aws_secret_value]='aws_secret_access_key[[:space:]]*=[[:space:]]*[A-Za-z0-9/+=]{40,}'
  [private_key_block]='BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY'
  [jwt]='eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+'
  [slack_token]='xox[bpoars]-[A-Za-z0-9-]{10,}'
  [github_pat]='gh[opusr]_[A-Za-z0-9]{36,}'
  [assembly_api_key]='ASSEMBLY_OPENAPI_KEY[[:space:]]*=[[:space:]]*[A-Za-z0-9]{32,}'
  [naver_secret]='NAVER_NEWS_API_CLIENT_SECRET[[:space:]]*=[[:space:]]*[A-Za-z0-9]{16,}'
)

for name in "${!patterns[@]}"; do
  pattern="${patterns[$name]}"
  if printf '%s' "$input" | grep -qE "$pattern"; then
    echo "[scrub-secrets] BLOCKED: tool input contains a value matching pattern '$name'." >&2
    echo "[scrub-secrets] Remove the secret (use Secrets Manager / SSM Parameter Store) and try again." >&2
    exit 2
  fi
done

exit 0
