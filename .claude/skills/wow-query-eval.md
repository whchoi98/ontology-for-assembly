---
name: wow-query-eval
description: Run the 14×6 wow evaluation matrix against the deployed CloudFront domain to verify search and scenario quality across all 14 scenarios × 6 personas. Use when measuring overall pass rate, before merging changes to api/services/search.py, api/routers/*.py, ontology/mappings/, data/, or when investigating regressions in semantic search or persona-aware scenario rendering.
---

# Wow Query Evaluation (14 시나리오 × 6 페르소나 = 84 케이스)

Project-specific quality gate. The harness has 84 demo-critical queries spanning the 14 scenarios × 6 personas matrix. The eval declares **≥85% pass rate** as the merge gate, plus **political_balance_score ≥0.8 평균** as a hard floor — both enforced by `sys.exit(1)` in the script.

## Pre-flight checks

Before running, verify:

1. **CloudFront reachable**: `curl -sI https://<deployed-domain>/healthz` returns 200.
2. **API healthy**: `curl -sI https://<deployed-domain>/api/healthz` returns 200.
3. **Cognito demo users provisioned**:
   - `staff@assembly-demo.net` (editorial / data·AI / ad-sales 페르소나)
   - `subscriber@assembly-demo.net` (paid subscriber 페르소나)
   - guest 쿠키 (anonymous reader)
   - B2B API Key (DynamoDB seeded)
   - 자세한 절차: `scripts/provision_demo_accounts.sh`
4. **Bedrock Guardrails ID 환경변수** 설정됨 (`BEDROCK_GUARDRAIL_ID`).

## Run

```bash
python3 scripts/eval_wow_queries.py --cf-domain <deployed-domain>
```

옵션:
- `--scenario A,B,L` — 특정 시나리오만
- `--persona editorial,general_reader` — 특정 페르소나만
- `--no-bias-check` — political_balance_score 검증 skip (디버깅 한정)

The script prints a per-query pass/fail row, an overall pass rate, 페르소나·시나리오별 breakdown, **평균 political_balance_score**, and exits non-zero if (pass rate < 85%) or (avg bias score < 0.8).

## Interpreting failures

If pass rate drops below 85%, investigate in this order:

1. **Per-persona breakdown** — 6 페르소나 중 한 곳만 실패하면 해당 페르소나의 KPI 가중치 또는 system prompt에 drift가 있을 가능성. `api/services/persona.py:PERSONA_REGISTRY` 변경 이력 확인.
2. **Per-scenario breakdown** — 시나리오 단일 실패는 해당 라우터의 회귀일 가능성. 특히 시나리오 B(3단계)·L(광고)·K(이상치)는 PDF 시그니처라 추가 주의.
3. **Keyword vocabulary** — A·F 시나리오 실패는 `ontology/mappings/`의 한국어 동의어 매핑 누락 가능성.
4. **Reranker fallback** — Cohere rerank-v3 사용 불가 시 RRF order fallback. 로그에서 "reranker unavailable" 확인.
5. **Guardrails 오인 차단** — 정치 중립성 가드레일이 정상 답변까지 차단하는 경우. `BEDROCK_GUARDRAIL_ID`의 룰 정밀화.

## Bias score 평균 < 0.8 인 경우

1. 실패한 쿼리의 응답 텍스트를 읽고 어느 정당이 한쪽으로 편향됐는지 확인.
2. `api/services/guardrails.py:bias_score` 계산 로직 확인 — 정당별 언급 빈도 표준편차가 맞게 계산되는지.
3. system prompt suffix가 LLM 호출 시점에 실제 첨부되는지 (lazy concat 누락 흔함).

## What "pass" means

- 시나리오별 기대 keyword가 응답 텍스트나 메타데이터 top-K에 등장.
- LLM 응답의 `political_balance_score ≥0.7` (개별 응답 임계, 평균 ≥0.8 별도).
- DataSourceBadge가 응답에 첨부되어 있어야 함 (시나리오 A·C·E·M 필수).
- 시나리오 L 응답에 AdMatchDecision id 첨부 필수.

## Related

- `.claude/commands/test-all.md` — broader test suite wrapper.
- `scripts/eval_wow_queries.py` — eval entry point.
- `api/services/guardrails.py` — bias score 계산.
- `api/services/persona.py:PERSONA_REGISTRY` — 페르소나 SSOT.
