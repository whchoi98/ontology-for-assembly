# Onboarding

<a href="#english"><img src="https://img.shields.io/badge/lang-English-blue.svg" alt="English"></a>
<a href="#korean"><img src="https://img.shields.io/badge/lang-한국어-red.svg" alt="Korean"></a>

---

<a id="english"></a>

# English

A guide for new developers getting productive on `ontology-for-assembly`. For full context read [CLAUDE.md](../CLAUDE.md), the per-module `CLAUDE.md` files, and [architecture.md](architecture.md).

## Prerequisites

- Python 3.12 (the codebase targets 3.12; note that 3.9 surfaces FastAPI deprecation warnings)
- Node.js 20 or later
- Docker with `linux/arm64` build support (Graviton ECS targets)
- AWS CDK v2.150 or later
- AWS CLI v2 with credentials (only needed for live AWS calls; offline dev runs on deterministic mocks)
- 국회 OpenAPI key (https://open.assembly.go.kr) — only for real-data ingestion

## Local Setup

```bash
git clone https://github.com/whchoi98/ontology-for-assembly.git
cd ontology-for-assembly

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Frontend
cd web && npm ci && cd -

# Infrastructure (TypeScript)
cd infra-cdk && npm ci && cd -
```

## Run Offline

The backend falls back to deterministic mocks when AWS credentials are absent, so most scenarios work without any cloud resources.

```bash
# API (FastAPI)
uvicorn api.main:create_app --factory --reload --port 8080

# Web (Next.js) in a second shell
cd web && npm run dev
```

`DEMO_PUBLIC_MODE=true` (set in `tests/conftest.py` and recommended for local dev) bypasses Cognito/B2B auth.

## Verify

```bash
make ast          # Python compile check
make test         # full pytest
make type-check   # tsc (web + infra-cdk) + mypy
make cdk-test     # CDK 6-stack Jest snapshot
make wow-eval     # 84 cases — A–N core scenarios x 6 personas (deployed CF)
```

Known state: `make test` currently shows 41 failures. `test_lookalike_router` (15) is from the in-progress migration of synthetic `MONA_001` seeds to real National Assembly data (fixtures not yet updated). `test_objects_router` (1, `limit` validation) and `test_real_adapters` (1, error-handling) are separate, unrelated failures; the rest are in the same real-data/objects area.

## Key Concepts

- **23 scenarios (A–W)** — `web/components/Sidebar.tsx:SCENARIOS` is the SSOT. Not all map 1:1 to routers (P/Q/R/S reuse `members.py` + generic `insight_generic.py`).
- **6 personas** — `api/services/persona.py:PERSONA_REGISTRY` drives tone, navigation, and ad policy.
- **31-class ontology** — catalog SSOT is `api/services/objects_catalog.py`; Pydantic SSOT is `data/schemas.py`.
- **Political neutrality** — Guardrails + `political_balance_score`; never store inference fields like `Reader.political_leaning` (ADR-0004).
- **Single LLM entrypoint** — all Bedrock calls go through `api/services/bedrock.py:invoke()`.

## Where to Look

| Task | Start here |
|---|---|
| Add a scenario | `CLAUDE.md` Auto-Sync Rules + `web/components/Sidebar.tsx` |
| Add a class | `api/services/objects_catalog.py` + `data/schemas.py` |
| Change scenario B agents | `api/services/multi_agent.py` |
| Infra change | `infra-cdk/lib/*-stack.ts` + `infra-cdk/CLAUDE.md` |
| API contract | `docs/api-reference.md` |
| Architecture decisions | `docs/decisions/` (ADR 0001–0010) |

---

<a id="korean"></a>

# 한국어

`ontology-for-assembly`에 처음 합류한 개발자를 위한 안내입니다. 전체 맥락은 [CLAUDE.md](../CLAUDE.md), 모듈별 `CLAUDE.md`, [architecture.md](architecture.md)를 참고합니다.

## 사전 요구 사항

- Python 3.12 (코드베이스는 3.12 기준이며, 3.9에서는 FastAPI deprecation 경고가 나타납니다)
- Node.js 20 이상
- `linux/arm64` 빌드를 지원하는 Docker (Graviton ECS 타겟)
- AWS CDK v2.150 이상
- AWS CLI v2 자격증명 (라이브 AWS 호출 시에만 필요; 오프라인 개발은 결정적 mock으로 동작)
- 국회 OpenAPI key (https://open.assembly.go.kr) — real 데이터 적재 시에만 필요

## 로컬 설정

```bash
git clone https://github.com/whchoi98/ontology-for-assembly.git
cd ontology-for-assembly

# 백엔드
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 프론트엔드
cd web && npm ci && cd -

# 인프라 (TypeScript)
cd infra-cdk && npm ci && cd -
```

## 오프라인 실행

백엔드는 AWS 자격증명이 없으면 결정적 mock으로 fallback하므로 대부분의 시나리오가 클라우드 리소스 없이 동작합니다.

```bash
# API (FastAPI)
uvicorn api.main:create_app --factory --reload --port 8080

# Web (Next.js) - 두 번째 셸에서
cd web && npm run dev
```

`DEMO_PUBLIC_MODE=true` (`tests/conftest.py`에 설정, 로컬 개발 권장)는 Cognito/B2B 인증을 우회합니다.

## 검증

```bash
make ast          # Python 컴파일 체크
make test         # 전체 pytest
make type-check   # tsc (web + infra-cdk) + mypy
make cdk-test     # CDK 6-stack Jest 스냅샷
make wow-eval     # 84 케이스 — A–N 핵심 시나리오 x 6 페르소나 (배포된 CF)
```

알려진 상태: `make test`에서 현재 41개 실패. `test_lookalike_router`(15)는 합성 `MONA_001` seed를 실 국회 데이터로 이전하는 진행 중 작업 때문입니다(픽스처 미갱신). `test_objects_router`(1, `limit` 검증)와 `test_real_adapters`(1, 에러 처리)는 별개의 무관한 실패이며, 나머지는 동일한 real-data/objects 영역입니다.

## 핵심 개념

- **23 시나리오 (A–W)** — `web/components/Sidebar.tsx:SCENARIOS`가 SSOT. 라우터와 1:1이 아님(P/Q/R/S는 `members.py` + 범용 `insight_generic.py` 재사용).
- **6 페르소나** — `api/services/persona.py:PERSONA_REGISTRY`가 어조·내비·광고 정책 구동.
- **31-class 온톨로지** — 카탈로그 SSOT는 `api/services/objects_catalog.py`, Pydantic SSOT는 `data/schemas.py`.
- **정치 중립성** — Guardrails + `political_balance_score`; `Reader.political_leaning` 등 추론 필드 미저장(ADR-0004).
- **단일 LLM 진입점** — 모든 Bedrock 호출은 `api/services/bedrock.py:invoke()` 경유.

## 어디를 볼까

| 작업 | 시작점 |
|---|---|
| 시나리오 추가 | `CLAUDE.md` Auto-Sync Rules + `web/components/Sidebar.tsx` |
| 클래스 추가 | `api/services/objects_catalog.py` + `data/schemas.py` |
| 시나리오 B 에이전트 변경 | `api/services/multi_agent.py` |
| 인프라 변경 | `infra-cdk/lib/*-stack.ts` + `infra-cdk/CLAUDE.md` |
| API 계약 | `docs/api-reference.md` |
| 아키텍처 결정 | `docs/decisions/` (ADR 0001–0010) |
