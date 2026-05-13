# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Phase 4 Track 4-1: 시나리오 K 표결 이상치 (PDF ★, 2026-05-13)
- `api/services/outlier_detect.py`: 3 유형 탐지 - party_line_break (당론 이탈), swing_vote (박빙), cross_party (정파 초월 협력). 5 합성 시드 (deviation_score 0.68~0.82).
- `api/routers/outlier.py`: GET /api/outlier (필터·페이징) + GET /api/outlier/{id} (디테일). 페르소나별 안내 메시지·후속 행동 제안.
- ADR-0004 정치 중립성: ai_label에 정당 비방 어휘 미포함 (test로 강제). "당론 이탈"은 사실 기술, 평가 X.
- `web/lib/scenario-clients.ts`: Phase 4 시나리오 API 클라이언트 모음 (outlierApi 신규).
- `web/app/outlier/page.tsx`: 3 유형 필터 + 리스트·디테일 2-column + AI 패턴 라벨 amber 카드.
- `web/components/Sidebar.tsx`: K 시나리오 활성화 + "PDF ★" 배지.
- `tests/test_outlier_router.py`: 24 테스트 (3 유형, 정치 균형, 6 페르소나 안내, 유효성).
- 누적 pytest **745 통과**.

### Added — Phase 5 Track 5-7: CytoscapeView 4 고급 패턴 (2026-05-13)
- `web/components/CytoscapeView.tsx` 재작성: 4 패턴 모두 적용.
  ① **이미지 노드** — Person 노드에 placeholder 아바타 (data URI SVG, 모든 의원 동일 - ADR-0004 정치 중립). `background-image` + `background-clip: node`로 원형 클리핑. label은 노드 하단.
  ② **`[relation="..."]` 셀렉터** — 16개 관계 타입별 색·width·line-style 차별화. PROPOSED 파랑 굵게 solid, MEMBER_OF 녹색 dashed, ABOUT 청록 dotted, BELONGS_TO 자주 가늘게, VOTED 주황 굵게, CANDIDATE 노랑 dashed 등.
  ③ **fcose 레이아웃 + compound** — `cytoscape-fcose` extension 자동 register. MEMBER_OF 엣지 자동 감지 → Committee를 compound parent로, Person을 자식으로 묶음. 정당(BELONGS_TO)은 일반 노드로 유지 (ADR-0004 정파 시각화 회피).
  ④ **1-hop 이웃 강조** — `cy.on('tap', 'node')` → `closedNeighborhood()` 외 elements에 `faded` class (opacity 0.2). 배경 tap reset.
- `api/routers/search.py`: edge type "ON" → "VOTE_ON" canonical 정규화.
- `api/routers/objects.py`: `_try_build_subgraph` 관계 이름 정규화 매핑 - field name uppercased → canonical relation (PROPOSED, BELONGS_TO, MEMBER_OF, ABOUT 등 schemas.py RELATION_TYPES와 정합).
- `web/app/objects/[type]/page.tsx`: detail panel의 subgraph JSON viewer → CytoscapeView 임베드 (height 300).
- `web/types/cytoscape-fcose.d.ts`: 외부 라이브러리 ambient declaration.
- npm 의존성 추가: cytoscape-fcose 2.2.
- 라이브 검증: search subgraph(B2206001) → PROPOSED 3건 + VOTE_ON 1건, objects(MONA_001) → BELONGS_TO 1건. 모든 관계가 셀렉터에 매핑됨.
- 빌드: tsc 0 error, next build 9 routes (search 6.36 kB, objects/[type] 99.1 kB First Load).

### Added — Phase 5 Track 5-6: Object Explorer 31 클래스 (2026-05-13)
- `api/services/objects_catalog.py`: 31 클래스 dispatcher 패턴. CLASS_GROUPS 7 그룹 + CLASS_DISPLAY_FIELDS (id·label·subtitle 매핑). 15 구현 (Person·Party·Bill·Vote·Committee·Session·Statement·Agency·Topic·Article·Reader·Advertisement·AdInventory·SocialSignal·PollResult) + 16 placeholder.
- `api/routers/objects.py`: 4 엔드포인트 - GET /api/ontology/classes (전체 메타), /api/ontology/{cls} (단일), /api/objects/{cls} (페이징 리스트), /api/objects/{cls}/{id} (디테일 + 1-hop subgraph).
- 1-hop subgraph 자동 추론: 참조 필드(proposer_id, bill_id, topic_ids, candidate_ad_ids 등) → 자동 관계 그래프 구성.
- `web/app/objects/page.tsx`: 31 클래스 그룹 카드 그리드 (구현 15 + 미구현 16).
- `web/app/objects/[type]/page.tsx`: 클래스별 인스턴스 페이징 + 인라인 디테일 패널. 디테일에 필드 dl + 1-hop subgraph JSON.
- `web/components/Sidebar.tsx`: Object Explorer 링크 추가 (31 클래스 배지).
- `tests/test_objects_router.py`: **31 테스트** - 클래스 메타, 페이징, 단일 객체, subgraph, 15 구현 클래스 parametrize, 422 유효성.
- 누적 pytest **721 통과**. 9 web routes (정적 8 + 동적 /objects/[type] 1).

### Added — Phase 5 Track 5-5: SSE streaming (시나리오 B 실시간 응답, 2026-05-13)
- `api/routers/chat.py`: `POST /api/chat/stream` 신규. `sse_starlette.EventSourceResponse` 사용. 3 stage 비교 모드만 지원.
- SSE 이벤트 어휘 정착: `phase` (stage 시작) / `log` (도구·에이전트 호출) / `result` (stage 완료) / `done` (전체 완료, total_ms).
- 15 이벤트 sequence: phase(chatbot) → result(chatbot) → phase(agent) → 4 tool logs → result(agent) → phase(agentic) → 4 agent logs → result(agentic) → done.
- 시연 효과를 위해 stage·tool 사이에 `asyncio.sleep(0.05~0.08)` 삽입 - 한 단계씩 나타나는 진행감.
- `web/lib/api-client.ts`: `chatStream()` 함수 - fetch + ReadableStream 수동 SSE 파싱. CRLF/LF 양쪽 구분자 지원.
- `web/app/chat/page.tsx`: SSE 소비 + 실시간 UI - 각 stage 카드에 status(대기/진행 중/완료) badge + log 라이브 표시 + 진행 중 카드 animate-pulse.
- `tests/test_chat_stream.py`: **10 테스트** - 15 이벤트 sequence, phase·log·result·done 순서, 도구·에이전트 trace, 페르소나 전파, 422 유효성.
- `requirements.txt` 기존 `sse-starlette==2.2.1` 활용.
- 누적 pytest **690 통과**.

### Added — Phase 5 Track 5-4: harness-eval baseline + wow-eval 84 케이스 (2026-05-13)
- `scripts/eval_wow_queries.py`: 6 페르소나 × 14 시나리오 = 84 케이스 평가. 현재 구현된 A·B·L 시나리오 = 18 active, 나머지 66 자동 SKIPPED. PASS_RATE_THRESHOLD=0.85, BALANCE_THRESHOLD=0.8. exit code 0/1 (CI gate).
- in-process TestClient 지원 (`--base-url inproc`) - AWS 미배포 환경에서도 평가 가능.
- `.harness-eval/latest.json`: 결과 자동 저장. 운영 콘솔 `wow-quality` 패널이 자동 읽기.
- README 배지: ![wow-eval Pass Rate 100%], ![Avg Balance 0.95], ![Active 18/84], ![Last Eval].
- 첫 baseline 결과: **18/18 active PASS (100%), avg balance 0.950**.
- `tests/test_eval_wow_queries.py`: 9 테스트 (case 카탈로그·skip 로직·summarize·json output·in-process 전체 실행).

### Added — Phase 5 Track 5-3: GuidedTour 6 페르소나 추천 흐름 (2026-05-13)
- `web/components/GuidedTour.tsx`: 우측 하단 플로팅 가이드 버튼 + 모달. 6 페르소나별 권장 3-step 시나리오 흐름. 각 step에 "why this for you" 한 줄 설명.
- TOURS 매핑: editorial(C→B→K) / data_ai(E→J→B) / ad_sales(L→G→F) / general_reader(A→B→H) / paid_subscriber(C→K→M) / b2b(A→J→K).
- `web/app/layout.tsx`: GuidedTour 모든 페이지에서 사용 가능.
- 미구현 시나리오는 disabled 표시 (후속 phase 추적).

### Added — Phase 5 Track 5-2: 운영 콘솔 5 패널 (2026-05-13)
- `api/services/ops_metrics.py`: thread-safe LLM trace 링버퍼(deque maxlen=100) + GuardrailCounters 누적.
- `api/services/bedrock.py`: `invoke()` 매 호출 후 자동 `_record()` - persona·scenario·score·duration_ms 기록.
- `api/routers/ops.py`: 5 패널 엔드포인트 - `/api/ops/{ingest,guardrail,memory,wow-quality,trace}`.
- `web/lib/ops-client.ts` + `web/app/ops/page.tsx`: 5 패널 grid UI - Stat 카드 + trace 테이블 + 새로고침. 임계 미달 warn 색상.
- `tests/test_ops_metrics.py`: 18 테스트.

### Added — Phase 5 Track 5-1: CytoscapeView 1-hop subgraph 시각화 (2026-05-13)
- `web/components/CytoscapeView.tsx`: cytoscape 3.31 + cose force-directed 레이아웃. SSR 안전 dynamic import. 노드 타입별 색상 (Bill 파랑/Person 자주/Vote 주황/Article 녹색/Topic 청록/Statement 분홍/Committee 녹색/Party 자주/Agency 노랑). 루트 노드는 크기·border 강조.
- `web/app/search/page.tsx`: JSON viewer 대체 → 실시간 그래프 + 노드 라벨·엣지 타입 표시. JSON은 디버깅용 details에 보존.
- 시각 디자인 ADR-0004 준수: 정당 색·이념 색 미사용. 노드 타입(Bill·Person 등) 기반만.
- npm 의존성 추가: cytoscape 3.31.0, react-cytoscapejs 2.0.0, @types/cytoscape 3.21.7 (lazy load - 초기 bundle 영향 최소).
- `/search` First Load JS: 91 → 92 kB (+1 kB, Cytoscape는 동적 import).

### Added — Phase 3 Track 5: Next.js 14 web 앱 골격 (2026-05-13)
- `web/package.json` + `tsconfig.json` + `next.config.js` + `tailwind.config.ts`: Next.js 14.2 + Tailwind CSS + TypeScript strict 모드. ECS Fargate ARM64 deploy 호환(`output: 'standalone'`).
- `web/app/layout.tsx`: RootLayout - Sidebar + 메인 콘텐츠 2-column.
- `web/app/page.tsx`: 홈 - 14 시나리오 카드 그리드. 구현 시나리오(A·B·L) 클릭 가능, 나머지 비활성.
- `web/app/search/page.tsx`: 시나리오 A - POST /api/search 호출 + hits + 1-hop subgraph (JSON 자세히 보기).
- `web/app/chat/page.tsx`: 시나리오 B - 3-stage 사이드바이사이드 비교. tools_called·agents_invoked·political_balance_score 표시. 3개 샘플 쿼리 버튼.
- `web/app/ad-match/page.tsx`: 시나리오 L - 3-way 광고 매칭 비교. 안전/비위 2 샘플 콘텐츠. **거절 결정은 빨강 카드 + ★ 광고 노출 생략** 강조. governance_summary banner.
- `web/components/PersonaSwitch.tsx`: 6 페르소나 토글 (localStorage). 변경 시 페이지 reload로 일관성 보장.
- `web/components/Sidebar.tsx`: 페르소나 + 14 시나리오 nav + 데이터 출처 범례. 구현 안 된 시나리오는 비활성.
- `web/components/DataSourceBadge.tsx`: real(녹색)·synthetic(노란색)·external(파란색) 색상 구분 배지. ADR-0004 - 정당 색 미사용.
- `web/lib/personas.ts`: 6 페르소나 SSOT (백엔드와 정합. 향후 GET /api/personas로 fetch 대체 예정).
- `web/lib/api-client.ts`: search·chat·adMatch 타입드 클라이언트. X-Persona-Id 자동 첨부. NEXT_PUBLIC_API_BASE_URL / INTERNAL_API_BASE_URL 분리.
- `web/.env.example`: API base URL 설정 예시.
- `npx tsc --noEmit` 통과 + `next build` 7 라우트 정적 prerendering 성공 (총 91 kB First Load JS).
- 109 npm 패키지 (Next.js 14.2.30 + React 18.3 + Tailwind 3.4 + TypeScript 5.7).

### Added — Phase 3 Track 4: 국회 OpenAPI 나머지 4 어댑터 (2026-05-13)
- `data/real/committee.py`: `npffdutiapkzbfyvr` 위원회 어댑터. 8 mock 위원회 (상임위·특별위 분류).
- `data/real/session.py`: `nktulghyaivebdpnz` 회의록 - **Session + Statement 두 노드 동시 yield**. 5 mock 회의 × 발언 2-3건씩.
- `data/real/party.py`: 정당 어댑터 (guardrails KNOWN_PARTIES와 정합, 6 정당).
- `data/real/agency.py`: 국정감사 대상 기관 어댑터. 12 mock (정부부처/공기업/헌법기관 3 분류).
- `data/load.py`: `emit_real_local` 확장 - **8 NDJSON 출력** (기존 3 + 신규 4 + statements 분리). max-* 옵션 8개 (`--max-committees/sessions/parties/agencies` 추가).
- `scripts/verify_demo_dataset.py`: EXPECTED_FILES 업데이트 (real 8개 + 클래스 lookup 5개 추가).
- `tests/test_real_adapters_extra.py` — **25 테스트** - 4 어댑터 Pydantic 검증, type 정규화, cross-reference (Session→Committee), 결정성.
- `--source all --demo` 라이브: **15 NDJSON 파일** (synthetic 5 + real 8 + external 2) + 6/6 verification 통과.
- 누적 pytest **653 통과** (Phase 3 +153).

### Added — Phase 3 Track 3: 시나리오 L 광고 매칭 (AI 거버넌스 데모 메인, 2026-05-13)
- `api/services/ad_matcher.py`: 3 모드 광고 매칭 - keyword (토픽-카테고리 단순 매칭), embedding (코사인 유사도, mock=hash 기반), **agent (★ Bedrock 판단 - 민감 콘텐츠 감지)**.
- ADR-0004 Layer 6 trigger: Agent 모드만 SENSITIVE_PATTERNS (scandal·tragedy·minor_victim·controversy)를 감지하여 `chosen_ad_id=None` (광고 노출 생략) + reason_text에 "ADR-0004 Layer 6 trigger" 명시.
- `api/routers/ad_match.py`: POST /api/ad-match + GET /api/ad-match/modes. compare 모드에서 3 모드 동시 실행 + `governance_summary`로 차이 강조 ("Agent 모드만 광고를 거절").
- `api/main.py`: ad_match 라우터 등록.
- `tests/test_ad_match.py`: **39 테스트** - 안전/비위 콘텐츠 분리, Agent 거절 패턴, governance_summary, AdMatchDecision Pydantic 검증, SENSITIVE_PATTERNS 4 카테고리.
- 라이브 데모:
  - 안전(AI 산업 진흥) → 3 모드 모두 광고 매칭 (key 0.50 / emb 0.78 / agent 0.75)
  - 비위(검찰 수사) → keyword 0.30 매칭, embedding 0.83 매칭, **Agent 거절** (audit trace: "skip — 민감 콘텐츠 감지 (controversy, scandal). ADR-0004 Layer 6 trigger")
- 누적 pytest **627 통과** (Phase 3 +90).

### Added — Phase 3 Track 2: 시나리오 A 검색 라우터 (2026-05-13)
- `api/routers/search.py`: POST /api/search + GET /api/search/info. 페르소나 cohort 필터 + `opensearch.hybrid_search` + Neptune 1-hop subgraph (top hit). Cytoscape 호환 `SubgraphModel` (nodes/edges).
- 페르소나별 top_k 조정: 일반 독자 ≤5 (입문성), 데이터·AI ≥15 (분석 후보), 그 외 요청값.
- 페르소나별 extras: guide_hint(일반 독자) / premium_cta(유료) / api_response_hint(B2B) / analytics_hint(데이터·AI) / coverage(광고/세일즈).
- `api/main.py`: search 라우터 등록.
- `api/services/neptune.py`: mock 개선 - RETURN 변수(`return p`, `return b` 등) 인식. 1-hop subgraph 쿼리에서 정확한 노드 타입 반환. 5 helper로 분리 (bills/persons/votes/articles).
- `tests/test_search_router.py`: 37 테스트 (6 페르소나 처리, top_k 조정, cohort 전파, subgraph 모양, extras 페르소나별 분기, info endpoint).
- 라이브 데모: subgraph root=Bill + 3 Persons(PROPOSED) + 1 Vote(ON) = 5 nodes/4 edges.

### Added — Phase 3 Track 1: infra-cdk 6 스택 (2026-05-13)
- `infra-cdk/bin/assembly.ts`: 6 스택 인스턴스화 (network → data → ai → compute → edge → observability). 신규 VPC (ADR-0001 D7 - gcc retail VPC import 패턴과 분리).
- `infra-cdk/lib/network-stack.ts`: VPC 10.30.0.0/16, 3-AZ, NAT 1개, 5 SG (alb·app·neptune·os·lambda). cloudfront prefix list ingress 강제.
- `infra-cdk/lib/data-stack.ts`: Neptune cluster (t3.medium, isolated subnet), OpenSearch Serverless VECTORSEARCH 컬렉션, S3 3개 (raw/uploads/synthetic), DynamoDB 4개 (b2b-keys, ad-inventory, ad-impression with TTL, reader-profile).
- `infra-cdk/lib/ai-stack.ts`: Bedrock Guardrail '정치 중립성' (PartyAttack/PoliticianInsult DENY 토픽 + HATE/INSULTS/MISCONDUCT 필터).
- `infra-cdk/lib/compute-stack.ts`: ECS Fargate ARM64 (api+web 각 2 replica) + ALB + Ad Matcher Lambda 분리 (ADR-0004 Layer 6, ARM64).
- `infra-cdk/lib/edge-stack.ts`: Cognito 3개 pool (staff/subscriber/guest) + 페르소나 그룹 6개 + API Gateway B2B + Usage Plan + CloudFront. us-east-1 deploy.
- `infra-cdk/lib/observability-stack.ts`: CloudWatch Dashboard + 알람 2개 (political_balance_score < 0.8 + ALB 5xx > 1%).
- `infra-cdk/test/stacks.test.ts`: **24 Jest 테스트** + **6 스냅샷**. ARM64 강제·Guardrail 존재·Cognito 6 그룹·TTL·정치 균형 임계 검증.
- `cdk synth` 6 스택 통과 (76 feature flags - production hardening은 후속).
- npm 의존성 300 패키지 (aws-cdk-lib 2.170 + ts-jest 29.2 + jest 29.7 + typescript 5.7).

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

### Added — Phase 2 시작: 합성 generator + load CLI (2026-05-13)
- `data/synthetic/topics.py`: 25개 중립 정책 토픽 카탈로그 (산업·법무·사회·경제·환경·문화·외교안보). 이념 라벨 0개. `to_graph_nodes()` Pydantic Topic 변환.
- `data/synthetic/article.py`: 2,000 합성 기사 generator. 정치 균형(양당 빈도 CV<0.3) + 출처 인용 + 단정 표현 금지. AUTHOR_POOL 10명, PERSON_ID_POOL 100명, BILL_ID_POOL 100건, 9개 제목 템플릿. seed 결정성.
- `data/synthetic/reader.py`: 50,000 합성 독자 generator. SHA-256 솔티드 해시 ID(64자 lowercase hex), tier 분포 anonymous 80/free 15/paid 5, 17 시도 region(sgg 이상 정밀도 금지), 관심사 0-5개. ADR-0003 익명화 + ADR-0004 Layer 4 PII 가드.
- `data/synthetic/advertisement.py`: 500 합성 광고 + AdInventory 1:1 generator. 14 ADVERTISER_PROFILES (테크/금융/교육/친환경/자동차/통신/헬스케어/마케팅), 광고주별 avoid_topics 정책, 월 예산 50만~5천만 원 × 1~12개월, target_personas는 general_reader/paid_subscriber만.
- `data/load.py`: CLI 통합. `--source synthetic --to local --out-dir ...` 동작. 5개 NDJSON 파일(topics·articles·readers·advertisements·ad_inventories) 출력. `write_ndjson()` Pydantic 모델→NDJSON 헬퍼. Phase 3 stub (`--source real|external`, `--to s3`)는 exit code 2로 안내.
- `tests/test_synthetic_topics.py` — 9 테스트 (25개 등록·이념 라벨 가드·Pydantic 변환).
- `tests/test_synthetic_article.py` — 17 테스트 (결정성·정치 균형·political_balance_score ≥0.8·출처 인용).
- `tests/test_synthetic_reader.py` — 18 테스트 (HashedId 정규식·tier 분포 ±2%·PII 가드·salt 격리·관심사 tier 상관관계).
- `tests/test_synthetic_advertisement.py` — 21 테스트 (advertiser/inventory 1:1·avoid_topics 정합·target_personas 정책·budget 범위).
- `tests/test_load.py` — 16 테스트 (NDJSON round-trip·5개 파일·Phase 3 stub·subprocess CLI 실행).
- pytest **495 케이스 전 통과** (1.03초).
- 라이브 CLI 검증: 100 articles + 5000 readers + 30 ads = 1.1MB NDJSON. 균형 잡힌 정당 언급(민주 6건/국힘 6건), 익명 해시 ID, 17 시도 region 확인.

### Added — Phase 2 Track 2-2: 국회 OpenAPI 어댑터 (2026-05-13)
- `data/real/_client.py`: 공유 HTTP 클라이언트. SigV4 X (단순 KEY 인증), 페이징, JSON 응답 표준화 (`ApiResponse`). `AssemblyClient.iter_all_pages` row 단위 yield. `DEMO_PUBLIC_MODE=true` 분기.
- `data/real/bill.py`: `nzmimeepazxkubdpn` (의안처리상황) → Pydantic Bill. `STATUS_MAP` 처리결과 정규화, `_parse_date` 다양한 형식 지원. mock 의안 10건 (양당 균형).
- `data/real/member.py`: `nwvrqwxyaytdsfvhu` (국회의원 현황) → Pydantic Person. 지역구·비례대표 분류, party 4종 균형. mock 의원 10명.
- `data/real/vote.py`: `nojepdqqaweusdfbi` (본회의 표결) → Pydantic Vote. vote_id = V_<BILL_ID>_<DATE> 결정적 생성. mock 10건 (passed 7, rejected 2, withdrawn 1).
- 엔드포인트 코드는 env 변수(`ASSEMBLY_API_*_ENDPOINT`)로 외부화 - 환경별 격리.
- `data/load.py` CLI: `--source real|all` + `--demo` 플래그 + `--max-bills/--max-members/--max-votes` 추가.
- `tests/test_real_adapters.py` — 30 테스트 (API 응답 파싱·status 정규화·cross-adapter 참조 정합·정당 균형).

### Added — Phase 2 Track 2-3: 외부 시그널 ETL (2026-05-13)
- `data/external/naver_news.py`: 네이버 뉴스 검색 API → SocialSignal. HTML strip, pubDate 파싱, 결정적 signal_id (URL MD5 해시). Demo mock 10개 뉴스(균형 잡힌 정당 언급).
- `data/external/poll_result.py`: 합성 여론조사 generator → PollResult. 정당 지지율 6 정당(합 100%, 한 정당 ≤60%) + 토픽 의견(찬성/반대/잘 모름). 가공 기관명("Synth-Poll-A" 등 - 실 기관명 미사용).
- `data/load.py` CLI: `--source external` + `--news-query/--news-count/--poll-count` 추가.
- `tests/test_external_adapters.py` — 23 테스트 (뉴스 결정성·정당 합 100%·토픽 의견 균형·정치 중립성).

### Added — Phase 2 Track 2-5: PDF 시그니처 시드 + 통합 검증 (2026-05-13)
- `data/synthetic/seeds.py`: PDF 3페이지 시그니처 시연 시드. 7 entity (Person/Bill/Article/Vote/Statement/AdMatchDecision/Cluster). 데모 자산 ID 상수 (`DEMO_HUB_PERSON_ID`, `DEMO_AI_BILL_ID`, `DEMO_TRAGIC_ARTICLE_ID`, `DEMO_SWING_VOTE_ID`).
- 시나리오 B (3-stage chat) 허브 의원 + AI 의안 + 공동발의 패턴 시드.
- 시나리오 K (표결 이상치) 당론 이탈 시드.
- 시나리오 L (광고 매칭 거부) - `AdMatchDecision`의 `chosen_ad_id=None` + ADR-0004 Layer 6 reason 명시.
- 시나리오 M (의원 정치 여정) - 허브 의원 Statement + 정합 person_id 연결.
- 시나리오 E (클러스터) - 중립 추상 라벨 "혁신 입법 다수파".
- `scripts/verify_demo_dataset.py`: 통합 검증 스크립트. 6 검사 (파일 존재·Pydantic round-trip·source 태깅·정치 균형·cross-reference·seeds). standalone 실행 + pytest 양용. exit code 0/1/2.
- `tests/test_synthetic_seeds.py` — 13 테스트 (시드 ID·이념 라벨 가드·cross-reference·skip 결정 형식).
- `tests/test_verify_demo_dataset.py` — 7 테스트 (검증 스크립트 self-test, 모든 check 통과).

### Phase 2 누적 성과
- pytest **574 케이스 전 통과** (1.09초, 411 → 495 → 574).
- 10 NDJSON 파일 생성 (synthetic 5 + real 3 + external 2). `--source all --demo` 한 번에 718+ 노드.
- 라이브 검증 스크립트 6/6 통과.
- Phase 3 인프라(Neptune·OpenSearch·S3) 정착 후 즉시 `aws s3 sync` + Bulk Loader 적재 가능.

### Notes
- `raw_data/`는 `.gitignore`. 국회 OpenAPI raw payload와 합성 독자/광고 시드는 KMS S3 별도 보관.
- 첫 배포 도메인: `*.cloudfront.net` (커스텀 도메인은 Phase 5 polish에서 추가).
- 정치 중립성 가드레일은 Bedrock Guardrails로 시나리오 B·C·I 모두에 적용.
