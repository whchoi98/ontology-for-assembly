# CLAUDE.md

Project memory for Claude Code. This file is auto-loaded into every session and should describe what this codebase is, how it is organized, and what conventions matter when changing it. Keep it under ~300 lines and update it when architectural decisions change.

## Project

`ontology-for-assembly` is a 30–60 minute proof-of-concept demo for a **한국 언론사 대상 Agentic AI + 지식그래프** scenario powered by 국회 열린데이터광장(open.assembly.go.kr) 공공 OpenAPI. AWS Bedrock + AgentCore + Neptune + OpenSearch Serverless 위에서 14개 wow 시나리오(A–N)와 6개 페르소나(편집국 · 데이터·AI · 광고·세일즈 · 일반 독자 · 유료 구독자 · 기업/B2B 정책 인텔리전스)를 통해 *3-단계 진화 비교(Chatbot → Agent → Agentic AI)*와 *AI 거버넌스 광고 매칭*을 시연한다.

Multi-runtime monorepo: Python FastAPI backend, Next.js 14 frontend, AWS CDK infrastructure(6 stacks), synthetic-data loader가 일회성 ECS 태스크 겸용.

> 권위 스펙: `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` (14 시나리오 / 25+ 클래스 / 6 페르소나).
> 차용 원본: https://github.com/whchoi98/ontology-for-gcc (plan1-foundation 브랜치) — 디렉토리·스택·하니스·시나리오 골격 100% 차용, 도메인만 교체.

## 핵심 시연 메시지

1. **3단계 진화 비교** — 같은 질문에 Chatbot(RAG) · Agent(Tool Use) · Agentic AI(자율 다중 에이전트)가 어떻게 다른 답변을 내는지를 시나리오 B에서 한 화면 비교.
2. **AI 거버넌스 광고 매칭** — 시나리오 L에서 키워드 매칭 · 임베딩 · Agent 판단 3-way를 비교. 정치 민감 콘텐츠에서 Agent가 "광고 노출 생략"을 판단하는 trace를 라이브로 보여줌.
3. **B2C·B2B 동시 시연** — 편집국(내부) + 일반/유료 독자(B2C) + 기업/정책 인텔리전스(B2B) 6 페르소나가 같은 데이터를 자신의 KPI로 본다.

## 6 페르소나

| # | 이름 | 인증 | 주력 시나리오 |
|---|---|---|---|
| 1 | 편집국 (Editorial) | Cognito staff 그룹 | C·B·K·M (취재·기사) |
| 2 | 데이터·AI (Data·AI Desk) | Cognito staff 그룹 | E·J·K·N (분석) |
| 3 | 광고·세일즈 (Ad·Sales) | Cognito staff 그룹 | L·G·F (수익화) |
| 4 | **일반 독자** (General Reader, B2C 무료) | Cognito Guest + 게스트 쿠키 | A·B·H·M (탐색) |
| 5 | **유료 구독자** (Paid Subscriber, B2C 유료) | Cognito subscriber 그룹 | C·K·M·D (심층) |
| 6 | **기업/B2B 정책 인텔리전스** | API Key (DynamoDB + Secrets Manager) | A·C·J·K (정책 모니터링) |

페르소나 전환 효과: 사이드바 정렬, 홈 카드 하이라이트, 챗 system prompt 어조, Object Explorer 펼침 클래스, 광고 노출 정책. 자세한 가중치는 ADR-0002 + `api/services/persona.py:PERSONA_REGISTRY` 참조.

## 14 시나리오 (A–N)

| code | 이름 | 핵심 기술 |
|---|---|---|
| A | 의안·의원 의미 검색 | BM25(Nori) + Cohere KNN + RRF + rerank-v3, 1-hop 그래프 |
| B | 기자/독자 챗봇 | Bedrock Converse + AgentCore Memory + 10 도구 (3단계 비교) |
| C | 기사 인사이트 | Sonnet 4.6 스트리밍 + Code Interpreter 차트 |
| D | 데스크/관심사 페르소나 매칭 | 6 페르소나 KPI 가중치 그래프 워크 |
| E | 의원 정치성향 클러스터링 | KMeans + LLM 라벨링 (정당 비방 없이 추상 라벨) |
| F | 유사 의원/의안 룩어라이크 | Cohere embed-v4 + OpenSearch KNN |
| G | 기사 ROI/CTR 시뮬레이션 | Bayesian + Code Interpreter 분포 차트 |
| H | 지역구 choropleth 지도 | 17 시도 GeoJSON + 의원 분포 |
| I | 편향·정치중립 가드레일 | Bedrock Guardrails + bias score 노출 |
| J | 외부 신호 융합 | 네이버 뉴스 + SNS + 여론조사 cross-source |
| K | 표결·발언 패턴 변화 탐지 | pandas 윈도 + LLM 패턴 라벨 (PDF 3-page 시그니처) |
| L | **광고 매칭 매트릭스** | 키워드·임베딩·Agent 3-way + Ad Matcher Lambda |
| M | 의원 정치 여정 timeline | 발의·표결·발언·위원회 통합 (PDF 3-page 시그니처) |
| N | 사회 이슈 × 입법 상관 | 토픽 트렌드 ↔ 법안 발의 산점도 |

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend runtime | Python 3.12 on Fargate ARM64 |
| Backend framework | FastAPI + Pydantic v2 + uvicorn |
| Frontend runtime | Node.js 20 on Fargate ARM64 |
| Frontend framework | Next.js 14 App Router (standalone) + React 18 + Tailwind |
| Graph DB | Amazon Neptune (openCypher) |
| Search | OpenSearch Serverless (Nori BM25 + Cohere KNN, RRF fusion) |
| Foundation models | Bedrock Sonnet 4.6 (chat/insights), Cohere embed-v4 (벡터), Cohere rerank-v3 |
| Memory | AgentCore Memory (short-term session + long-term reader/staff namespaces) |
| Sandbox | AgentCore Code Interpreter Firecracker microVM (matplotlib + NanumGothic) |
| Maps | react-simple-maps + d3-geo + KOSTAT 17 시도 GeoJSON |
| Auth | Cognito user pool (staff/subscriber) + Cognito Guest Identity Pool (일반 독자) + Lambda@Edge JWT |
| B2B API | API Gateway Usage Plan + API Key (DynamoDB) |
| Edge | CloudFront → ALB (HTTP origin, cloudfront prefix-list SG) |
| Compute | ECS Fargate ARM64, two-replica services (api + web) |
| Ad Matcher | Lambda (별도) + Bedrock + DynamoDB AdInventory |
| IaC | AWS CDK v2 (TypeScript) — 6 stacks: network, data, compute, ai, edge, observability |

## Project Structure

```
ontology-for-assembly/
├── api/                          Python 3.12 FastAPI backend
│   ├── routers/                  시나리오별 엔드포인트 (1파일 = 1시나리오)
│   │   ├── search.py             # A 의미 검색
│   │   ├── chat.py               # B 챗봇 (3단계 비교 SSE)
│   │   ├── insights.py           # C 기사 인사이트
│   │   ├── persona_match.py      # D 페르소나 매칭
│   │   ├── cluster.py            # E 의원 클러스터링
│   │   ├── lookalike.py          # F 룩어라이크
│   │   ├── article_roi.py        # G 기사 ROI
│   │   ├── district_map.py       # H 지역구 지도
│   │   ├── neutrality.py         # I 편향·중립성 가드레일
│   │   ├── external_signal.py    # J 외부 신호
│   │   ├── outlier.py            # K 표결 이상치
│   │   ├── ad_match.py           # L 광고 매칭 (3-way)
│   │   ├── journey.py            # M 의원 여정
│   │   ├── issue_legislation.py  # N 이슈 × 입법 상관
│   │   ├── objects.py            # 25 클래스 객체 탐색
│   │   ├── ontology.py           # 온톨로지 메타
│   │   ├── personas.py           # GET /api/personas (PERSONA_REGISTRY SSOT)
│   │   └── ops.py                # /healthz, 운영 콘솔
│   ├── services/                 # bedrock, neptune, opensearch, agentcore, agent,
│   │                             # guardrails, persona, cohort, ad_matcher,
│   │                             # assembly_api (국회 OpenAPI 어댑터)
│   ├── middleware_auth.py        # Cognito JWT (staff/subscriber) + B2B API Key
│   ├── aws_clients.py            # @lru_cache boto3 session
│   └── Dockerfile                # API + 일회성 데이터 로더 겸용
├── web/                          Next.js 14 App Router
│   ├── app/                      # 14 시나리오 페이지 + objects + ops + meta
│   ├── components/               # PersonaSwitch, GuidedTour, CytoscapeView,
│   │                             # KoreaChoropleth, DataSourceBadge, AdMatchSidebar
│   └── lib/api-client.ts         # 타입 안전 SSE + REST
├── infra-cdk/                    AWS CDK v2 (TypeScript) — 6 stacks
│   ├── bin/assembly.ts
│   └── lib/{network,data,compute,ai,edge,observability}-stack.ts
├── data/                         데이터 적재
│   ├── load.py                   CLI: --neptune --opensearch --from-s3
│   ├── schemas.py                25+ 클래스 Pydantic + 관계
│   ├── real/                     국회 OpenAPI 어댑터 (bill, member, vote, ...)
│   ├── synthetic/                독자·광고·기사 합성 generator
│   └── external/                 뉴스 RSS, SNS, 여론조사 ETL
├── ontology/                     classes / relations / mappings / standards / adapters
├── tests/                        pytest smoke + tests/api/ httpx 통합
├── docs/                         architecture, ADRs (0001–0004), runbooks
├── scripts/                      eval_wow_queries, cognito 프로비저닝
├── .claude/                      agents, skills, hooks, commands, settings
├── .github/workflows/ci.yml      4-job CI
└── .harness-eval/                점수 history → README 배지
```

## Key Commands

```bash
# 컨테이너 이미지 빌드 (ARM64)
docker build --platform linux/arm64 -f api/Dockerfile -t <ecr>/assembly-dev-api:<tag> .
docker build --platform linux/arm64 -f web/Dockerfile -t <ecr>/assembly-dev-web:<tag> .

# 인프라 배포
cd infra-cdk && npx cdk deploy --all

# ECS 강제 롤아웃
aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-api --force-new-deployment

# 데이터 적재 (one-shot ECS 태스크)
aws ecs run-task --cluster assembly-dev-cluster --task-definition assembly-dev-api \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","data.load","--neptune","--opensearch","--from-s3"]}]}'

# 오프라인 테스트
make test
make ast
cd web && npx tsc --noEmit
cd infra-cdk && npx jest --ci

# 14 시나리오 × 6 페르소나 wow 평가 (배포된 CloudFront)
make wow-eval
```

## Conventions

### Code

- **Imports**: prefer relative imports inside `api/` (`from api.services import neptune`). 순환 회피용 lazy import는 함수 body 안에서 `from api.routers import district_map as _dm`.
- **Cypher**: 파라미터는 항상 `parameters={...}` keyword로 전달. 사용자 입력 f-string interpolate 금지.
- **boto3**: `from api.aws_clients import session as boto_session` — factory 호출 후 `.client(...)`.
- **SSE 이벤트**: 모든 스트리밍 endpoint는 `{"type": "phase|delta|log|final|result", "data": {...}}` 통일.
- **F-strings**: `{}` 안에서 quote 이스케이프 금지 (`f"...{d[\"k\"]}..."`는 SyntaxError). 로컬 변수 추출.
- **마크다운 렌더링**: `react-markdown` v10 + `remark-gfm`, `.chat-markdown` 스타일.
- **Agent tools**: TOOL_SPECS는 `api/services/agent.py` 단일 등록점. 새 도구는 JSON Schema 등록 + `_dispatch_tool` branch + `log` SSE event로 streaming + `_TRACE_BUF` 링버퍼.

### Models

- Bedrock chat/insights는 Sonnet 4.6 고정 (`BEDROCK_CHAT_MODEL_ID=global.anthropic.claude-sonnet-4-6`). Haiku로 silent downgrade 금지.
- 리랭커 Cohere rerank-v3 cross-region inference profile, 실패 시 RRF fallback.

### Infrastructure

- 모든 Fargate task는 ARM64. `--platform linux/arm64` 미지정 시 x86 이미지를 ECS가 reject.
- ECS service는 `:latest` + SHA-pinned tag 병행. 결정적 롤아웃은 SHA tag로 task definition revision 등록.
- Neptune은 private subnet — 직접 EC2 접근 불가. 로더는 같은 SG의 ECS one-shot task.
- VPC: 신규 VPC 생성 (gcc는 retail VPC import였지만 assembly는 독립 운영). 6 stack 모두 assembly 전용.
- 커스텀 도메인은 첫 배포에 미적용. Phase 5 polish에서 `cdk deploy assembly-edge -c domain=<...>` + Cognito callback PUT.

### 정치 중립성 (Critical)

- **Bedrock Guardrails**: 시나리오 B·C·I·K 응답의 입력·출력 양쪽에 적용.
- **Persona-aware tone**: `persona.system_prompt(persona_id, scenario_code)`에서 가치 판단 단정 표현 차단 지시.
- **bias score**: 모든 LLM 응답에 `political_balance_score`를 자동 첨부, 한쪽 정당만 부각될 경우 UI 경고.
- **시연 질문 풀**: `scripts/eval_wow_queries.py`의 사전 검증 5개 외 라이브 자유 입력은 백업 모드로 전환.
- **저장 금지**: `Reader.political_leaning` 등 정치 성향 추론 필드 절대 생성·저장 금지 (SECURITY.md §3 참조).

### 광고 매칭 윤리 (시나리오 L)

- `api/services/ad_matcher.py`는 별도 Lambda 함수로 분리. API 응답과 독립 처리.
- 3-way 모드: `keyword` / `embedding` / `agent` — `AD_MATCH_MODE` env로 전환, 라이브 시연 시 UI 토글.
- Agent 판단 시 다음 상황은 자동 광고 생략: 비극·재난, 정치인 비위 의혹, 미성년 피해자. reasoning trace는 `AdMatchDecision` 노드에 저장.

### Testing & CI

- **Test layout**: `tests/test_smoke.py` (각 시나리오 라우터 import) + `tests/api/` (Pydantic + /healthz + /api/search 통합 with httpx + boto3 mock) + `infra-cdk/test/stacks.test.ts` (Jest 스냅샷 per stack).
- **Env defaults**: `tests/conftest.py`에서 더미 값 설정 + `DEMO_PUBLIC_MODE=true` + `REQUIRE_ORIGIN_AUTH=false`. production은 미설정 (fail-closed).
- **Mocking**: 항상 import-site (`patch("api.routers.search.search.hybrid_search", ...)`).
- **CI gates** (`.github/workflows/ci.yml`): push/PR마다 4-job — `python-ast` · `tsc-check` · `cdk-synth` · `pytest`. 모두 <15초.
- **Wow eval ≥85%**: `scripts/eval_wow_queries.py` 미달 시 `sys.exit(1)`. 정치 중립성 메트릭도 별도 임계값.

### Harness (.claude/)

- `.claude/settings.json`: 공유 hooks + 60+ deny list. `.claude/settings.local.json`은 personal allow (gitignored).
- `scrub-secrets.sh` PreToolUse + PostToolUse: AKIA/ASIA/JWT/private-key/Slack/GitHub PAT 차단.
- `changelog-reminder.sh` Stop: 라우터·서비스·페이지·스택 변경 시 CHANGELOG 갱신 알림.
- Agents: `code-reviewer.md`, `security-auditor.md` (model: sonnet, structured output).
- Skills: `wow-query-eval.md`, `cypher-conventions.md`, `persona-context.md`.
- `harness-eval:full` (5–10분) 또는 `harness-eval:standard` (30초)로 12-dimension rubric 점수.

## Auto-Sync Rules

세션 중 다음 변경이 일어나면 **즉시** 해당 문서·코드를 동시 갱신:

- **새 시나리오 추가 (A–N 14개 외 확장)**: `web/components/Sidebar.tsx` · `web/app/<slug>/page.tsx` · `api/routers/<slug>.py` · `api/main.py` · `web/lib/api-client.ts` · `web/app/page.tsx` 홈 카드 (CARD_COLOR map) · `docs/api-reference.md` · `tests/test_smoke.py` parametrize · `web/components/GuidedTour.tsx` step. + CHANGELOG (EN/KR).
- **새 클래스 추가**: `_TYPE_REGISTRY`(`api/routers/objects.py`) · `TYPE_META`(`web/app/objects/[type]/page.tsx`) · Sidebar 객체 탐색 섹션 · `_CLASSES`/`_RELATIONS`(`api/routers/ontology.py`) · 홈 칩 그룹 · (persistent 시) `data/schemas.py` + 합성 generator.
- **새 Agent tool**: `api/services/agent.py:TOOL_SPECS` (JSON Schema) + `_dispatch_tool` branch + 의존성 있을 시 system prompt 체이닝 힌트.
- **새 페르소나 추가/제거**: `api/services/persona.py:PERSONA_REGISTRY` (SSOT) + `PersonaSwitch.tsx` · 홈 카드 · 사이드바 default · GuidedTour 시작 페르소나.
- **환경 변수 변경**: `.env.example` · `infra-cdk/lib/compute-stack.ts` task-def env · README env 섹션 · `docs/runbooks/`.
- **IAM scope 변경**: `SECURITY.md` + 관련 ADR.
- **아키텍처 결정**: `docs/decisions/NNNN-<slug>.md` from `.template.md` + 관련 모듈 CLAUDE.md "Key Design Decisions" 링크 + 코드 `@see ADR-NNNN`.
- **새 agent/skill/hook**: `.claude/settings.json` (hooks만) + frontmatter description의 trigger 조건 + 본 CLAUDE.md "Harness" 갱신.

## Memory References

User-specific memory: `~/.claude/projects/-home-ec2-user-my-project-ontology-for-assembly/memory/` (see `MEMORY.md` index). Project-specific 지식은 `docs/decisions/` (ADRs) + 모듈 CLAUDE.md.
