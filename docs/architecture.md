# Architecture

<a href="#english"><img src="https://img.shields.io/badge/lang-English-blue.svg" alt="English"></a>
<a href="#korean"><img src="https://img.shields.io/badge/lang-한국어-red.svg" alt="Korean"></a>

---

<a id="english"></a>

# English

## System Overview

`ontology-for-assembly` is a multi-runtime monorepo demo that runs 23 newsroom Agentic AI scenarios (A–W) and 6 personas on top of a 31-class domain ontology sourced from the Korean National Assembly Open API. A Python FastAPI backend (21 routers) and a Next.js 14 frontend run as ARM64 Fargate services behind CloudFront, backed by Amazon Neptune (openCypher) and OpenSearch Serverless (hybrid BM25 + KNN), with Bedrock Sonnet 4.6 and AgentCore providing the agentic layer. All infrastructure is provisioned by AWS CDK v2 across 6 stacks that import a shared VPC (ADR-0006).

## Components by Layer

### Ingestion

| Component | Location | Role |
|---|---|---|
| Load CLI | `data/load.py` | argparse entrypoint; one-shot ECS task (`--source`/`--to`/`--neptune`/`--opensearch`) |
| AWS loader | `data/load_aws.py` | NDJSON to S3, S3 to Neptune Bulk Loader, NDJSON to OpenSearch bulk index |
| Real adapters | `data/real/` | 국회 OpenAPI (bill, member, vote, committee, session, party, agency) via shared `_client.py` |
| Synthetic generators | `data/synthetic/` | readers, ads, articles, topics, placeholders, demo seeds |
| External ETL | `data/external/` | Naver News, poll results |

### Storage

| Component | Role |
|---|---|
| Amazon Neptune | openCypher graph; private isolated subnet |
| OpenSearch Serverless | BM25 (Nori) + Cohere KNN, RRF fusion |
| DynamoDB (4 tables) | b2b-keys, ad-inventory, ad-impression, reader-profile |
| S3 (3 buckets) | raw-docs, uploads, synthetic-data |

### Processing / AI

| Component | Location | Role |
|---|---|---|
| Bedrock entrypoint | `api/services/bedrock.py` | Single `invoke()`/`invoke_stream()` for Sonnet 4.6; deterministic demo mock fallback |
| Multi-agent pipeline | `api/services/multi_agent.py` | Scenario B Stage 3: Planner to Graph to Analyst to Editor |
| Stage dispatch | `api/services/three_stage.py` | Chatbot / Agent / Agentic mode branching |
| Guardrails | `api/services/guardrails.py` | political_balance_score computation |
| Scenario builders | `api/services/*_builder.py` | Per-scenario domain logic (cluster, journey, lookalike, etc.) |
| Catalog | `api/services/objects_catalog.py` | 31-class metadata SSOT (Object Explorer + ontology meta) |
| Embeddings / rerank | Cohere embed-v4, rerank-v3 (via Bedrock) | Vector + cross-encoder rerank |
| AgentCore | Memory + Code Interpreter | Session memory + sandboxed charts |

### Query / API

| Component | Location | Role |
|---|---|---|
| FastAPI app | `api/main.py` | 21 routers registered via lazy import |
| API auth | (none in API layer) | Auth enforced at edge; the API trusts upstream (effectively demo-public) |
| boto3 factory | `api/aws_clients.py` | `@lru_cache` session |

### Presentation

| Component | Location | Role |
|---|---|---|
| Next.js 14 app | `web/app/` | 23 scenario pages + members + mindmap + Object Explorer + ops + codegraph (graphify static asset, no backend) |
| API clients | `web/lib/api-client.ts`, `scenario-clients.ts` | Typed SSE + REST, X-Persona-Id auto-attach |
| Sidebar SSOT | `web/components/Sidebar.tsx` | `SCENARIOS` array drives nav, icons, badges |

### Security

| Component | Role |
|---|---|
| Cognito (3 pools) | staff, subscriber, guest identity pool |
| Lambda@Edge | JWT validation, salted guest cookie |
| API Gateway | B2B Usage Plan + API Key (DynamoDB) |
| Bedrock Guardrails | political neutrality (scenarios B, C, I, K) |
| Neutrality rules | no `Reader.political_leaning`; party-neutral naming (ADR-0004) |

### Observability

| Component | Role |
|---|---|
| CloudWatch dashboard | 2 widgets: ECS CPU/Memory, Ad Matcher Lambda invocations/errors |
| Alarms | 2: avg political_balance_score < 0.8, ALB 5xx > 1% |
| Ops console | `api/routers/ops.py` 5 panels (ingest, guardrail, memory, eval, trace) |

## Full Architecture Diagram

```
                                  ┌─────────────────────────┐
                                  │   Browser (6 personas)  │
                                  └────────────┬────────────┘
                                               ▼
                                  ┌─────────────────────────┐
                                  │  CloudFront (B2C / B2B)  │
                                  │  + Lambda@Edge JWT       │
                                  └──────┬───────────┬───────┘
                          (web origin)   ▼           ▼  (B2B api)
                              ┌──────────────┐  ┌──────────────────┐
                              │     ALB      │  │   API Gateway    │
                              └──────┬───────┘  │  Usage Plan+Key  │
                                     ▼          └────────┬─────────┘
                ┌────────────────────────────┐          │
                │   ECS Fargate (ARM64)       │◀─────────┘
                │  ┌────────────┐ ┌─────────┐ │
                │  │ web (Next) │ │ api(FAST)│ │
                │  └────────────┘ └────┬────┘ │
                └──────────────────────┼──────┘
              ┌───────────────┬────────┼────────┬──────────────┐
              ▼               ▼        ▼         ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐
       │  Neptune   │ │ OpenSearch │ │ DDB  │ │  Bedrock │ │AgentCore │
       │ (openCypher)│ │ Serverless │ │ x4   │ │Sonnet 4.6│ │Mem + CI  │
       └────────────┘ └────────────┘ └──────┘ └──────────┘ └──────────┘
              ▲               ▲
              │               │  (one-shot ECS task)
       ┌──────┴───────────────┴──────┐
       │   data/load.py + load_aws   │◀── 국회 OpenAPI / Naver / synthetic
       └─────────────────────────────┘

   CloudWatch (dashboards + alarms) observes all ECS / Neptune / Bedrock metrics.
```

## Data Flow Summary

국회 OpenAPI + synthetic + external → `data/load` → S3 → Neptune Bulk Loader + OpenSearch → FastAPI router → `*_builder` / `bedrock.invoke` (+ Guardrails) → SSE/REST → Next.js page → persona-aware render.

## Infrastructure (CDK Stacks)

| Stack | Key resources |
|---|---|
| `network` | Shared VPC import (`vpc-0dfa5610180dfa628`, 10.100.0.0/16, 2-AZ) + 5 SGs |
| `data` | Neptune cluster, OpenSearch Serverless, 3 S3, 4 DynamoDB |
| `compute` | ECS cluster, ALB, api/web Fargate (ARM64, 2/2), Ad Matcher Lambda |
| `ai` | Bedrock Guardrails, AgentCore Memory store (3 namespaces) |
| `edge` | CloudFront (B2C + B2B), Lambda@Edge, Cognito (3 pools), API Gateway, Route53 |
| `observability` | CloudWatch dashboards, alarms, balance-score metric |

Stack dependency: `network` → `data`/`compute`/`ai`; `data` → `compute`/`ai`; `compute` → `edge`; `observability` subscribes to all.

## Key Design Decisions

- **Shared VPC import** (ADR-0006) — import `vpc-0dfa5610180dfa628` instead of a dedicated VPC; saves NAT GW cost and keeps the 4 ontology projects consistent. Supersedes ADR-0001 D7.
- **Builder-per-scenario** — domain logic lives in `api/services/<scenario>_builder.py`, keeping routers thin and testable.
- **Single Bedrock entrypoint** — all LLM calls pass through `bedrock.py:invoke()`; falls back to a deterministic mock when AWS credentials are absent.
- **Catalog in code** — the 31-class catalog SSOT is `api/services/objects_catalog.py` (the `ontology/` yaml directory is an unpopulated scaffold).
- **Political neutrality as a feature** (ADR-0004) — Guardrails + `political_balance_score` exposed in the UI; inference fields such as `Reader.political_leaning` are never stored.
- **6 personas** (ADR-0002, ADR-0003) — `api/services/persona.py:PERSONA_REGISTRY` is the SSOT for tone, navigation, and ad policy.

## Operations

See `docs/runbooks/01-deployment.md` for the deployment runbook. Recommended additions: database-migration (one-shot ECS loader), incident-response (balance/5xx/Neptune alarms), environment-setup (3 Cognito pools + B2B keys).

---

<a id="korean"></a>

# 한국어

## 시스템 개요

`ontology-for-assembly`는 국회 열린데이터광장 OpenAPI에서 가져온 31-class 도메인 온톨로지 위에서 23개 언론사 Agentic AI 시나리오(A–W)와 6 페르소나를 구동하는 멀티 런타임 모노레포 데모입니다. Python FastAPI 백엔드(21 라우터)와 Next.js 14 프론트엔드가 CloudFront 뒤의 ARM64 Fargate 서비스로 실행되고, Amazon Neptune(openCypher)과 OpenSearch Serverless(하이브리드 BM25 + KNN)가 데이터를, Bedrock Sonnet 4.6과 AgentCore가 에이전트 계층을 담당합니다. 모든 인프라는 공유 VPC를 import하는 6개 스택의 AWS CDK v2로 프로비저닝됩니다(ADR-0006).

## 계층별 컴포넌트

### Ingestion

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| Load CLI | `data/load.py` | argparse 진입점; 일회성 ECS 태스크(`--source`/`--to`/`--neptune`/`--opensearch`) |
| AWS 로더 | `data/load_aws.py` | NDJSON→S3, S3→Neptune Bulk Loader, NDJSON→OpenSearch bulk index |
| Real 어댑터 | `data/real/` | 국회 OpenAPI(bill, member, vote, committee, session, party, agency), 공통 `_client.py` |
| 합성 generator | `data/synthetic/` | 독자, 광고, 기사, 토픽, placeholder, 시연 시드 |
| 외부 ETL | `data/external/` | 네이버 뉴스, 여론조사 |

### Storage

| 컴포넌트 | 역할 |
|---|---|
| Amazon Neptune | openCypher 그래프; private isolated subnet |
| OpenSearch Serverless | BM25(Nori) + Cohere KNN, RRF fusion |
| DynamoDB (4종) | b2b-keys, ad-inventory, ad-impression, reader-profile |
| S3 (3종) | raw-docs, uploads, synthetic-data |

### Processing / AI

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| Bedrock 진입점 | `api/services/bedrock.py` | Sonnet 4.6 단일 `invoke()`/`invoke_stream()`; 결정적 demo mock fallback |
| 멀티 에이전트 | `api/services/multi_agent.py` | 시나리오 B Stage 3: Planner→Graph→Analyst→Editor |
| Stage 분기 | `api/services/three_stage.py` | Chatbot / Agent / Agentic 모드 분기 |
| Guardrails | `api/services/guardrails.py` | political_balance_score 계산 |
| 시나리오 빌더 | `api/services/*_builder.py` | 시나리오별 도메인 로직(cluster, journey, lookalike 등) |
| 카탈로그 | `api/services/objects_catalog.py` | 31-class 메타 SSOT(Object Explorer + 온톨로지 메타) |
| 임베딩 / rerank | Cohere embed-v4, rerank-v3(Bedrock 경유) | 벡터 + cross-encoder rerank |
| AgentCore | Memory + Code Interpreter | 세션 메모리 + 샌드박스 차트 |

### Query / API

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| FastAPI 앱 | `api/main.py` | 21 라우터 lazy import 등록 |
| API 인증 | (API 계층에 없음) | 인증은 edge에서 강제; API는 upstream 신뢰(사실상 demo-public) |
| boto3 factory | `api/aws_clients.py` | `@lru_cache` 세션 |

### Presentation

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| Next.js 14 앱 | `web/app/` | 23 시나리오 페이지 + members + mindmap + Object Explorer + ops + codegraph (graphify 정적 자산, 백엔드 없음) |
| API 클라이언트 | `web/lib/api-client.ts`, `scenario-clients.ts` | 타입드 SSE + REST, X-Persona-Id 자동 첨부 |
| Sidebar SSOT | `web/components/Sidebar.tsx` | `SCENARIOS` 배열이 내비·아이콘·배지 구동 |

### Security

| 컴포넌트 | 역할 |
|---|---|
| Cognito (3 pool) | staff, subscriber, guest identity pool |
| Lambda@Edge | JWT 검증, 솔티드 게스트 쿠키 |
| API Gateway | B2B Usage Plan + API Key(DynamoDB) |
| Bedrock Guardrails | 정치 중립성(시나리오 B, C, I, K) |
| 중립성 규칙 | `Reader.political_leaning` 미저장; 정당명 중립 표기(ADR-0004) |

### Observability

| 컴포넌트 | 역할 |
|---|---|
| CloudWatch 대시보드 | 위젯 2종: ECS CPU/Memory, Ad Matcher Lambda invocations/errors |
| 알람 | 2종: 평균 political_balance_score < 0.8, ALB 5xx > 1% |
| 운영 콘솔 | `api/routers/ops.py` 5 패널(ingest, guardrail, memory, eval, trace) |

## 전체 아키텍처 다이어그램

```
                                  ┌─────────────────────────┐
                                  │   Browser (6 personas)  │
                                  └────────────┬────────────┘
                                               ▼
                                  ┌─────────────────────────┐
                                  │  CloudFront (B2C / B2B)  │
                                  │  + Lambda@Edge JWT       │
                                  └──────┬───────────┬───────┘
                          (web origin)   ▼           ▼  (B2B api)
                              ┌──────────────┐  ┌──────────────────┐
                              │     ALB      │  │   API Gateway    │
                              └──────┬───────┘  │  Usage Plan+Key  │
                                     ▼          └────────┬─────────┘
                ┌────────────────────────────┐          │
                │   ECS Fargate (ARM64)       │◀─────────┘
                │  ┌────────────┐ ┌─────────┐ │
                │  │ web (Next) │ │ api(FAST)│ │
                │  └────────────┘ └────┬────┘ │
                └──────────────────────┼──────┘
              ┌───────────────┬────────┼────────┬──────────────┐
              ▼               ▼        ▼         ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐
       │  Neptune   │ │ OpenSearch │ │ DDB  │ │  Bedrock │ │AgentCore │
       │ (openCypher)│ │ Serverless │ │ x4   │ │Sonnet 4.6│ │Mem + CI  │
       └────────────┘ └────────────┘ └──────┘ └──────────┘ └──────────┘
              ▲               ▲
              │               │  (일회성 ECS 태스크)
       ┌──────┴───────────────┴──────┐
       │   data/load.py + load_aws   │◀── 국회 OpenAPI / 네이버 / synthetic
       └─────────────────────────────┘

   CloudWatch(대시보드 + 알람)가 모든 ECS / Neptune / Bedrock 메트릭을 관측.
```

## 데이터 흐름 요약

국회 OpenAPI + synthetic + external → `data/load` → S3 → Neptune Bulk Loader + OpenSearch → FastAPI 라우터 → `*_builder` / `bedrock.invoke` (+ Guardrails) → SSE/REST → Next.js 페이지 → 페르소나 인지 렌더링.

## 인프라 (CDK 스택)

| 스택 | 주요 리소스 |
|---|---|
| `network` | 공유 VPC import(`vpc-0dfa5610180dfa628`, 10.100.0.0/16, 2-AZ) + SG 5개 |
| `data` | Neptune cluster, OpenSearch Serverless, S3 3종, DynamoDB 4종 |
| `compute` | ECS cluster, ALB, api/web Fargate(ARM64, 2/2), Ad Matcher Lambda |
| `ai` | Bedrock Guardrails, AgentCore Memory store(3 namespace) |
| `edge` | CloudFront(B2C + B2B), Lambda@Edge, Cognito(3 pool), API Gateway, Route53 |
| `observability` | CloudWatch 대시보드, 알람, balance-score 메트릭 |

스택 의존: `network` → `data`/`compute`/`ai`; `data` → `compute`/`ai`; `compute` → `edge`; `observability`는 전체 구독.

## 핵심 설계 결정

- **공유 VPC import** (ADR-0006) — 전용 VPC 대신 `vpc-0dfa5610180dfa628` import. NAT GW 비용 절감 + 4개 온톨로지 프로젝트 일관성. ADR-0001 D7 supersede.
- **시나리오별 빌더** — 도메인 로직을 `api/services/<scenario>_builder.py`에 분리, 라우터는 얇게 유지하고 테스트 용이.
- **단일 Bedrock 진입점** — 모든 LLM 호출이 `bedrock.py:invoke()` 경유; AWS 자격증명 없으면 결정적 mock으로 fallback.
- **카탈로그 in code** — 31-class 카탈로그 SSOT는 `api/services/objects_catalog.py`(`ontology/` yaml 디렉토리는 미채움 스캐폴드).
- **정치 중립성을 기능으로** (ADR-0004) — Guardrails + `political_balance_score`를 UI 노출; `Reader.political_leaning` 등 추론 필드는 미저장.
- **6 페르소나** (ADR-0002, ADR-0003) — `api/services/persona.py:PERSONA_REGISTRY`가 어조·내비·광고 정책 SSOT.

## 운영

배포 런북은 `docs/runbooks/01-deployment.md` 참조. 추가 권장 런북: database-migration(일회성 ECS 로더), incident-response(balance/5xx/Neptune 알람), environment-setup(3 Cognito pool + B2B key).
