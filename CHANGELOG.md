# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Phase 0 Bootstrap (2026-05-13)
- Fork target 결정: `ontology-for-gcc` (plan1-foundation) 아키텍처를 최대한 차용.
- 디렉토리 트리 생성 (gcc 동등): `api/`, `web/`, `infra-cdk/`, `data/`, `ontology/`, `tests/`, `docs/`, `scripts/`, `.claude/`, `.harness-eval/`, `.github/workflows/`.
- 메타 파일: `.gitignore`, `.editorconfig`, `.env.example`, `Makefile`, `requirements.txt`, `requirements-dev.txt`, `SECURITY.md`, `CHANGELOG.md`.
- 권위 설계 스펙: `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` — 6 페르소나(편집국 / 데이터·AI / 광고·세일즈 / 일반 독자 / 유료 구독자 / 기업·B2B 정책 인텔리전스), 14 시나리오 A–N, 25+ 클래스 온톨로지.
- ADR 0001–0004 작성: gcc 아키텍처 차용, 6-페르소나 설계, 대고객 서비스 확장, 정치 중립성 가드레일.
- `.claude/` 하니스: code-reviewer / security-auditor agents, wow-query-eval / cypher-conventions / persona-context skills, scrub-secrets + changelog-reminder hooks, deploy/review/test-all commands, settings.json (정치 도메인 deny list 보강).
- 모듈별 CLAUDE.md (api, web, infra-cdk, data, ontology).
- CI 4-job (`python-ast` · `tsc-check` · `cdk-synth` · `pytest`).

### Added — Phase 1 시작 (2026-05-13)
- `api/services/persona.py` SSOT 완성: 6 페르소나(editorial · data_ai · ad_sales · general_reader · paid_subscriber · b2b) + `NEUTRALITY_GUARD_SUFFIX` 상수(ADR-0004 Layer 2) + `system_prompt()`/`get()`/`ad_policy_for()`/`scenario_order()`/`all_persona_ids()` 헬퍼.
- `data/schemas.py` 31 노드 클래스 + 35 관계 SSOT: 인물·조직 6 / 입법 7 / 주제·외부 6 / 미디어 2 / 독자 5 / 광고 4 / 분석 1. `GraphNode` base + `source` 태깅 강제 + `extra="forbid"` + `HashedId` 정규식 가드.
- ADR-0004 Layer 4 가드 3중 강화: ① CI grep job, ② Pydantic `extra="forbid"`, ③ import-time `validate_no_forbidden_fields()`.
- `tests/conftest.py` — 26개 env 변수에 더미 값 collection-time 주입.
- `tests/test_persona.py` — 28 테스트 (페르소나 lookup, scenario_priority 14개 커버리지, NEUTRALITY_GUARD 자동 첨부, ad_policy 분기, customer-facing 3개 tone 차별화).
- `tests/test_schemas.py` — 39 테스트 (31 클래스 등록·HashedId 검증·AdMatchDecision audit trace·정치 중립성 필드 가드·관계 카탈로그 무결성·7개 그룹 완전성).
- `api/services/guardrails.py` (ADR-0004 Layer 1·3 통합): `political_balance_score(text)` — 정당 언급 균형(0.5) + 출처 인용(0.3) + 단정 표현 감점(0.2)의 가중 합산. `KNOWN_PARTIES` 9개 canonical 정당 (이념 라벨 0개). `check_prompt/check_output` heuristic + Bedrock Guardrails stub. `annotate_response()` — SSE final event용 메타데이터 builder. ALARM_THRESHOLD = 0.8.
- `tests/test_guardrails.py` — 22 테스트 (균형/편향 점수, 출처·단정 표현 영향, 정당 비방 차단, alarm 임계, 정당명 substring 이중카운트 방지, 페르소나별 응답 시뮬레이션).
- 버그 픽스: `_count_party_mentions` substring 이중카운트 (예: "민주당" ⊂ "더불어민주당") → placeholder 치환 패턴으로 해결.
- `tests/test_smoke.py` — services + schemas + guardrails 레이어 import 검증.
- `api/services/cohort.py`: `select(persona_id, scenario_code)` — 페르소나×시나리오 → data source list 결정 + `to_cypher_filter()` Cypher 변환 + `explain()` audit. SCENARIO_OVERRIDES 5개 (G·J·K·L·N).
- `api/services/bedrock.py`: `invoke()` 단일 LLM 진입점 - persona system prompt + Bedrock Guardrails 입력 가드 + Sonnet 4.6 호출 + political_balance_score 자동 첨부. DEMO_PUBLIC_MODE mock 응답 (페르소나별 어조 echo). `InvokeResult.to_sse_final()` SSE final event 변환.
- `tests/test_cohort.py` — 6 페르소나 × 14 시나리오 = 84 case parametrize + Cypher filter + audit trace.
- `tests/test_bedrock.py` — invoke 단일 진입점, persona·scenario 전파, 입력 가드 차단, mock 응답 균형성, SSE 직렬화.
- `api/services/neptune.py`: `open_cypher(query, *, parameters=None)` — **parameters 키워드 전용** 강제(Cypher injection syntactic 가드). SigV4 signed POST + Demo mode 쿼리 패턴 매칭 mock. `CypherResult` iterable/len/index 지원.
- `api/services/opensearch.py`: `hybrid_search(query, top_k, source_filter)` — BM25(Nori) + Cohere embed-v4 KNN + RRF + cohort source filter. Demo mode mock은 균형 잡힌 hit (정당 비방 없음, 다양한 node_type).
- `tests/test_neptune.py` — 19 테스트 (parameters keyword-only 강제, mock 쿼리 분기, source 태깅).
- `tests/test_opensearch.py` — 13 테스트 (top_k 제한, source_filter cohort 연동, 정당 비방 가드).
- `api/services/multi_agent.py` (Stage 3): 4 에이전트(Planner/Graph/Analyst/Editor) 순차 협업 + AgenticResult. AGENT_PROMPTS SSOT + run_agentic_pipeline.
- `api/services/three_stage.py` (시나리오 B 핵심): stage1_chatbot(RAG) / stage2_agent(Tool Use 4개) / stage3_agentic(Multi-Agent) / run_all_stages 비교 시연. StageResult dataclass + duration_ms + extras(approach/limitation/agent 중간 출력).
- `api/routers/chat.py`: POST /api/chat (compare/chatbot/agent/agentic 4 모드) + GET /api/chat/modes. X-Persona-Id 헤더 처리. Pydantic 유효성 검증.
- `api/main.py`: FastAPI app factory + 라우터 등록점 + /healthz, /api/healthz.
- `tests/test_three_stage.py` — 18 테스트 (3 stage 검증, 복잡도 점진성, 6 페르소나 처리, 직렬화).
- `tests/test_multi_agent.py` — 10 테스트 (4 에이전트 순서, 중간 출력, 도구 호출).
- `tests/test_chat_router.py` — 17 테스트 (TestClient, compare 모드, X-Persona-Id 6개, 유효성 검증).
- pytest **393 케이스 전 통과** (0.49초). 시나리오 B vertical slice 동작 확인 (mock 응답 구조 가시화).

### Changed — 디자인 원칙: stage 일관 / 페르소나 차별 (2026-05-13)
- `bedrock._mock_response` 재설계: stage 일관 + 페르소나 차별. 같은 질문에 3 stage final 텍스트는 동일하되 6 페르소나가 서로 다른 청중 언어로 응답(편집국 후속 취재 / 데이터·AI 통계 / 광고 AdMatchDecision / 일반 독자 친절 가이드 / 유료 구독자 심층+PDF / B2B JSON).
- Multi-agent 내부 에이전트(Planner/Graph/Analyst) 출력은 페르소나 무관 균일 (internal process detail). Editor 최종 출력은 페르소나 적용.
- `_detect_persona_id` 헬퍼 추가: persona.system_prompt 합성 결과("사용자는 <name> ...")에서 페르소나 ID 추출.
- 신규 테스트 18개: 6 페르소나 텍스트 distinctness, 페르소나별 식별 마커, stage 일관성, multi-agent 내부 중립성, 양당 균형, 출처 인용, B2B JSON 형식, 일반 독자 친절 어조.
- pytest **411 케이스 전 통과** (0.49초).
- 원칙 근거 (사용자): "같은 질문에 일관된 답변이 맞고, 독자·부서별로 답변이 달라지는게 좋습니다" + "PoC 수준 + 계속 사용한 에셋 (GS Caltex처럼)".

### Notes
- `raw_data/`는 `.gitignore`. 국회 OpenAPI raw payload와 합성 독자/광고 시드는 KMS S3 별도 보관.
- 첫 배포 도메인: `*.cloudfront.net` (커스텀 도메인은 Phase 5 polish에서 추가).
- 정치 중립성 가드레일은 Bedrock Guardrails로 시나리오 B·C·I 모두에 적용.
