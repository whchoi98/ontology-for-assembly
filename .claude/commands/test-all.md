---
description: Run the full test surface (TS + Python AST + pytest + CDK snapshot + wow-query eval)
---

Execute the project's test surface in this order, stopping at first failure:

1. **TypeScript type-check** (web + infra-cdk):
   ```bash
   cd web && npx tsc --noEmit && cd -
   cd infra-cdk && npx tsc --noEmit && cd -
   ```

2. **Python syntax** (AST validate every router + service + data module):
   ```bash
   python3 -m compileall -q api data scripts
   ```

3. **pytest smoke + integration** (offline, ~1초):
   ```bash
   pytest tests -q
   ```

4. **CDK snapshot tests** (6 stacks, ~13초):
   ```bash
   cd infra-cdk && npx jest --ci
   ```

5. **Wow-query evaluation** (requires deployed CloudFront):
   ```bash
   python3 scripts/eval_wow_queries.py
   ```
   Target: pass-rate ≥85% across 84 cases (14 시나리오 × 6 페르소나), average `political_balance_score` ≥0.8, average latency <2s.

6. **Smoke test** the critical paths via CloudFront:
   ```bash
   DOMAIN=$(aws cloudformation describe-stacks --stack-name assembly-edge \
     --query 'Stacks[0].Outputs[?OutputKey==`PublicDomain`].OutputValue' --output text)
   curl -fsS https://$DOMAIN/healthz
   curl -fsS -X POST https://$DOMAIN/api/search \
     -H 'content-type: application/json' \
     -H 'X-Persona-Id: editorial' \
     -d '{"q":"AI 관련 법안","top_k":5}' | jq '.hits | length'
   curl -fsS -X POST https://$DOMAIN/api/ad-match \
     -H 'content-type: application/json' \
     -H 'X-Persona-Id: general_reader' \
     -d '{"article_id":"art_001","mode":"agent"}' | jq '.decision.allowed'
   ```

Report each step's outcome. If anything fails, surface the exact error and propose a fix.

**Steps 1–4 are CI gates** (run on every push/PR via `.github/workflows/ci.yml`).
**Step 5–6 require a deployed environment** — use only for pre-merge live verification.
