---
description: Run code-reviewer + security-auditor agents in parallel on current unstaged changes
---

Run two specialized agents in parallel against the current unstaged + staged diff:

1. **code-reviewer** — bugs, security issues, project convention drift (CLAUDE.md gotchas, SSE vocab, ARM64 platform pin, persona consistency, ad matching, political neutrality).

2. **security-auditor** — secret leakage, IAM widening, network exposure, reader anonymity, political neutrality guardrail completeness, ad matching governance.

Both agents read SECURITY.md and CLAUDE.md before reviewing.

Each returns findings grouped by severity (Critical / High / Medium / Low). Combine the reports and present:

```
## code-reviewer
[findings...]

## security-auditor
[findings...]

## Summary
- Total Critical: N
- Total High: N
- Total Medium: N
- Total Low: N
- Recommended action: [BLOCK / FIX_HIGH / MERGE_WITH_NOTES]
```

If both agents end with "No high-confidence issues at Medium+ severity", recommendation = MERGE_WITH_NOTES.

If any Critical: BLOCK. If any High but no Critical: FIX_HIGH.

Use the Agent tool with `subagent_type=code-reviewer` and `subagent_type=security-auditor` (project agents — they don't appear in the top-level agent list).
