# ontology-for-assembly — 한국 언론사 Agentic 온톨로지 PoC 설계

| | |
|---|---|
| 작성일 | 2026-05-13 |
| 상태 | 설계 완료, Plan 1 (Foundation) 대기 |
| 참조 PoC | `ontology-for-gcc` (14 시나리오·25 클래스·5 페르소나) |
| 입력 자산 | 국회 OpenAPI (open.assembly.go.kr) + 합성 독자/광고/기사 + 외부 시그널(네이버 뉴스 RSS, SNS, 여론조사) |
| 빌드 접근 | gcc fork → 도메인 교체 → 대고객(B2C+B2B) 페르소나 확장 |
| 시나리오 | **14개 (A–N)** |
| 클래스 | **31 개** — 인물·조직 6 / 입법 7 / 주제·외부 6 / 미디어 2 / 독자 5 / 광고 4 / 분석 1 (+ Persona 코드 SSOT) |
| 관계 | **35 개** edge type |
| 페르소나 | **6 페르소나** — 편집국 / 데이터·AI / 광고·세일즈 (내부 3) + 일반 독자 / 유료 구독자 / 기업·B2B (대고객 3) |
| Cohort | 실 데이터(국회 OpenAPI) + 합성(독자 ~5만 + 광고 ~500 + 기사 ~2,000) + 외부(뉴스·SNS·여론조사) |

## Summary

**한국 언론사**가 국회 공공 OpenAPI를 데이터 기반으로 활용하여 ① 편집국 생산성, ② 독자 서비스 차별화(B2C), ③ 정책 인텔리전스(B2B)를 동시에 시연할 수 있는 30–60분 PoC. 25+ 클래스 통합 온톨로지를 Neptune에 적재하고 AWS Bedrock + AgentCore + OpenSearch + 외부 신호 API 위에서 14개 wow 시나리오(A–N)를 통해 *Agentic AI 분석*을 시연.

핵심 차별점 세 가지:
1. **3단계 진화 비교** (시나리오 B): Chatbot(RAG) → Agent(Tool Use) → Agentic AI(다중 에이전트)
2. **AI 거버넌스 광고 매칭** (시나리오 L): 키워드·임베딩·Agent 판단 3-way + Agent의 윤리적 광고 생략 trace
3. **B2C·B2B 동시 페르소나** (6개): 편집국·데이터·AI·광고/세일즈(내부) + 일반 독자·유료 구독자·기업/B2B(외부)

## Goals

1. 국회 OpenAPI 7+ 엔드포인트(의안·의원·표결·위원회·회의록·정당·국정감사)와 합성 독자·광고·기사 + 외부 시그널을 단일 진실원으로 **25+ 클래스 온톨로지**를 Neptune에 적재. 동일 데이터를 OpenSearch BM25(Nori) + Cohere KNN 하이브리드 인덱스로 동시 검색.
2. **3단계 진화 비교 시연(B)** + **광고 매칭 거버넌스(L)** + **편집국·독자·B2B 6 페르소나 동시 데모**의 세 가지 메인 시연 메시지를 end-to-end로 구현.
3. gcc 동일 패턴(FastAPI + Next.js 14 + CDK 6-stack + Sonnet 4.6 + AgentCore Memory + Code Interpreter)을 그대로 채택해 구현 리스크 최소화.
4. CI 4-job + **14 시나리오 × 6 페르소나** wow 쿼리 평가 ≥85% + harness-eval 7.5+/10 (B 등급) + **political_balance_score ≥0.8** 첫 릴리스 기준.
5. **데이터 출처 투명성**: 모든 화면에 `DataSourceBadge` — real/synthetic/external 명시.
6. **정치 중립성 가드레일**: Bedrock Guardrails + 사전 검증 시연 질문 풀 + 백업 영상 + bias score 자동 계산.

## Non-Goals

- 실시간 정치인 비위 의혹 보도 (PoC는 사실관계 분석 도구로 한정).
- 광고 실 인벤토리 연동 (합성 광고 카탈로그 사용).
- 모바일 네이티브 앱 (브라우저만).
- 실시간 스트리밍 적재 (배치 ETL + Neptune Bulk Loader).
- 회의록 음성-텍스트 변환 (이미 텍스트화된 회의록만 사용).
- 정치인 개인 SNS 계정 직접 스크래핑 (공개 API + Naver/Daum 검색만).

## Decisions Log

| ID | 항목 | 선택 | 대안 | 근거 |
|---|---|---|---|---|
| D1 | 도메인·범위 | 언론사 + 국회 공공 데이터, gcc 동일 패턴 | 정부·정당 직접 / 학술 / 시민단체 | 청중(언론사 CxO) 적합, 공공 API 라이선스 무부담 |
| D2 | 페르소나 | 6개 (내부 3 + 대고객 3 — 편집국·데이터·AI·광고/세일즈·일반 독자·유료 구독자·기업/B2B) | 5개 내부만 / 8개 풀스펙 | 사용자 명시 "대고객 서비스 향" + B2C 일반/유료 차별화 + B2B 정책 인텔리전스 |
| D3 | 시나리오 수 | 14개 A–N (gcc 동등) | 6개 MVP / 10개 | 사용자 명시 "Full 14개" + gcc 코드 최대 재활용 |
| D4 | 클래스 수 | 25+ — 인물 6 / 입법 7 / 주제 6 / 미디어 2 / 독자 5 / 광고 4 / 분석 2 | 20 / 30 | gcc 동등 풍부함 + B2C 독자 측 노드 추가 |
| D5 | 데이터 모드 | 실(OpenAPI) + 합성(독자~5만, 광고~500, 기사~2,000) + 외부(뉴스·SNS·여론) | 100% 합성 / 100% 실 | 독자·광고는 실 보유 불가, 의안·표결은 실데이터 사용. 출처 배지로 구분 |
| D6 | 인프라 패턴 | gcc 동일 — ap-northeast-2 + 6-stack CDK | 다른 리전 / 단순화 | 컨벤션 일치, gcc 운영 노하우 재사용 |
| D7 | VPC | **신규 VPC 생성** (gcc는 retail import였음) | retail 공유 / hub-spoke | assembly는 독립 운영, 데이터·네트워크 격리 |
| D8 | 자원 공유 | 없음. 모두 assembly 전용 | gcc/retail 공유 | 독립 teardown + 정치 도메인 격리 |
| D9 | 빌드 접근 | gcc fork → 도메인 rename → 페르소나 추가 → 라우터 14개 새로 작성 | greenfield | 시간 단축 + 시나리오 템플릿 확립 |
| D10 | 적재 방식 | Neptune Bulk Loader + S3 (~100만+ 노드) | 직접 MERGE | gcc 동일, 7~8배 빠름 |
| D11 | **광고 매칭 3-way** | 키워드 · 임베딩 · Agent 판단 — 별도 Ad Matcher Lambda 분리 | 단일 모드 / API 인라인 | "AI 거버넌스" 메인 차별점, 라이브 토글 시연 |
| D12 | **3단계 진화 비교** | 시나리오 B에 Chatbot/Agent/Agentic AI 3 모드 사이드바이사이드 | 한 모드만 | 청중에게 "왜 Agentic AI인가" 즉각 이해 |
| D13 | **다중 에이전트 구성** | 4 에이전트 — Planner / Graph(Neptune Cypher) / Analyst(가설·재질의) / Editor(기사 형식·출처) | 단일 에이전트 / 2 에이전트 | 자율 협업의 풍부함 시연 |
| D14 | **정치 중립성** | Bedrock Guardrails + bias score + 시연 질문 사전 검증 풀 + 백업 영상 | guardrail 없음 / Guardrails만 | 청중 신뢰 확보 + 시연 사고 방지 |
| D15 | 페르소나 인증 다층화 | Cognito staff + Cognito subscriber + Cognito Guest + API Gateway API Key | 단일 Cognito | 6 페르소나 권한·요금제·rate limit 분리 |
| D16 | Reader 노드 익명화 | 게스트 쿠키 → 솔티드 해시로만 노드 ID 생성. IP/UA 미저장 | 명시 식별 | GDPR/개인정보보호법 PoC 안전성 |
| D17 | 외부 시그널 어댑터 | 네이버 뉴스 검색 API + 합성 SNS + 합성 여론조사 (실 API 후속) | 실 SNS 스크래핑 | 라이선스·rate limit 회피, 시연 안정성 |
| D18 | **AdMatchDecision 노드** | 모든 광고 매칭 시도를 `(Article)-[:CONSIDERED]->(AdMatchDecision {mode, score, reason, allowed})-[:CANDIDATE]->(Advertisement)`로 저장 | 로그 파일 | 운영 콘솔에서 reasoning trace 사후 감사 |
| D19 | Cypher 표현 | openCypher (Neptune) — `parameters={...}` 키워드 강제 | Gremlin | gcc 동일, FastAPI 통합 단순 |
| D20 | 시연 시연 단축키 | 발표자 모드 단축키 — 백업 영상 즉시 전환, 페르소나 빠른 토글 | 없음 | 라이브 사고 대비 |

## 1. Architecture & Infrastructure

### 1.1 인프라 토폴로지

```
ap-northeast-2 (서울)
┌──────────────────────────────────────────────────────────────────────┐
│  assembly-network-stack (신규 VPC)                                    │
│  ┌─────────────────────────────────────────┐                          │
│  │  VPC  (10.30.0.0/16, 3-AZ)              │                          │
│  │  public / private(NAT) / isolated         │                          │
│  │  NAT GW · prefix-list                     │                          │
│  └─────────────────────────────────────────┘                          │
│         │                                                             │
│  ┌──────┴──────────────────────────────────────────────────┐         │
│  │  assembly stacks                                           │         │
│  │  • assembly-network: VPC + SGs (api/neptune/os/lambda)    │         │
│  │  • assembly-data:    Neptune cluster, OpenSearch Serv,    │         │
│  │                       S3 buckets (raw/uploads/synthetic),   │         │
│  │                       DynamoDB (b2b-keys, ad-inventory,     │         │
│  │                       ad-impression, reader-profile)        │         │
│  │  • assembly-compute: ECS cluster, ALB, api+web 2/2,         │         │
│  │                       Ad Matcher Lambda                      │         │
│  │  • assembly-ai:      Bedrock KB, Guardrails (정치 중립),     │         │
│  │                       AgentCore Memory store                 │         │
│  │  • assembly-edge:    CloudFront(B2C web) + CloudFront(B2B),  │         │
│  │                       Lambda@Edge, Cognito(staff/subscriber/ │         │
│  │                       guest), API Gateway(B2B), Route53      │         │
│  │  • assembly-observ:  CloudWatch dashboards, alarms,          │         │
│  │                       political_balance_score 메트릭          │         │
│  └──────────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 기술 스택

| Layer | 선택 |
|---|---|
| Backend runtime | Python 3.12 on Fargate ARM64 |
| Backend framework | FastAPI + Pydantic v2 + uvicorn |
| Frontend runtime | Node.js 20 on Fargate ARM64 |
| Frontend framework | Next.js 14 App Router (standalone) + React 18 + Tailwind |
| Graph DB | Amazon Neptune (openCypher) — assembly 전용 클러스터 |
| Search | OpenSearch Serverless (Nori BM25 + Cohere KNN, RRF) |
| Foundation models | Bedrock Sonnet 4.6 (chat·insights), Cohere embed-v4, Cohere rerank-v3 |
| Memory | AgentCore Memory (staff/subscriber/guest namespaces 분리) |
| Sandbox | AgentCore Code Interpreter Firecracker microVM |
| Maps | react-simple-maps + d3-geo + KOSTAT 17 시도 GeoJSON |
| Auth | Cognito user pool (staff/subscriber) + Cognito Guest Identity Pool (일반 독자) + Lambda@Edge JWT |
| B2B API | API Gateway Usage Plan + API Key + DynamoDB |
| Edge | CloudFront → ALB (HTTP origin, cloudfront prefix-list SG) |
| Compute | ECS Fargate ARM64, two-replica services |
| Ad Matcher | Lambda 별도 + Bedrock 호출 |
| IaC | AWS CDK v2 (TypeScript) — 6 stacks |

### 1.3 도메인 분리 배포 패턴

- 첫 배포: `cdk deploy --all` (도메인 없음, `*.cloudfront.net`).
- 도메인 추가: `cdk deploy assembly-edge -c domain=assembly.whchoi.net` 후 `scripts/cognito-update-callbacks.sh` (전체 PUT 안전화).

### 1.4 보안

- Cognito RS256 JWT, JWKS TTL 캐시.
- ALB SG → `com.amazonaws.global.cloudfront.origin-facing` prefix-list만 ingress.
- Neptune private subnet, 로더는 ECS one-shot task.
- Bedrock Guardrails 입력 스크럽 + 출력 필터 (B·C·I·K).
- IAM least privilege, Secrets Manager + KMS.
- `.claude/hooks/scrub-secrets.sh` PreToolUse + PostToolUse.
- `raw_data/`, `synthetic_seed/` `.gitignore`. KMS S3 별도 보관.

자세한 보안 정책은 `SECURITY.md` 참조.

## 2. Project Structure

```
ontology-for-assembly/
├── api/                          # FastAPI (Python 3.12, ARM64)
│   ├── main.py                   # 14 라우터 + objects/ontology/personas/ops 등록
│   ├── config.py                 # Settings (env)
│   ├── aws_clients.py            # @lru_cache boto3 session
│   ├── middleware_auth.py        # Cognito JWT (staff/subscriber) + B2B API Key
│   ├── routers/                  # 17 파일 — 14 시나리오 + objects + ontology + personas + ops
│   ├── services/                 # neptune, opensearch, bedrock, agent,
│   │                             # agentcore, guardrails, persona, cohort,
│   │                             # ad_matcher (3-way), assembly_api (OpenAPI 어댑터),
│   │                             # external (news/sns/poll), three_stage (B 모드 분기),
│   │                             # multi_agent (Planner/Graph/Analyst/Editor)
│   ├── models/                   # Pydantic v2 도메인 모델
│   └── Dockerfile                # API + 일회성 데이터 로더 겸용
├── web/                          # Next.js 14 (TS, ARM64)
│   ├── app/                      # 14 시나리오 페이지 + objects/[type] + meta + ops
│   ├── components/               # PersonaSwitch (6), GuidedTour, CytoscapeView,
│   │                             # KoreaChoropleth (17 시도), JourneyTimeline,
│   │                             # DataSourceBadge (real/synthetic/external),
│   │                             # AdMatchSidebar (모든 페이지 우측), ThreeStageCompare,
│   │                             # BiasScoreIndicator
│   └── lib/api-client.ts         # 타입 안전 SSE + REST
├── infra-cdk/                    # CDK v2 (TS) — 6 stacks
│   ├── bin/assembly.ts
│   └── lib/{network,data,compute,ai,edge,observability}-stack.ts
├── data/                         # 데이터 적재
│   ├── load.py                   # CLI
│   ├── schemas.py                # 25+ 클래스 Pydantic + 관계
│   ├── real/                     # 국회 OpenAPI 어댑터 — bill, member, vote, committee,
│   │                             # session, party, agency
│   ├── synthetic/                # reader, advertisement, ad_inventory, article generator
│   └── external/                 # naver_news, sns_signal, poll_result ETL
├── ontology/                     # classes / relations / mappings / standards / adapters
│   └── standards/                # 의안 카테고리·정당 코드 카탈로그 (yaml)
├── tests/
├── docs/                         # specs / decisions / runbooks / api-reference
├── scripts/
├── .claude/                      # agents · skills · hooks · commands · settings
├── .github/workflows/ci.yml
├── .harness-eval/
├── CLAUDE.md · README.md · SECURITY.md · CHANGELOG.md
└── .env.example · requirements*.txt · Makefile
```

## 3. 14 시나리오 × 6 페르소나 매트릭스

### 3.1 시나리오 카탈로그

| code | 이름 | 핵심 기술 | PDF 시그니처 |
|---|---|---|:---:|
| A | 의안·의원 의미 검색 | BM25(Nori) + Cohere KNN + RRF + rerank-v3 + 1-hop Cytoscape | |
| B | **3단계 진화 챗봇** | Chatbot(RAG) / Agent(Tool Use) / Agentic AI(4-agent 협업) 사이드바이사이드 | ★ |
| C | 기사 인사이트 | Sonnet 4.6 스트리밍 + Code Interpreter NanumGothic matplotlib | |
| D | 페르소나 매칭 | 6 페르소나 KPI 가중치 그래프 워크 | |
| E | 의원 정치성향 클러스터링 | KMeans + LLM 중립 라벨 ("개혁성향" 대신 "혁신 입법 다수") | |
| F | 유사 의원/의안 룩어라이크 | Cohere embed-v4 + KNN | |
| G | 기사 ROI/CTR 시뮬레이션 | Bayesian + Code Interpreter 분포 | |
| H | 지역구 choropleth | 17 시도 GeoJSON + 의원 분포 | |
| I | **편향·정치중립 가드레일** | Bedrock Guardrails + political_balance_score + bias detector | |
| J | 외부 신호 융합 | 네이버 뉴스 + SNS + 여론조사 cross-source | |
| K | **표결·발언 패턴 변화** | pandas 윈도 + LLM 패턴 라벨 ("당론 이탈", "스윙 보트") | ★ |
| L | **광고 매칭 매트릭스 (3-way)** | 키워드·임베딩·Agent 판단 + AdMatchDecision trace | ★ |
| M | **의원 정치 여정 timeline** | 발의·표결·발언·위원회 통합 (App+Tx+Term+Coupon 패턴) | ★ |
| N | 이슈 × 입법 상관 | 토픽 트렌드 ↔ 법안 발의 산점도 | |

PDF 3페이지 시그니처(★) 4개: 시연 핵심 콘텐츠로, 별도 PDF 자료에도 포함.

### 3.2 페르소나 × 시나리오 우선순위 매트릭스

페르소나 전환 시 사이드바·홈카드·system prompt가 함께 변하도록 `PERSONA_REGISTRY`에 명시.

| 페르소나 | 1순위 시나리오 | 2순위 | KPI focus | tone |
|---|---|---|---|---|
| **편집국** (내부) | C·B·K·M | A·D·N | 취재 신선도, 발굴 가능성, 출처 신뢰도 | 차분, 사실 중심, 출처 우선 |
| **데이터·AI** (내부) | E·J·K·N | C·B·F | 패턴 인사이트, 데이터 출처 투명성 | 분석적, 정량 수치 강조 |
| **광고·세일즈** (내부) | L·G·F | D·A | 광고 매칭 정확도, ROI, CTR | 비즈니스, 매출 관점 |
| **일반 독자** (B2C 무료) | A·B·H·M | C·D | 입문성, 지역 관심, 친절 가이드 | 친근, 평이, 그래픽 우선 |
| **유료 구독자** (B2C 유료) | C·K·M·D | B·N·J | 심층 분석, 알림, PDF 리포트 | 전문가, 무제한, 개인화 |
| **기업/B2B** (B2B) | A·C·J·K | F·N | 정책 영향, 규제 변화 알림 | 공식, 보고서 형식, API 응답 |

### 3.3 시나리오 B (3단계 진화 챗봇) 상세

시연의 메인 차별점. 같은 질문에 3 모드가 동시 응답 → 사이드바이사이드 패널.

```
사용자 질문 (예: "최근 1년간 AI 관련 입법 활동이 가장 활발한 의원 3명과
                  공동발의 네트워크, 표결 협력 패턴을 알려줘")
        │
        ├─→ [Stage 1: Chatbot (RAG)]
        │     Bedrock KB + OpenSearch top-K
        │     → "관련 법안 5건, 발의자 ○○○, ○○○"
        │     한계: 협력 패턴 못 다룸
        │
        ├─→ [Stage 2: Agent (Tool Use)]
        │     Bedrock Converse + 도구 4개 순차 호출
        │     search_bills → get_proposers → cosponsor_network → vote_analysis
        │     → 구조화 답변 + 단순 네트워크 그래프
        │     한계: 사전 정의 흐름, 새 질문 약함
        │
        └─→ [Stage 3: Agentic AI (4 에이전트)]
              Planner: 질문 분해 → 6 하위 과제
              Graph: Neptune Cypher 5회 실행 → 그래프 데이터
              Analyst: 결과 해석 → 가설 → Graph에 재질의
              Editor: 기사 초안 + Cytoscape 시각화 + 후속 취재 포인트 3개
              → 기사 + 시각화 + "추가로 ○○○ 의원 지역구 산업과의 상관관계 확인 권장"
              하이라이트: Agent가 스스로 후속 질문 제안
```

### 3.4 시나리오 L (광고 매칭 매트릭스) 상세

별도 Ad Matcher Lambda + 사이드바 위젯으로 모든 화면에 표시.

```
[화면 표시 중인 콘텐츠]
        │
        ↓
[Ad Matcher Lambda]
        │
        ├─→ Mode A: Keyword
        │     "AI", "입법" → 광고 인벤토리에서 키워드 매칭
        │     → AI 교육 광고 (관련성: 낮음, 점수 0.45)
        │
        ├─→ Mode B: Embedding
        │     콘텐츠 임베딩 → 광고 임베딩 코사인 유사도
        │     → 기업 RegTech 솔루션 광고 (관련성: 중, 점수 0.71)
        │
        └─→ Mode C: Agent 판단 (★ 메인 차별점)
              Bedrock + 시스템 프롬프트 = "이 광고가 이 콘텐츠에 노출되는 것이 적절한가?"
              체크: 비극·재난? 정치인 비위? 미성년 피해자? 광고주 정파 충돌?
              결과 1: 노출 (광고: ○○○, 신뢰도 0.87, 이유: "정책 관련 정보성 콘텐츠")
              결과 2: 미노출 (이유: "정치인 비위 의혹 관련 - 광고주 평판 보호")
              → 모든 결정은 AdMatchDecision 노드에 reasoning 저장
              → 운영 콘솔에서 사후 감사 가능
```

UI: 사이드바 위젯 상단에 3 모드 토글 + "현재 모드의 결정 이유" 텍스트.

## 4. 25+ 클래스 온톨로지

### 4.1 클래스 카탈로그

```
[1] 인물·조직 (6)
    :Person          — 의원. 핵심 속성: assembly_id, name, term, district, party_id,
                       committees, profile_image, source
    :Party           — 정당. name, founded_date, ideology_tag (중립 라벨)
    :Staff           — 보좌진. person_id (의원), role, since
    :Committee       — 위원회. name, type (상임/특별), chair_person_id
    :District        — 지역구. sido, sgg, code, geo_center
    :Term            — 회기. number (e.g. 21대), start_date, end_date

[2] 입법 (7)
    :Bill            — 의안. bill_id, title, proposed_date, status, category,
                       proposer_id, summary_text, full_text_url
    :Law             — 법령. law_id, name, last_revised
    :Amendment       — 개정안. bill_id, original_law_id, diff_summary
    :Vote            — 표결. vote_id, bill_id, date, result, attendance_count
    :Statement       — 발언. statement_id, person_id, session_id, date, content,
                       sentiment, topics
    :Session         — 회의. session_id, type (본회의/상임위), date, committee_id
    :Budget          — 예산. fiscal_year, ministry, amount, status

[3] 주제·외부 (6)
    :Topic           — 토픽 (AI 자동 추출). name, category, embedding
    :Policy          — 정책. name, related_bills[], related_agencies[]
    :Agency          — 기관 (국정감사 대상). name, type (정부/공기업)
    :ElectionResult  — 선거 결과. election_id, district_id, person_id, won
    :PollResult      — 여론조사. pollster, date, topic, sample_size, breakdown
    :SocialSignal    — SNS·뉴스 신호. source, url, date, sentiment, topic_ids

[4] 미디어 측 (2)
    :Article         — 기사. article_id, title, content, published_at, author,
                       topic_ids[], referenced_persons[], referenced_bills[],
                       source ∈ {real, synthetic}
    :Tag             — 태그. name, category

[5] 독자 측 (5) ★ B2C 신규
    :Reader          — 독자. reader_id (솔티드 해시), tier (anonymous/free/paid),
                       interests[], region, since (시간 시그널만)
    :ReaderProfile   — 독자 프로파일 (집계). reader_id, top_topics, reading_minutes_avg,
                       device_class. 절대 political_leaning 필드 만들지 말 것
    :SubscriptionTier — 구독 등급. name (free/standard/premium), features[], price
    :ReadingEvent    — 읽기 이벤트. reader_id, article_id, duration_sec, completed
    :Bookmark        — 책갈피. reader_id, target_id (article|person|bill), date

[6] 광고 (4) ★ 시나리오 L
    :Advertisement   — 광고. ad_id, advertiser, category, content_summary,
                       avoid_topics[] (광고주 명시 회피 토픽)
    :AdInventory     — 인벤토리. ad_id, budget, period_start, period_end, target_personas[]
    :AdImpression    — 광고 노출 이벤트. impression_id, reader_id, article_id, ad_id,
                       date, ttl_14d
    :AdMatchDecision — ★ 매칭 결정 trace. decision_id, mode (keyword/embedding/agent),
                       article_id, candidate_ad_ids[], chosen_ad_id (or null),
                       reason_text, score, timestamp

[7] 분석 메타 (2)
    :Cluster         — 의원 클러스터. cluster_id, label (중립), centroid, member_ids[]
    :Persona         — 페르소나 (6). persona_id, name_kr, kpi_focus, tone, scenario_priority,
                       default_cohort
```

총 **25 클래스 + Persona = 26**. Persona는 SSOT 코드 상수.

### 4.2 핵심 관계 (~35 엣지 타입)

```
인물·정당:
  (Person)-[:BELONGS_TO {from, to}]->(Party)
  (Person)-[:REPRESENTS]->(District)
  (Person)-[:SERVED_IN]->(Term)
  (Staff)-[:WORKS_FOR]->(Person)

입법 활동:
  (Person)-[:PROPOSED]->(Bill)
  (Person)-[:CO_PROPOSED]->(Bill)
  (Person)-[:MEMBER_OF]->(Committee)
  (Committee)-[:OVERSEES]->(Agency)
  (Bill)-[:AMENDS]->(Law)
  (Bill)-[:RELATES_TO]->(Topic)
  (Bill)-[:ASSIGNED_TO]->(Committee)
  (Vote)-[:ON]->(Bill)
  (Person)-[:VOTED {choice}]->(Vote)
  (Statement)-[:BY]->(Person)
  (Statement)-[:AT]->(Session)
  (Statement)-[:ABOUT]->(Topic)
  (Session)-[:OF]->(Committee)

주제·외부:
  (PollResult)-[:ABOUT]->(Topic)
  (SocialSignal)-[:ABOUT]->(Topic)
  (Policy)-[:LINKS]->(Bill)

미디어·독자·광고:
  (Article)-[:ABOUT]->(Topic|Bill|Person)
  (Reader)-[:READ]->(ReadingEvent)-[:OF]->(Article)
  (Reader)-[:FOLLOWS]->(Person|Topic)
  (Reader)-[:BOOKMARKED]->(Bookmark)
  (Reader)-[:HAS_TIER]->(SubscriptionTier)
  (Article)-[:CONSIDERED]->(AdMatchDecision)
  (AdMatchDecision)-[:CANDIDATE]->(Advertisement)
  (AdMatchDecision)-[:CHOSE]->(Advertisement)
  (AdImpression)-[:OF_AD]->(Advertisement)
  (AdImpression)-[:ON_ARTICLE]->(Article)
  (AdImpression)-[:TO_READER]->(Reader)

분석 메타:
  (Person)-[:IN_CLUSTER]->(Cluster)
  (Reader)-[:MATCHED]->(Persona)
```

### 4.3 데이터 cohort 및 출처 태깅

모든 노드는 `source ∈ {real, synthetic, external}` 속성을 가짐.

| 클래스 | 주 데이터 출처 | 합성/외부 |
|---|---|---|
| Person, Bill, Vote, Committee, Statement, Session, Party | 국회 OpenAPI (real) | — |
| Agency, ElectionResult | 국회 OpenAPI (real) | — |
| PollResult | (real 가능 시) / synthetic | external 후속 |
| SocialSignal | 네이버 뉴스 (external) + 합성 SNS | mix |
| Article | synthetic (~2,000) | — |
| Reader, ReadingEvent, Bookmark, SubscriptionTier | synthetic (~50,000 독자) | — |
| Advertisement, AdInventory, AdImpression, AdMatchDecision | synthetic | — |
| Topic | LLM 추출 (Bill·Statement·Article에서) | — |
| Cluster | KMeans 결과 | — |

## 5. 데이터 파이프라인

### 5.1 적재 흐름

```
[국회 OpenAPI 7+]      ─┐
[합성 generator 4종]    ├─→ data/load.py (S3 upload)
[외부 API: 네이버 뉴스 etc] ─┘            │
                                          ↓
                            [Neptune Bulk Loader (csv) or
                             ECS one-shot openCypher MERGE]
                                          ↓
                                     [Neptune DB]
                                          │
                                          ↓
                            [Embedding 파이프라인 — Cohere embed-v4]
                                          ↓
                            [OpenSearch Serverless hybrid index]
```

### 5.2 실시간 reader 이벤트 (선택)

PoC에서는 batch 시뮬레이션:
- 합성 generator가 `ReadingEvent` 50만 건 사전 생성
- `(Reader)-[:READ]->(:ReadingEvent)-[:OF]->(:Article)` 직접 적재
- 운영 모드에서는 Kinesis → Lambda → Neptune 업데이트 패턴 (Phase 5 polish)

### 5.3 데이터 출처 투명성

모든 시나리오 페이지 상단에 `DataSourceBadge` 컴포넌트:
- 🟢 **real** — 국회 OpenAPI 원본
- 🟡 **synthetic** — 합성 데이터
- 🔵 **external** — 외부 시그널

페르소나·시나리오에 따라 cohort 자동 필터링 (`api/services/cohort.py:select(persona_id, scenario_code)`).

## 6. 정치 중립성 가드레일 (Critical)

### 6.1 Bedrock Guardrails 룰

- **차단 어휘**: 정당명 + 비방 표현 조합, 정치인 + 모욕 표현, 종교·성별·지역 차별
- **변환 규칙**: "○○당이 잘못했다" → "○○당의 해당 사안 처리에 대해 비판이 있다 (출처: ...)"
- **출력 필수 요소**: 정치 평가 시 반드시 출처 인용 + 반대 의견 병기

### 6.2 시스템 프롬프트 가드

모든 LLM 호출에 다음 system prompt suffix 자동 첨부:
```
당신은 한국 언론사의 사실 분석 도구입니다. 다음 원칙을 반드시 지키세요:
1. 특정 정당·정치인에 대한 단정적 가치 판단을 하지 마세요.
2. 항상 데이터 출처와 통계 근거를 함께 제시하세요.
3. 비판적 의견과 옹호 의견이 있는 사안은 양쪽 모두 짧게 언급하세요.
4. 정치인의 사적 영역(가족·개인 신념)에 대한 추론을 하지 마세요.
```

### 6.3 political_balance_score 메트릭

응답마다 자동 계산되어 `final` SSE event에 첨부:
```python
def political_balance_score(response_text: str, bills_referenced: list[str]) -> float:
    # 1. 정당별 언급 빈도의 표준편차 → 작을수록 균형
    # 2. 긍정·부정 표현의 정당별 분포 → 작을수록 균형
    # 3. score ∈ [0.0, 1.0], 0.8 미만이면 UI 노란색 경고
```

### 6.4 시연 안전장치

- **사전 검증 시연 질문 풀** (`scripts/eval_wow_queries.py`): 5개 핵심 질문 + 30개 보조. 라이브 시연은 풀에서만 선택.
- **자유 입력 모드**: 청중 질문 시 ① guardrails 우선 ② 백업 모드 옵션 (사전 응답으로 대체) ③ 발표자 단축키로 다음 슬라이드로 전환.
- **백업 영상**: 모든 시연 시나리오는 사전 녹화 영상 백업 (`docs/demo-recordings/`).
- **편향 알림**: `political_balance_score < 0.8`이면 UI에 즉시 노란색 경고 + 운영 콘솔에 로그.

자세한 정책은 `SECURITY.md §2` 참조.

## 7. 핵심 컴포넌트 노트

- **`services/agent.py:TOOL_SPECS`** — Agent(Stage 2) + Agentic(Stage 3) 도구 풀. 기본 4개(`memory_recall`, `neptune_subgraph`, `semantic_search`, `kb_lookup`) + 도메인 6개(`person_lookup`, `bill_lookup`, `cosponsor_network`, `vote_analysis`, `committee_walk`, `district_stats`) + 외부 2개(`news_search`, `poll_lookup`).
- **`services/three_stage.py`** — 시나리오 B의 모드 분기. `stage1_rag()`, `stage2_agent()`, `stage3_agentic()`. 모두 같은 SSE `phase` 이벤트 어휘 사용.
- **`services/multi_agent.py`** — Stage 3의 4 에이전트 협업. `Planner` → `Graph` → `Analyst` → (재호출 가능) → `Editor`. 각 단계 SSE `log` 이벤트로 streaming.
- **`services/ad_matcher.py`** — Lambda 별도 배포. `match(article_id, reader_id, mode)` 진입. mode별 다른 함수.
- **`services/persona.py:PERSONA_REGISTRY`** — 6 페르소나 SSOT. `{persona_id: {name_kr, tier, kpi_focus, tone, scenario_priority, default_cohort, system_prompt_suffix}}`.
- **`services/cohort.py:select(persona_id, scenario_code)`** — `data_depth`/`source` 조합 반환. 예: `select('paid_subscriber', 'M') → ['real']` (구독자에게는 실 데이터만).
- **`services/assembly_api.py`** — 국회 OpenAPI 어댑터 (7 엔드포인트). Secrets Manager에서 키 로드, S3 캐시.
- **`services/guardrails.py:check(prompt, output, persona)`** — Bedrock Guardrails 호출 wrapper + bias score 계산.
- **`web/components/DataSourceBadge.tsx`** — 모든 시나리오 페이지 상단. real/synthetic/external 배지.
- **`web/components/AdMatchSidebar.tsx`** — 모든 페이지 우측. 3-mode 토글 + 현재 결정 이유.
- **`web/components/ThreeStageCompare.tsx`** — 시나리오 B 전용. 3 패널 SSE 동시 스트리밍.
- **`web/components/BiasScoreIndicator.tsx`** — political_balance_score 시각화. 0.8 미만 노란색.

## 8. Phase 분해 (5 plans)

| Phase | 산출물 | 기간 |
|---|---|---|
| **Plan 1 — Foundation** | 6-stack CDK 배포, ECR 이미지, Cognito 3 그룹, Lambda@Edge JWT, 25 클래스 schemas | 1주 |
| **Plan 2 — Data** | 국회 OpenAPI 어댑터 7종, 합성 generator 4종, 외부 ETL 3종, Neptune 적재 100만+ 노드 | 1주 |
| **Plan 3 — Scenarios A–G** | 시나리오 7개 라우터+페이지+테스트, 3-stage 챗봇(B)이 핵심 | 1.5주 |
| **Plan 4 — Scenarios H–N + Ad Matcher** | 시나리오 7개 라우터+페이지, Ad Matcher Lambda, AdMatchDecision trace | 1.5주 |
| **Plan 5 — Polish** | Object Explorer 25 클래스, 운영 콘솔 5 패널, GuidedTour, 정치 중립성 메트릭 자동화, custom domain, harness-eval 8.5+/A, wow-eval ≥90% | 1주 |

총 약 6주 예상.

## 9. 인수 기준 (Acceptance Criteria)

1. **시나리오 14개 모두** end-to-end 동작. 라이브 시연 가능 (백업 영상 별도).
2. **CI 4-job 그린** + smoke 50+ 테스트 통과.
3. **wow-query 평가**: 14 × 6 = 84 케이스 중 ≥85% 통과. CloudFront 라이브 측정.
4. **political_balance_score 평균 ≥0.85** (전 시나리오 LLM 응답).
5. **광고 매칭 trace**: `AdMatchDecision` 노드 모든 매칭 시도 기록. 운영 콘솔에서 조회 가능.
6. **harness-eval 점수 ≥8.5/A** (12-dimension rubric).
7. **DataSourceBadge** 모든 화면 노출 + 페르소나 전환 즉시 반영.
8. **6 페르소나 인증·권한** 모두 작동: staff(SSO), subscriber(SSO+tier), guest(쿠키), B2B(API Key).

## 10. References

- gcc 차용 원본: https://github.com/whchoi98/ontology-for-gcc (plan1-foundation)
- 국회 OpenAPI: https://open.assembly.go.kr/portal/openapi/main.do
- gcc spec (포맷 모델): `docs/superpowers/specs/2026-05-08-ontology-gcc-design.md`
- gcc CLAUDE.md (컨벤션 모델): 클론된 `/tmp/ontology-for-gcc/CLAUDE.md`
- Bedrock Guardrails 가이드: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html
- 한국 KOSTAT 시도 코드: https://kostat.go.kr
