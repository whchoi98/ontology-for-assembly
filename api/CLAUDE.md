# api/ — FastAPI Backend (Python 3.12, ARM64)

`api/`는 14 시나리오 라우터 + 17 서비스 wrapper + 6 페르소나 인증 분기를 담은 백엔드. 같은 Docker 이미지가 API 서버와 일회성 데이터 로더(`python -m data.load`)로 양용된다.

## Structure

```
api/
├── main.py                       # 17 라우터 등록 + 미들웨어 체인
├── config.py                     # Pydantic Settings (env)
├── aws_clients.py                # @lru_cache boto3 session factory
├── middleware_auth.py            # Cognito JWT (staff/subscriber) + B2B API Key 분기
├── routers/
│   ├── search.py                 # A 의미 검색
│   ├── chat.py                   # B 3단계 진화 챗봇 (Chatbot/Agent/Agentic)
│   ├── insights.py               # C 기사 인사이트
│   ├── persona_match.py          # D 페르소나 매칭
│   ├── cluster.py                # E 의원 클러스터링
│   ├── lookalike.py              # F 룩어라이크
│   ├── article_roi.py            # G 기사 ROI
│   ├── district_map.py           # H 지역구 지도
│   ├── neutrality.py             # I 편향·중립성
│   ├── external_signal.py        # J 외부 신호 융합
│   ├── outlier.py                # K 표결 이상치
│   ├── ad_match.py               # L 광고 매칭 (3-way)
│   ├── journey.py                # M 의원 정치 여정
│   ├── issue_legislation.py      # N 이슈 × 입법 상관
│   ├── objects.py                # 25+ 클래스 객체 탐색
│   ├── ontology.py               # 온톨로지 메타 (ER · 표준 · 검증)
│   ├── personas.py               # GET /api/personas (PERSONA_REGISTRY SSOT)
│   └── ops.py                    # /healthz, 운영 콘솔 패널
├── services/
│   ├── neptune.py                # openCypher wrapper (parameters 키워드 강제)
│   ├── opensearch.py             # BM25 + KNN + RRF
│   ├── bedrock.py                # Sonnet 4.6 invoke 단일 진입점
│   ├── agent.py                  # TOOL_SPECS 단일 등록점 + _dispatch_tool
│   ├── agentcore.py              # Memory + Code Interpreter
│   ├── guardrails.py             # Bedrock Guardrails + political_balance_score
│   ├── persona.py                # PERSONA_REGISTRY SSOT + system_prompt
│   ├── cohort.py                 # select(persona_id, scenario_code) → source list
│   ├── ad_matcher.py             # Lambda 호출 wrapper (3-mode)
│   ├── three_stage.py            # 시나리오 B 모드 분기 (stage1/2/3)
│   ├── multi_agent.py            # Stage 3의 4 에이전트 (Planner/Graph/Analyst/Editor)
│   ├── assembly_api.py           # 국회 OpenAPI 어댑터 (7+ 엔드포인트)
│   ├── external.py               # 네이버 뉴스 + SNS + 여론조사 어댑터
│   ├── reranker.py               # Cohere rerank-v3
│   ├── embedding.py              # Cohere embed-v4
│   ├── sse.py                    # SSE 이벤트 표준 helper
│   └── tools/                    # 도구 구현체 디렉토리
├── models/                       # Pydantic v2 도메인 모델
└── Dockerfile                    # API + 로더 겸용
```

## Key Design Decisions

- 6 페르소나 SSOT는 `services/persona.py:PERSONA_REGISTRY` (ADR-0002).
- 모든 LLM 호출은 `services/bedrock.py:invoke()` 경유 — Guardrails + neutrality suffix 자동 적용 (ADR-0004).
- Agent 도구 등록은 `services/agent.py:TOOL_SPECS` 단일점.
- 광고 매칭은 별도 Lambda — `services/ad_matcher.py`는 invoke wrapper만.
- 데이터 cohort 필터는 `services/cohort.py:select(persona_id, scenario_code)` — 모든 라우터가 호출.

## Conventions

- **Imports**: `from api.services import neptune` 형식. 순환 회피용 lazy import는 함수 body 안.
- **Cypher 파라미터**: 항상 `parameters={...}` 키워드. 사용자 입력 f-string interpolate 금지. `.claude/skills/cypher-conventions.md` 참조.
- **boto3**: `from api.aws_clients import session as boto_session` — factory 호출 후 `.client(...)`.
- **SSE**: `{"type": "phase|delta|log|final|result", "data": {...}}`. `services/sse.py` helper 사용.
- **F-strings**: `{}` 안 quote 이스케이프 금지. 로컬 변수 추출.
- **페르소나 lookup**: `PERSONA_REGISTRY.get(persona_id) or PERSONA_REGISTRY["editorial"]` (fallback 필수).
- **LLM 응답**: 모든 응답에 `political_balance_score`, `data_source` 첨부.

## Adding a New Scenario

`/CLAUDE.md` "Auto-Sync Rules" 9곳 체크리스트 참조. 백엔드 측 3곳:
1. `api/routers/<slug>.py` 새 라우터 파일
2. `api/main.py` 라우터 등록
3. `tests/test_smoke.py` parametrize entry

## Adding a New Agent Tool

1. `services/agent.py:TOOL_SPECS`에 JSON Schema entry 추가.
2. `_dispatch_tool` branch 추가.
3. 의존성 있으면 `services/agent.py:SYSTEM_PROMPT_CHAINING_HINTS`에 등록.
4. 도구 호출이 `log` SSE event로 자동 streaming되도록 `services/sse.py:emit_tool_call()` 사용.
5. `_TRACE_BUF` 링버퍼에 저장 (운영 콘솔 트레이스 panel).

## Related ADRs

- ADR-0001 (gcc 아키텍처 차용)
- ADR-0002 (6 페르소나 설계)
- ADR-0003 (대고객 확장 — 인증 다층화)
- ADR-0004 (정치 중립성 가드레일)
