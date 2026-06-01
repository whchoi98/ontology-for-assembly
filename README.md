# ontology-for-assembly

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![English](https://img.shields.io/badge/lang-English-blue.svg)](#english)
[![한국어](https://img.shields.io/badge/lang-한국어-red.svg)](#한국어)

A 30–60 minute proof-of-concept demo for a Korean newsroom Agentic AI knowledge graph on AWS Bedrock + AgentCore + Neptune — powered by 국회 열린데이터광장 OpenAPI · 23 wow scenarios (A–W) · 31 ontology classes · 6 personas (3 internal + 3 customer-facing) · real + synthetic + external data.

AWS Bedrock + AgentCore + Neptune 위에서 **한국 언론사 Agentic 온톨로지**가 23개 wow 시나리오와 6개 페르소나(편집국·데이터·AI·광고/세일즈·일반 독자·유료 구독자·기업/B2B 정책 인텔리전스)를 통해 어떻게 *3-단계 진화 비교(Chatbot→Agent→Agentic AI)* 와 *AI 거버넌스 광고 매칭*을 시연하는지 보여주는 30–60분 PoC 데모.

차용 베이스: [`ontology-for-gcc`](https://github.com/whchoi98/ontology-for-gcc) (plan1-foundation) — 디렉토리·6-stack CDK·하니스 100% 차용, 도메인만 국회/언론으로 교체.

---

# English

## Overview

`ontology-for-assembly` is a hands-on demonstration of how a 31-class domain ontology (legislators, bills, votes, committees, statements, parties, agencies, readers, advertisements, etc.) can power **23 distinct** Agentic AI scenarios for a Korean newsroom on AWS managed AI services. The demo deploys a multi-tier application — FastAPI backend, Next.js 14 frontend, AWS CDK infrastructure (6 stacks) — that integrates Bedrock Sonnet 4.6, AgentCore Memory and Code Interpreter, Neptune openCypher, OpenSearch Serverless hybrid search, and CloudFront-fronted ECS Fargate (Graviton ARM64).

Scenarios span semantic search, conversational reporter/reader agent with multi-turn memory, MD-grade insights with streaming token summaries, persona matching, legislator clustering, lookalike expansion, article ROI/CTR simulation, district map, neutrality guardrails, external signal fusion, vote-pattern outlier detection, **ad-match governance (keyword vs embedding vs Agent-judgment)**, full legislator journey timeline, and issue-vs-legislation correlation (A–N) — plus person-relationship analysis, petition-to-legislation, committee influence heatmap, promise tracking, topic burst, party cohesion, influence ranking, voting clusters, and swing-voter detection (O–W).

**Personas (6)**: editorial · data·AI · ad/sales (3 internal) + general reader · paid subscriber · B2B policy intelligence (3 customer-facing).

**Data cohorts**: real (assembly OpenAPI) + synthetic (readers, ads, articles) + external (Naver News RSS, SNS, polls). Each node is tagged with `source ∈ {real, synthetic, external}` for provenance badges.

## Features

See `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` for the authoritative scope. Highlights:

- **Semantic Search (A)** — Korean natural-language queries through OpenSearch BM25 (Nori) + Cohere KNN hybrid, fused with reciprocal-rank fusion, then reranked with `cohere.rerank-v3`.
- **Three-stage chatbot comparison (B)** — Side-by-side Chatbot (RAG) vs Agent (Tool Use) vs Agentic AI (multi-agent: Planner / Graph / Analyst / Editor).
- **Article Insights (C)** — Sonnet 4.6 streaming Korean summary plus AgentCore Code Interpreter rendering matplotlib charts with NanumGothic Korean glyphs.
- **Persona Match (D)** — 6 personas (editorial / data·AI / ad·sales / general reader / paid subscriber / B2B) with weighted KPI scoring.
- **Legislator Clustering (E)** — sklearn KMeans with LLM-driven cluster labels (politically neutral abstractions).
- **Lookalike Expansion (F)** — Cohere embed-v4 seed + OpenSearch KNN top-X% similarity.
- **Article ROI Simulator (G)** — Bayesian engagement estimate plus Code Interpreter distribution chart.
- **District Map (H)** — Korean sido choropleth + 17 시도 GeoJSON + legislator distribution.
- **Neutrality Lens (I)** — Bedrock Guardrails + political balance score + bias detector.
- **External Signal Fusion (J)** — Naver news + SNS + polls cross-source narrative.
- **Vote-pattern Outlier (K)** — pandas window detection (party-line break, swing votes) with LLM pattern labeling. PDF 3-page signature.
- **Ad-match Matrix (L)** — keyword × embedding × Agent-judgment 3-way comparison. Agent skips ads on tragedy/scandal/minor-victim contexts. PDF 3-page signature.
- **Legislator Journey Timeline (M)** — proposals + votes + statements + committee membership unified timeline.
- **Issue × Legislation Correlation (N)** — topic trend ↔ bill proposal scatter plot.

Expansion scenarios (O–W):

- **Person Relationship (O)** — graph path between two figures (`/api/relations/{a}/{b}`).
- **Petition → Legislation (P)**, **Committee Influence Heatmap (Q)**, **Promise Tracker (R)**, **Topic Burst (S)** — frontend pages backed by member directory data + the generic `/api/insight` LLM narrative.
- **Party Cohesion (T)**, **Influence Ranking (U)**, **Voting Cluster (V)**, **Swing Voter (W)** — Phase 4f advanced insights over real Neptune edges (`/api/insights/*`).

Plus: **31-class object explorer** (search · pagination · 1-hop subgraph), **ontology mindmap** (1–3 hop relations graph), **member directory** (286 members · 9 metrics), **operational console** (5 panels — ingest · guardrail · memory · eval · trace), and **GuidedTour** (6 personas × scenario recommendation cards).

## Prerequisites

- AWS account with Bedrock, Neptune, OpenSearch Serverless, and AgentCore enabled in `ap-northeast-2`
- AWS CLI v2 with credentials (SSO or IAM)
- Node.js 20 or later
- Python 3.12 or later
- Docker with `linux/arm64` build support (Graviton ECS targets)
- AWS CDK v2.150 or later
- 국회 OpenAPI key (https://open.assembly.go.kr 회원가입 → 활용신청)

## Installation

```bash
# Clone
git clone https://github.com/whchoi98/ontology-for-assembly.git
cd ontology-for-assembly

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd web && npm ci && cd -

# Infrastructure
cd infra-cdk && npm ci && cd -

# Bootstrap CDK + deploy all 6 stacks
cd infra-cdk
npx cdk bootstrap aws://<account>/ap-northeast-2
npx cdk deploy --all
```

## Configuration

See [.env.example](.env.example) for the full list of environment variables. Highlights:

| Variable | Description |
|----------|-------------|
| `AWS_REGION` | `ap-northeast-2` |
| `BEDROCK_CHAT_MODEL_ID` | `global.anthropic.claude-sonnet-4-6` (default) |
| `BEDROCK_EMBED_MODEL_ID` | `global.cohere.embed-v4:0` |
| `BEDROCK_GUARDRAIL_ID` | political neutrality guardrail (ADR-0004) |
| `ASSEMBLY_OPENAPI_KEY` | 국회 OpenAPI key |
| `AD_MATCH_MODE` | `keyword \| embedding \| agent` (Scenario L 3-way toggle) |
| `DEMO_PUBLIC_MODE` | `false` in production. `true` only for live demo bypass |

## Project Structure

```
ontology-for-assembly/
├── api/                 FastAPI backend (Python 3.12, ARM64)
├── web/                 Next.js 14 frontend (TypeScript, ARM64)
├── infra-cdk/           AWS CDK v2 — 6 stacks
├── data/                Real + synthetic + external data adapters
├── ontology/            Catalog scaffold (live catalog in api/services/objects_catalog.py)
├── tests/               pytest smoke + per-router httpx integration
├── docs/                architecture, ADRs, runbooks, design spec
├── scripts/             wow-query eval, Cognito provisioning
├── .claude/             Project harness
└── .harness-eval/       Score history
```

## Testing

```bash
make test-fast              # Python AST + smoke (<1s)
make test                   # full pytest
make type-check             # tsc (web + infra-cdk) + mypy
make cdk-test               # CDK 6-stack snapshot
make wow-eval               # 84 cases — A–N core scenarios × 6 personas (deployed CF)
```

CI runs the first four on every push/PR via `.github/workflows/ci.yml`.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/<scenario-or-fix>`
3. Follow conventions in [CLAUDE.md](CLAUDE.md). Use Conventional Commits (`feat(api): add ad matcher`, `fix(infra-cdk): correct Cognito callback`).
4. Push and open a Pull Request

## License

MIT — see [LICENSE](LICENSE).

## Contact

- Maintainer: [whchoi98](https://github.com/whchoi98)
- Issues: <https://github.com/whchoi98/ontology-for-assembly/issues>
- Email: whchoi98@gmail.com

---

# 한국어

## 개요

`ontology-for-assembly`는 31-class 도메인 온톨로지(의원, 의안, 표결, 위원회, 발언, 정당, 기관, 독자, 광고 등)가 AWS 매니지드 AI 서비스 위에서 한국 언론사를 위한 **23개** Agentic AI 시나리오를 어떻게 구동하는지 보여주는 실습형 데모입니다. FastAPI 백엔드, Next.js 14 프론트엔드, AWS CDK 인프라(6 stacks)로 구성된 다층 애플리케이션이 Bedrock Sonnet 4.6, AgentCore Memory와 Code Interpreter, Neptune openCypher, OpenSearch Serverless 하이브리드 검색, CloudFront 앞단에 ECS Fargate(Graviton ARM64)를 통합합니다.

시나리오는 의미 검색, 다회차 메모리 기반 대화형 기자/독자 에이전트, 토큰 스트리밍 요약 기사 인사이트, 페르소나 매칭, 의원 클러스터링, 룩어라이크 확장, 기사 ROI/CTR 시뮬레이션, 지역구 지도, 정치 중립성 가드레일, 외부 신호 융합, 표결 패턴 변화 탐지, **광고 매칭 거버넌스(키워드·임베딩·Agent 판단 3-way)**, 의원 정치 여정 timeline, 사회 이슈 × 입법 상관(A–N) — 여기에 인물 관계 분석, 청원→입법, 위원회 영향력 heatmap, 공약 이행 추적, 토픽 burst, 정당 응집도, 의원 영향력 랭킹, 표결 cluster, swing voter 탐지(O–W)를 더해 총 23개에 걸쳐 있습니다.

**페르소나 (6개)**: 편집국 · 데이터·AI · 광고/세일즈 (내부 3) + 일반 독자 · 유료 구독자 · 기업/B2B 정책 인텔리전스 (대고객 3).

**데이터 cohort**: real (국회 OpenAPI) + synthetic (독자·광고·기사 합성) + external (네이버 뉴스 RSS·SNS·여론조사). 각 노드에 `source ∈ {real, synthetic, external}` 태깅하여 출처 배지 노출.

## 핵심 시연 메시지

1. **3단계 진화 비교** (시나리오 B) — Chatbot(RAG) → Agent(Tool Use) → Agentic AI(Planner·Graph·Analyst·Editor 4 에이전트 협업)를 한 화면 비교.
2. **AI 거버넌스 광고 매칭** (시나리오 L) — 키워드 · 임베딩 · Agent 판단 3-way. 정치 민감 콘텐츠에서 Agent가 "광고 노출 생략"을 자동 판단하는 reasoning trace 라이브 시연.
3. **B2C·B2B 동시 시연** — 6 페르소나가 같은 데이터를 자신의 KPI/관심사로 본다.

## 주요 기능

자세한 사항은 `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` 참조.

- **의미 검색 (A)** — 의안·의원 한국어 자연어 쿼리 → BM25(Nori) + Cohere KNN + RRF + rerank-v3 → 1-hop 지식그래프 시각화.
- **3단계 챗봇 (B)** — Chatbot/Agent/Agentic AI 사이드바이사이드 비교.
- **기사 인사이트 (C)** — Sonnet 4.6 스트리밍 + Code Interpreter NanumGothic 한글 차트.
- **페르소나 매칭 (D)** — 6 페르소나 KPI 가중치 그래프 워크.
- **의원 클러스터링 (E)** — KMeans + LLM 라벨 (정치 중립 추상 라벨).
- **룩어라이크 (F)** — Cohere embed-v4 + OpenSearch KNN top-X%.
- **기사 ROI 시뮬 (G)** — Bayesian 추정 + Code Interpreter 분포 차트.
- **지역구 지도 (H)** — 17 시도 choropleth + 의원 분포.
- **편향·중립성 (I)** — Bedrock Guardrails + political balance score + bias detector.
- **외부 신호 융합 (J)** — 네이버 뉴스 + SNS + 여론조사 cross-source.
- **표결 이상치 (K)** — pandas 윈도 + LLM 패턴 라벨 (PDF 3페이지 시그니처).
- **광고 매칭 매트릭스 (L)** — 키워드·임베딩·Agent 3-way + Agent 광고 생략 판단 (PDF 3페이지 시그니처).
- **의원 정치 여정 (M)** — 발의·표결·발언·위원회 통합 timeline.
- **이슈 × 입법 상관 (N)** — 토픽 트렌드 ↔ 법안 발의 산점도.

확장 시나리오 (O–W):

- **인물 관계 (O)** — 두 인물 간 그래프 경로 (`/api/relations/{a}/{b}`).
- **청원→입법 (P)**, **위원회 영향력 heatmap (Q)**, **공약 이행 추적 (R)**, **토픽 burst (S)** — 의원 디렉토리 데이터 + 범용 `/api/insight` LLM narrative 기반 프론트 페이지.
- **정당 응집도 (T)**, **의원 영향력 랭킹 (U)**, **표결 cluster (V)**, **swing voter (W)** — Phase 4f 고급 인사이트, real Neptune edges Cypher (`/api/insights/*`).

추가: **31-class 객체 탐색기**, **온톨로지 관계 그래프**(1–3 hop), **의원 디렉토리**(286명·9 지표), **운영 콘솔** (5 패널), **GuidedTour** (6 페르소나 × 시나리오 추천).

## 사전 요구 사항

- `ap-northeast-2`에서 Bedrock, Neptune, OpenSearch Serverless, AgentCore 활성화된 AWS 계정
- AWS CLI v2 (SSO 또는 IAM)
- Node.js 20+, Python 3.12+, Docker linux/arm64, AWS CDK v2.150+
- 국회 OpenAPI key (https://open.assembly.go.kr)

## 설치

```bash
git clone https://github.com/whchoi98/ontology-for-assembly.git
cd ontology-for-assembly

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web && npm ci && cd -
cd infra-cdk && npm ci && cd -

cd infra-cdk
npx cdk bootstrap aws://<account>/ap-northeast-2
npx cdk deploy --all
```

## 환경 변수

`.env.example` 참조. 주요 변수: `AWS_REGION`, `BEDROCK_CHAT_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`, `ASSEMBLY_OPENAPI_KEY`, `AD_MATCH_MODE`, `DEMO_PUBLIC_MODE`.

## 프로젝트 구조

```
ontology-for-assembly/
├── api/                 FastAPI 백엔드 (Python 3.12, ARM64)
├── web/                 Next.js 14 프론트엔드 (TS, ARM64)
├── infra-cdk/           AWS CDK v2 — 6 stacks
├── data/                실/합성/외부 데이터 어댑터
├── ontology/            카탈로그 스캐폴드 (실 카탈로그는 api/services/objects_catalog.py)
├── tests/               pytest smoke + 라우터별 httpx 통합
├── docs/                architecture, ADRs, runbooks, design spec
├── scripts/             wow-query 평가, Cognito 프로비저닝
├── .claude/             프로젝트 하니스
└── .harness-eval/       점수 history → README 배지
```

## 테스트

```bash
make test-fast              # AST + smoke (<1초)
make test                   # 전체 pytest
make type-check             # tsc + mypy
make cdk-test               # CDK 스냅샷
make wow-eval               # 84 케이스 — A–N 핵심 시나리오 × 6 페르소나 (배포된 CF)
```

CI는 push/PR마다 위 첫 4개를 `.github/workflows/ci.yml`로 실행.

## 정치 중립성 (Critical)

PoC 도메인 특성상 다음 안전장치를 항상 적용합니다:
- Bedrock Guardrails (시나리오 B·C·I·K 입력·출력)
- 사전 검증된 시연 질문 풀만 라이브 사용 (`scripts/eval_wow_queries.py`)
- `Reader.political_leaning` 등 정치 성향 추론 필드 저장 금지
- 광고 매칭에서 비극·정치인 비위·미성년 피해자 콘텐츠 자동 생략

자세한 내용은 [SECURITY.md](SECURITY.md) 참조.

## 기여

1. 저장소를 Fork
2. 기능 브랜치: `git checkout -b feat/<scenario-or-fix>`
3. [CLAUDE.md](CLAUDE.md) 컨벤션 준수. Conventional Commits (`feat(api): 광고 매처 추가`, `fix(infra-cdk): Cognito 콜백 수정`).
4. Push 후 PR 생성

## 라이선스

MIT — [LICENSE](LICENSE) 참조.

## 연락처

- 메인테이너: [whchoi98](https://github.com/whchoi98)
- 이슈: <https://github.com/whchoi98/ontology-for-assembly/issues>
- 이메일: whchoi98@gmail.com

<!-- harness-eval-badge:start -->
![wow-eval Pass Rate](https://img.shields.io/badge/wow--eval-100%25-brightgreen)
![Avg Balance Score](https://img.shields.io/badge/avg--balance-0.98-brightgreen)
![Active Cases](https://img.shields.io/badge/active--cases-84%2F84-brightgreen)
![Last Eval](https://img.shields.io/badge/eval-2026--05--14-blue)
<!-- harness-eval-badge:end -->

## harness-eval 자동 평가

```bash
# 84 케이스 평가 (6 페르소나 × A–N 14 핵심 시나리오)
python scripts/eval_wow_queries.py

# 운영 콘솔에서 결과 보기
curl http://localhost:8080/api/ops/wow-quality
```

현재: **84 active / 100% PASS / avg balance 0.98** (wow-eval은 핵심 14 시나리오 A–N × 6 페르소나 기준; 앱 자체는 23 시나리오 A–W 구현).
