# api/ — FastAPI Backend (Python 3.12, ARM64)

`api/`는 21 라우터(23 시나리오) + 22 서비스를 담은 백엔드. 서비스는 대부분 시나리오별 `*_builder.py` 패턴. 인증은 API 계층이 아니라 edge(Lambda@Edge JWT + API Gateway API Key, ADR-0003)에서 강제 — API는 upstream을 신뢰(사실상 demo-public). 같은 Docker 이미지가 API 서버와 일회성 데이터 로더(`python -m data.load`)로 양용된다.

## Structure

```
api/
├── main.py                       # create_app() — 21 라우터 등록 (lazy import) + /healthz, /api/healthz
├── aws_clients.py                # @lru_cache boto3 session factory
├── routers/
│   ├── search.py                 # A 의미 검색 (/api/search)
│   ├── chat.py                   # B 3단계 진화 챗봇 (/api/chat, /api/chat/stream)
│   ├── insights.py               # C 기사 인사이트 (/api/insights/topics, /articles)
│   ├── persona_match.py          # D 페르소나 매칭 (/api/persona-match)
│   ├── cluster.py                # E 의원 클러스터링 (/api/cluster)
│   ├── lookalike.py              # F 룩어라이크 (/api/lookalike)
│   ├── article_roi.py            # G 기사 ROI (/api/article-roi)
│   ├── district_map.py           # H 지역구 지도 (/api/district-map)
│   ├── neutrality.py             # I 편향·중립성 (/api/neutrality)
│   ├── external_signal.py        # J 외부 신호 융합 (/api/external-signal)
│   ├── outlier.py                # K 표결 이상치 (/api/outlier)
│   ├── ad_match.py               # L 광고 매칭 3-way (/api/ad-match)
│   ├── journey.py                # M 의원 정치 여정 (/api/journey)
│   ├── issue_legislation.py      # N 이슈 × 입법 상관 (/api/issue-legislation)
│   ├── relations.py              # O 인물 관계 (/api/relations/{a}/{b})
│   ├── insights_advanced.py      # T·U·V·W (/api/insights/{party-cohesion,influence-rank,voting-cluster,swing-voters})
│   ├── insight_generic.py        # P·Q·R·S 범용 LLM narrative (POST /api/insight)
│   ├── members.py                # 의원 디렉토리 (/api/members, /ranking/{metric}, /{id}, /{id}/news)
│   ├── objects.py                # 31 클래스 Object Explorer (/api/objects/*) + 온톨로지 메타 (/api/ontology/*)
│   ├── personas.py               # GET /api/personas (PERSONA_REGISTRY SSOT)
│   └── ops.py                    # 운영 콘솔 5 패널 (/api/ops/*)
├── services/
│   ├── bedrock.py                # Sonnet 4.6 invoke/invoke_stream 단일 진입점 (+ 결정적 demo mock)
│   ├── neptune.py                # openCypher wrapper (parameters 키워드 강제)
│   ├── opensearch.py             # BM25 + KNN + RRF
│   ├── guardrails.py             # 가드레일 로직 + political_balance_score 계산
│   ├── persona.py                # PERSONA_REGISTRY SSOT + system_prompt
│   ├── cohort.py                 # select(persona_id, scenario_code) → source list
│   ├── ad_matcher.py             # 광고 매칭 3-mode (keyword/embedding/agent)
│   ├── three_stage.py            # 시나리오 B 모드 분기 (Chatbot/Agent/Agentic)
│   ├── multi_agent.py            # Stage 3 자율 4 에이전트 (Planner/Graph/Analyst/Editor)
│   ├── objects_catalog.py        # 31 클래스 메타 카탈로그 SSOT (Object Explorer + /api/ontology)
│   ├── member_directory.py       # 의원 디렉토리 + 9 지표 + 뉴스
│   ├── ops_metrics.py            # 운영 콘솔 패널 데이터 집계
│   ├── outlier_detect.py         # K 표결 이상치 탐지 (builder 네이밍 아님)
│   └── *_builder.py              # 시나리오별 빌더 9종: cluster, lookalike, journey, article_roi,
│                                 #   persona_match, district_map, issue_legislation,
│                                 #   insights, signal_fusion
├── models/                       # 현재 빈 패키지 (Pydantic 모델은 각 라우터에 인라인 정의)
├── services/tools/               # 현재 빈 패키지 (예약)
└── Dockerfile                    # API + 로더 겸용
```

## Key Design Decisions

- 6 페르소나 SSOT는 `services/persona.py:PERSONA_REGISTRY` (ADR-0002).
- 모든 LLM 호출은 `services/bedrock.py:invoke()/invoke_stream()` 경유 — guardrail + neutrality 처리 자동 적용 (ADR-0004). AWS 자격증명 미설정 시 결정적 demo mock으로 fallback.
- 시나리오 B Stage 3 자율 에이전트는 `services/multi_agent.py:run_agentic_pipeline` + `AGENT_PROMPTS` (Planner→Graph→Analyst→Editor). 단계 분기는 `services/three_stage.py`.
- 시나리오별 도메인 로직은 `services/<scenario>_builder.py`에 분리 — 라우터는 얇게 유지, 테스트는 빌더 직접 호출.
- 31 클래스 메타 카탈로그 SSOT는 `services/objects_catalog.py` (`/api/objects`·`/api/ontology` 모두 여기서 서빙).
- 광고 매칭은 3-mode — `services/ad_matcher.py` (`AD_MATCH_MODE` env 또는 요청 mode로 전환).
- 데이터 cohort 필터는 `services/cohort.py:select(persona_id, scenario_code)` — 라우터가 호출.

## Conventions

- **Imports**: `from api.services import neptune` 형식. 순환 회피용 lazy import는 함수 body 안.
- **Cypher 파라미터**: 항상 `parameters={...}` 키워드. 사용자 입력 f-string interpolate 금지. `.claude/skills/cypher-conventions.md` 참조.
- **boto3**: `from api.aws_clients import session as boto_session` — factory 호출 후 `.client(...)`.
- **SSE**: `{"type": "phase|delta|log|final|result|done", "data": {...}}`. 라우터(`chat.py` 등)에서 직접 emit — 전용 helper 모듈 없음.
- **F-strings**: `{}` 안 quote 이스케이프 금지. 로컬 변수 추출.
- **페르소나 lookup**: `PERSONA_REGISTRY.get(persona_id) or PERSONA_REGISTRY["editorial"]` (fallback 필수).
- **LLM 응답**: 모든 응답에 `political_balance_score`, `data_source` 첨부.

## Adding a New Scenario

`/CLAUDE.md` "Auto-Sync Rules" 체크리스트 참조. 백엔드 측:
1. 전용 백엔드면 `api/routers/<slug>.py` + 도메인 로직 `api/services/<slug>_builder.py`. 단순 LLM narrative면 범용 `routers/insight_generic.py` 재사용.
2. `api/main.py` 라우터 등록 (lazy import 패턴).
3. `tests/test_<slug>_router.py` + `tests/test_smoke.py` import.

## Modifying the Scenario B Agent Pipeline

1. `services/multi_agent.py:AGENT_PROMPTS`에 에이전트 프롬프트 정의/수정.
2. `run_agentic_pipeline` 단계 순서(Planner→Graph→Analyst→Editor) 조정.
3. 단계 간 컨텍스트 전달은 각 `_invoke_agent` 결과를 다음 단계 message에 누적.

## Related ADRs

- ADR-0001 (gcc 아키텍처 차용)
- ADR-0002 (6 페르소나 설계)
- ADR-0003 (대고객 확장 — 인증 다층화)
- ADR-0004 (정치 중립성 가드레일)
- ADR-0005 (Phase 4 narrative 디자인 선택)
- ADR-0009 (하이브리드 mindmap / Neptune)
- ADR-0010 (real data 어댑터 매핑)
