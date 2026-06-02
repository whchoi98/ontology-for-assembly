# 데이터 참조 매트릭스 — ontology-for-assembly PoC

**문서 목적**: 23 시나리오(A–N 14 base + O–S 5 확장 + T–W 4 고급 = 14+5+4)의 데이터 출처·적재 경로·real/synthetic/external 라벨 매핑을 한 곳에 정리.

**관련 문서**:
- ADR-0004 (정치 중립성 가드레일)
- ADR-0010 (real data 어댑터 매핑)
- `CLAUDE.md` (프로젝트 메모리)

> **시연 데이터는 3 계층**으로 구성:
> - **real OpenAPI** (국회 공공 데이터)
> - **synthetic** (deterministic SHA256 seed로 결정적 생성)
> - **external** (외부 신호 — 네이버 뉴스·여론조사·SNS)
>
> 각 시나리오는 두세 계층을 혼합하며, 모든 응답은 `source` 필드로 라벨링됩니다.
> 정치 중립성 가드(ADR-0004)는 *real + 합성 모두*에 적용.

---

## 1. Real 데이터 (국회 공공 OpenAPI)

| 데이터 | OpenAPI Endpoint | 적재 양 | 활용 시나리오 |
|---|---|---:|---|
| **의원 명부 (Person)** | `nwvrqwxyaytdsfvhu` (22대) | **286명** | A·B·F·M·O·U·H·전 시나리오 |
| **의안 (Bill)** | `nzmimeepazxkubdpn` ("ALLBILL") | **2,098건** | A·B·C·K·M·O·F·N |
| **표결 정보** | `nojepdqqaweusdfbi` (22대, AGE+BILL_ID 필수) | **28,528개 VOTED 엣지** | I·K·T·W·V |
| **공동발의 cohort** | derive from PROPOSED + Bill `co_proposer_ids` | **19,191개 CO_PROPOSED_WITH 엣지** | F·O·U |
| **위원회 멤버십** | OpenAPI 의원 `CMIT_NM` 필드 | 286명 × 1-3 위원회 = MEMBER_OF 엣지 | O·Q·H |

### 적재 경로

```
National Assembly OpenAPI
    ↓ data/real/ 어댑터 (_client·bill·member·vote·committee·session·party·agency)
S3 (assembly-dev-synthetic-data)
    ↓ ECS one-shot task: python -m data.load --source all --to s3 --bucket <bucket> --neptune --opensearch
Neptune (graph)  +  OpenSearch (text/vector)
```

### Neptune 적재 결과 (Phase 4e 누적)

- **74,249개 real edges**: PROPOSED · CO_PROPOSED · CO_PROPOSED_WITH · VOTED · MEMBER_OF · BELONGS_TO · ASSIGNED_TO
- **2-flag 통제**:
  - `DEMO_PUBLIC_MODE=true` → Bedrock fixture 유지 (LLM 응답은 mock)
  - `ENABLE_NEPTUNE_REAL=true` → Neptune real Cypher query 활성화

---

## 2. Synthetic 데이터 (결정적 합성)

| 데이터 | 생성 로직 | 결정적 seed | 용도 |
|---|---|---|---|
| **의원 활동 메트릭** | `_synth_analytics()` | `SHA256(assembly_id)[:8]` | 출석률·발의·발언·정당 일치율·composite_score |
| **합성 기사 풀** | `data/synthetic/article.py` | 페르소나·토픽 cross-tab | C·G·D |
| **합성 광고 (AdInventory)** | `data/synthetic/advertisement.py` | 광고주 cohort 시드 | L (광고 매칭 3-way) |
| **합성 독자 (Reader)** | `data/synthetic/reader.py` | persona_id 결정적 | D·H·L |
| **17 시도 응집도 분포** | `_PARTY_DISTRIBUTION` dict | 공식 22대 결과 근사 | H choropleth (member_count, parties) |
| **AI 인사이트 fixture** | `bedrock.py:_mock_response` | 시나리오 label + persona_id 매핑 | 전 시나리오 (DEMO_PUBLIC_MODE=true) |

### 합성 데이터 윤리적 안전장치

- **`Reader.political_leaning` 등 정치 성향 추론 필드 절대 생성·저장 금지** (SECURITY.md §3)
- 모든 합성 응답은 `data_source: "synthetic"` 라벨 강제 (ADR-0004)

---

## 3. External 신호 (외부 source)

| 데이터 | Source | 적용 시나리오 |
|---|---|---|
| **네이버 뉴스 RSS** | news.naver.com (30일 rolling window) | J·N·S |
| **여론조사** | 리얼미터 (realmeter.net) · NBS (nbsi.kr) | J·N (lag/lead cross-correlation) |
| **SNS 발화량** | 카카오톡·X (mock layer) | J (외부 신호 cross-correlation) |
| **17 시도 GeoJSON** | KOSTAT (sgis.kostat.go.kr) — 행정구역 코드 | H (choropleth) |
| **의원 사진** | `assembly.go.kr/static/portal/img/openassm/{id}.jpg` | 전 시나리오 (Person 노드) |
| **위키피디아 의원 사진 캐시** | `data/real/members_22_photos.json` (build-time prefetch) | M·F·D·O fallback |

---

## 4. 시나리오별 데이터 매핑

| 시나리오 | Real (Neptune) | Synthetic | External | Real % |
|---|:--:|:--:|:--:|:--:|
| **A 의미 검색** | ✓ Bill 2,098 | — | — | **100%** |
| B 챗봇 (3-stage) | Stage 2/3 시 호출 | Stage 1 RAG fixture | — | hybrid |
| C 기사 인사이트 | — | ✓ 기사 풀 | — | 0% |
| D 페르소나 매칭 | Person | ✓ 기사 cohort | — | hybrid |
| E 의원 클러스터링 | Person + 표결 | ✓ 클러스터 라벨 | — | hybrid |
| **F 룩어라이크** | ✓ CO_PROPOSED_WITH | — | — | **100%** |
| G 기사 ROI | — | ✓ Bayesian seed | — | 0% |
| H 지역구 지도 | Person × district | ✓ 정당 분포 | ✓ KOSTAT | hybrid |
| I 편향·중립성 | 표결 | ✓ bias score | — | hybrid |
| J 외부 신호 | — | — | ✓ 네이버·SNS·여론 | external |
| **K 표결 이상치** | ✓ VOTED + BELONGS_TO | — | — | **100%** |
| L 광고 매칭 | — | ✓ AdInventory | — | 0% |
| **M 의원 정치 여정** | ✓ PROPOSED+VOTED | — | — | **100%** |
| N 이슈 × 입법 | Bill·Topic | ✓ 시계열 seed | ✓ 외부 신호 | hybrid |
| **O 인물 관계** | ✓ CO_PROPOSED_WITH + VOTED + MEMBER_OF | — | — | **100%** |
| **T 정당 응집도** | ✓ VOTED + BELONGS_TO | — | — | **100%** |
| **U 의원 영향력** | ✓ CO_PROPOSED_WITH + PROPOSED | — | — | **100%** |
| **V 표결 cluster** | ✓ VOTED + BELONGS_TO | — | — | **100%** |
| **W Swing voter** | ✓ VOTED + BELONGS_TO | — | — | **100%** |

> **Real 100% 시나리오: A · F · K · M · O · T · U · V · W (9개)** — Phase 4e/4f 누적 결과

---

## 5. 데이터 흐름 (요약 다이어그램)

```
┌─ National Assembly OpenAPI ──────────────────────┐
│  nwvrqwxyaytdsfvhu (Person)                       │
│  nzmimeepazxkubdpn (Bill, ALLBILL)                │  ← real source
│  nojepdqqaweusdfbi (Vote, AGE+BILL_ID required)   │
└──────┬────────────────────────────────────────────┘
       │ data/real/*.py 어댑터 (BILL_NM→BILL_NAME, RST_PROPOSER, PUBL_PROPOSER)
       ▼
   S3 (assembly-dev)
       │ python -m data.load --source all --to s3 --bucket <bucket> --neptune --opensearch
       ▼
┌─ Neptune (74,249 real edges) ─┐  ┌─ OpenSearch (BM25+KNN) ──┐
│  PROPOSED, CO_PROPOSED,        │  │  Nori tokenizer (BM25)    │
│  CO_PROPOSED_WITH, VOTED,      │  │  Cohere embed-v4 (KNN)    │
│  MEMBER_OF, BELONGS_TO,        │  │  RRF fusion + rerank-v3   │
│  ASSIGNED_TO                   │  │                            │
└────────────┬───────────────────┘  └─────────────┬──────────────┘
             │ ENABLE_NEPTUNE_REAL=true             │
             ▼                                       ▼
┌─ FastAPI 라우터 (14 + 4 시나리오) ──────────────────────┐
│  /api/insights/influence-rank (U)                      │
│  /api/insights/party-cohesion (T)                      │
│  /api/insights/swing-voters (W)                        │
│  /api/insights/voting-cluster (V)                      │
│  /api/relations/{a}/{b} (O)                            │
│  /api/journey/{person_id} (M)                          │
│  /api/lookalike/{seed} (F)                             │
│  /api/outlier (K)                                      │
│  /api/objects/{class}/{id} (Object Explorer)           │
└────────────┬───────────────────────────────────────────┘
             │ + Synthetic fixture overlay (DEMO_PUBLIC_MODE=true)
             │ + External signal (J·N)
             ▼
     CloudFront → ALB → ECS Fargate (api + web)
             ▼
     assembly.whchoi.net
```

---

## 6. 정확성·신뢰성 보장

| 항목 | 적용 방식 |
|---|---|
| **데이터 출처 라벨** | 모든 응답에 `source: "real"`/`"synthetic"`/`"external"` 필드 자동 첨부 |
| **신뢰구간 (95% CI)** | ROI ±18%, similarity ±0.05, 표결 일치율 ±5pp |
| **Reproducibility** | `seed=20260513` 고정 + Bedrock `temperature=0.2` |
| **Bedrock Guardrails** | 시나리오 B·C·I·K 응답 입·출력 양쪽 4-layer 필터 (ADR-0004) |
| **political_balance_score** | 모든 LLM 응답에 자동 첨부, `<0.8` 시 UI 노란 경고 |
| **Reader.political_leaning 등 정치 성향 추론 필드 금지** | SECURITY.md §3 (저장·생성 모두 차단) |

---

## 7. 데이터 fixture 위치 (소스 파일)

```
data/
├── real/                         # 어댑터(.py) + 캐시된 의원 fixture만; 의안·표결은 라이브 fetch
│   ├── _client.py                # 공통 HTTP 클라이언트 (retry + rate limit + UA)
│   ├── member.py / bill.py / vote.py / committee.py / session.py / party.py / agency.py
│   ├── members_22.json           # 286명 22대 의원 캐시 (OpenAPI nwvrqwxyaytdsfvhu)
│   └── members_22_photos.json    # 의원 사진 위키피디아 캐시
│                                 #   (bills/votes는 정적 JSON 없음 — bill.py/vote.py가 OpenAPI에서 fetch)
├── synthetic/
│   ├── article.py                # 합성 기사 풀 (페르소나 × 토픽)
│   ├── advertisement.py          # Advertisement + AdInventory
│   ├── reader.py                 # Reader 합성 (political_leaning 금지)
│   ├── topics.py                 # Topic 시드
│   ├── placeholders.py           # 미구현 클래스 placeholder 인스턴스
│   └── seeds.py                  # PDF 시그니처 시연 시드 (결정적 SHA256)
├── external/
│   ├── naver_news.py             # 네이버 뉴스 검색 어댑터
│   └── poll_result.py            # 여론조사 (real 가능 시) / synthetic
│                                 #   (SNS는 미구현 — Phase 5 polish 예정)
└── schemas.py                    # 31 Pydantic 노드 클래스 + 관계 정의
```

---

## 8. Phase 진화 (real 데이터 커버리지 확장 history)

| Phase | 시점 | 작업 |
|---|---|---|
| Phase 1 | 초기 | 100% synthetic fixture (시연 안정성 우선) |
| Phase 4a | 2026-05 초 | OpenAPI 어댑터 fix (BILL_NM → BILL_NAME, RST_PROPOSER) |
| Phase 4b | 2026-05 중 | S3 → Neptune (UNWIND MERGE) → OpenSearch 적재 |
| Phase 4c | 2026-05 중 | Object Explorer 25+ 클래스 real query 전환 |
| Phase 4d | 2026-05 중 | boto3 `neptunedata` SDK로 SigV4 403 해결 |
| Phase 4e | 2026-05 중 | A·F·K·M·O 5 시나리오 100% real 전환 |
| **Phase 4f** | 2026-05 후 | T·U·V·W 4 신규 시나리오 (모두 real 100%) |

**현재 (2026-06-02) 상태**: **23 시나리오 중 9개(A·F·K·M·O·T·U·V·W)가 100% real** (≈39%). 나머지는 hybrid(real + synthetic) 또는 synthetic.

---

## 9. 시연 시 narrative 가치

- **편집국**: real ↔ synthetic 라벨 명시로 *팩트체크 가능*
- **데이터·AI 데스크**: 9개 100% real 시나리오는 *통계적 분석 신뢰성 ↑*
- **광고·세일즈**: synthetic AdInventory + Agent 매칭은 *광고 매칭 윤리 시연*
- **일반 독자 / 유료 구독자**: 의원 활동·정당 응집도는 *real 공공 데이터로 검증 가능*
- **B2B 정책 인텔리전스**: Neptune CO_PROPOSED_WITH + VOTED edges 기반 *입법 통과 예측*

---

## 10. 후속 개선 후보 (Phase 4g+)

| 단계 | 작업 |
|---|---|
| Phase 4g 후보 | 본회의 출석률·발언 수 real fetch (synthetic 메트릭 → OpenAPI) |
| Phase 5 polish | composite_score 가중치 config 노출 (페르소나별 customize) |
| 거버넌스 | external signal 자동 fetch pipeline (현재 mock layer) |
| 정확성 ↑ | C·G·L 시나리오의 fact 비율 확대 검토 |
