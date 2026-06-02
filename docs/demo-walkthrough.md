# Demo Walkthrough — 시연자 대본

`ontology-for-assembly` PoC의 라이브 데모 가이드. 30분 단축 / 60분 풀 두 가지 흐름 + 청중 Q&A FAQ + 백업 시나리오.

대상 청중: 한국 언론사 CxO·편집국장·데이터·AI 데스크 리드·광고·세일즈 매니저·B2B 정책 컨설팅 임원.

> **핵심 메시지 3가지** (모든 시연에서 1번 이상 반복)
> 1. **3-단계 진화** (Chatbot → Agent → Agentic AI) — 같은 질문에 3가지 답변을 동시에 보여줌.
> 2. **AI 거버넌스가 보인다** — ADR-0004 4-layer 가드레일이 차단이 아닌 product feature.
> 3. **B2C + B2B + 내부 staff 동시 시연** — 6 페르소나가 같은 데이터를 자기 KPI로 본다.

---

## 사전 준비 체크리스트 (시연 30분 전)

| 항목 | 명령 | 기대 출력 |
|------|------|----------|
| 환경 변수 | `echo $DEMO_PUBLIC_MODE` | `true` (라이브 시연 안전 모드) |
| 풀 테스트 | `make test` | `975 passed` |
| 풀 빌드 | `cd web && npx next build` | 23 시나리오 + objects·ops·members·mindmap 라우트 생성 |
| wow-eval | `python scripts/eval_wow_queries.py --quiet` | `pass_rate: 1.0, active: 84` |
| 가드레일 ID | `grep guardrail_id .env` | 실 Bedrock Guardrail ID 존재 |
| CloudFront | `curl -I https://<dist>/healthz` | 200 OK |
| 운영 콘솔 | 브라우저 → `/ops` | 5 패널 정상 |

**라이브 자유 질문 안전 모드**:
- `DEMO_PUBLIC_MODE=true`는 mock fixture로 응답 — 정치 민감 자유 입력에서 fail-safe.
- 시연 중 의도치 않은 사용자 입력은 `/api/neutrality/score`로 실시간 채점하여 보여주는 **백업 카드**로 활용.

---

## 30분 단축 흐름 (CxO·임원 청중)

| 시간 | 페르소나 | 페이지 | Hot point |
|------|---------|--------|-----------|
| 0-3 | (intro) | 홈 (`/`) | 23 시나리오 × 6 페르소나 매트릭스 (데모는 핵심 14개 A–N 집중). "한 화면에 모든 시연" |
| 3-8 | 편집국 | `/chat` → `/journey` → `/outlier` | 3-stage 비교 + PDF 시그니처 2개 |
| 8-13 | 광고·세일즈 | `/ad-match` | **데모 메인** - AI 거버넌스 3-way 광고 매칭 |
| 13-18 | 데이터·AI | `/cluster` → `/external-signal` | cross-party 협력 + 외부 신호 lead |
| 18-23 | 일반 독자 | `/district-map` → `/insights` | B2C UX + 친절한 해설 + 정치 균형 점수 |
| 23-28 | B2B | `/insights` (API 응답 보기) → `/article-roi` | JSON·KRW unit·API 자동화 |
| 28-30 | (closing) | `/neutrality` + `/ops` | ADR-0004 4-layer "보이는 거버넌스" + 운영 콘솔 |

핵심 클로징 메시지:
> "30분 안에 본 것은 핵심 14개(A–N) 시나리오 중 7개. 남은 7개와 추가 9개 확장 시나리오(O–W)까지 총 23개 모두 작동합니다. 좌측 사이드바로 직접 확인 가능합니다."

---

## 60분 풀 흐름 (편집국·데이터팀 청중)

### Opening — 3분

홈페이지(`/`) 진입.

- **"23 시나리오 모두 활성(핵심 14 + 확장 9). 6 페르소나가 같은 데이터를 자기 KPI로 봅니다."**
- 카테고리 4개 그룹 가리키기: 핵심 wow / AI 거버넌스 / 데이터·AI / B2C·B2B.
- 상단 stats badge: `14/14`, `6 페르소나`, `ADR-0004 4-layer 모두 적용`.

### Block 1 — 편집국 (10분)

좌측 사이드바에서 **편집국** 페르소나 선택. Sidebar가 자동 재정렬.

| 페이지 | 시간 | Hot point |
|--------|------|-----------|
| `/search` | 2분 | "AI 입법" 검색 → 1-hop subgraph(Cytoscape) + 의안·의원 hits + rerank 점수 |
| `/chat` → query="22대 AI 입법 동향" | 4분 | **3 패널 사이드바이사이드** — Chatbot RAG(빠름·shallow) / Agent Tool Use(중간·tool trace) / Agentic AI 4 에이전트(느림·deep + 후속 취재 hint) |
| `/journey` → MONA_001 선택 | 2분 | **PDF 시그니처 ★** — 8 이벤트 timeline, 페르소나 extras에 "후속 취재 포인트" 자동 첨부 |
| `/outlier` | 2분 | **PDF 시그니처 ★** — 3 유형(당론 이탈·박빙·정파 초월 협력). AI 라벨이 정파 평가 어휘 없음을 강조 |

핵심 메시지:
> "여기까지 본 4 시나리오 모두 **출처 인용 + 양당 균형 표현 + 단정적 가치 판단 회피**가 자동 적용. 다음 블록에서 그 메커니즘을 직접 보여드립니다."

### Block 2 — AI 거버넌스 (10분)

| 페이지 | 시간 | Hot point |
|--------|------|-----------|
| `/neutrality` | 4분 | **ADR-0004 4-layer 다이어그램** — Bedrock Guardrails(L1) + System Prompt Suffix(L2) + balance_score(L3) + FORBIDDEN_FIELDS(L4). 4 등급 샘플(낮음 0.3 → 우수 0.97) 점수 차이 시연. 라이브 텍스트 입력 → 실시간 채점 (청중 자유 질문 받기) |
| `/ad-match` | 6분 | **데모 메인** — 같은 콘텐츠에 3 모드 적용. *keyword*가 매칭한 광고를 *embedding*은 다르게, *Agent*는 비위 의혹·비극 콘텐츠에서 **자동 광고 거절** (chosen_ad_id=null). reasoning trace 라이브 노출 |

핵심 메시지:
> "광고 매칭에서 keyword/embedding이 매칭한 슬롯을 Agent가 **AI 거버넌스 판단으로 자발적으로 거절**합니다. 한국 광고주가 가장 두려워하는 '정치 민감 콘텐츠 광고 매칭' 리스크를 시스템 단에서 차단합니다."

### Block 3 — 데이터·AI 데스크 (10분)

페르소나 전환: **데이터·AI**.

| 페이지 | 시간 | Hot point |
|--------|------|-----------|
| `/cluster` | 3분 | 5 thematic cluster. **모든 cluster가 cross-party** (정파 기반 grouping 금지로 자연스럽게 도출). cross_party_share로 정파 분산도 노출 |
| `/external-signal` | 4분 | **3 narrative 패턴** — signal_leads(AI: 시그널이 5주 앞섬) / legislation_leads(환경: 입법이 3주 앞섬) / decoupled(문화). 12주 dual-line SVG 시계열 |
| `/issue-legislation` | 2분 | **8×4 heatmap** + Top 5 강한 결합. 셀에 정당 카운트 없음(ADR-0004) — 매트릭스 axis 선택 자체가 거버넌스 |
| `/lookalike` → MONA_001 | 1분 | 동일 cluster + 다른 정당 후보 = **cross-party signal** 태그. 협력 잠재력 narrative |

핵심 메시지:
> "데이터 팀이 가장 가치 있게 보는 cross-party 협력 그룹 발굴. 정당으로 묶지 않기 때문에 정당을 가로지르는 새 그룹이 자연 발생합니다."

### Block 4 — B2C·B2B (10분)

페르소나 전환: **일반 독자** → **유료 구독자** → **B2B**.

| 페르소나 | 페이지 | 시간 | Hot point |
|---------|--------|------|-----------|
| 일반 독자 | `/district-map` → `seoul` | 2분 | 17 KOSTAT 시도 grid, 시도 선택 시 디테일. "내 동네 의원 한눈에" |
| 일반 독자 | `/insights` → 토픽 필터 | 2분 | 친절한 톤 + 정치 균형 점수 자동 노출 + 양당 정보 균형 인용 |
| 유료 구독자 | `/journey` | 2분 | 페르소나 전환 시 같은 페이지의 extras가 "premium PDF CTA"로 변화 — **동일 데이터, 다른 hint** |
| 유료 구독자 | `/persona-match` | 1분 | affinity 매트릭스 직접 공개 — 구독자 신뢰 확보 |
| B2B | `/insights/articles/<id>` | 2분 | extras에 `api_response_hint` — 자동화 지침. JSON 응답 그대로 dashboard 통합 가능 |
| B2B | `/article-roi` | 1분 | metrics 키 KRW unit 명시. webhook 알림 hint |

핵심 메시지:
> "같은 데이터, 같은 page route, 같은 query — 페르소나만 바꿔도 응답의 tone, extras, 추천 행동이 자동 재구성. **6 페르소나 매트릭스가 single source of truth**입니다."

### Block 5 — 운영 + 종합 (10분)

| 페이지 | 시간 | Hot point |
|--------|------|-----------|
| `/objects` | 2분 | **31 클래스 온톨로지** — Bill·Person·Vote 등. 클래스 선택 시 페이징 + 1-hop subgraph 시각화 |
| `/ops` | 3분 | 5 패널 — Ingest·Guardrail·Memory·wow-quality(84/84)·Trace 링버퍼 |
| `/ops` → wow-quality | 1분 | **84 케이스 100% PASS, avg balance 0.979** — 자동 CI gate |
| GuidedTour(우측 하단 🗺) | 2분 | 페르소나별 4-5 step 추천 흐름 — 시연자 안내 도구로도 활용 |
| 자유 질문 + Q&A | 2-5분 | (FAQ 섹션 참조) |

핵심 클로징:
> "10분 안에 보여드린 cross-party 협력 그룹, signal lead 패턴, AI 거버넌스 광고 매칭. **모두 같은 페이지의 같은 라우터로 6 페르소나가 각자 KPI로 보고 있습니다.** 이게 본 PoC가 GS Caltex급 production 자산으로 평가받는 이유입니다."

---

## Q&A FAQ

### 정치 중립성

**Q. 정치 중립성을 어떻게 보장합니까? 한쪽 정당으로 편향되면 어떻게 됩니까?**

A. 4-layer 가드레일이 작동합니다:
- L1 Bedrock Guardrails: 정당 비방 결합 패턴 자동 차단 (`bedrock-runtime.apply_guardrail`).
- L2 System Prompt Suffix: 모든 LLM 호출에 6개 원칙 자동 부착.
- L3 `political_balance_score`: 모든 응답에 자동 계산 + 임계 0.8 미만 시 알람.
- L4 FORBIDDEN_FIELDS: `Reader.political_leaning` 등 정치 성향 추론 필드 자체를 schema에서 금지.

`/neutrality` 페이지에서 라이브 채점을 보여드릴 수 있습니다. 청중이 임의 텍스트를 입력하면 즉시 점수 + 알람 시각화.

**Q. ADR-0004 위반 시도(예: 정당 비방 문장 입력)는 어떻게 처리됩니까?**

A. `/neutrality` 페이지에서 "더불어민주당이 잘못했다 무능했다 실패했다" 같은 텍스트를 입력해 보세요. 즉시 score ~0.3 + 알람 trigger + Layer 1이 차단 사유 노출.

### 다른 도메인 적용

**Q. 정치 외 다른 민감 도메인(의료·법무·세법)에도 적용 가능합니까?**

A. [[ADR-0005]]에서 5가지 narrative 디자인 패턴을 일반화 가능 패턴으로 정리했습니다. Visible Governance, Cross-axis Inversion, Narrative-first Statistics 등은 의료(환자 차별 회피)·법무(판결 편향 회피)·세법(소득 계층 차별 회피)에 그대로 적용 가능. 본 PoC가 reference architecture.

### 비용·운영

**Q. Production 운영 비용?**

A. `docs/deploy-logs/cost-estimate.md` 참조. dev 환경 ~$600/월(OpenSearch Serverless 60%). 사용자 1만 명 production ~$5,000/월. 절감 옵션 3가지 적용 시 dev ~$260/월.

**Q. Bedrock LLM 호출이 매번 발생합니까? latency·비용 어떻게 관리?**

A.
- AgentCore Memory short-term 캐시로 반복 질문 cost 감소.
- OpenSearch Serverless로 RAG 검색 → Sonnet 4.6 호출 횟수 최소화.
- 시연 평균: Sonnet 1회 호출 + Cohere embed 1회 + rerank 1회 = ~$0.05/시연.
- `/ops/trace` 패널에서 호출별 latency·비용 라이브 모니터링.

### B2B·B2C 인증

**Q. 6 페르소나 인증 분기?**

A. 인증은 **Lambda@Edge + API Gateway(edge 계층)**에서 강제 — FastAPI 계층엔 인증 미들웨어가 없고 유효한 `X-Persona-Id` 헤더만 수신(ADR-0003):
- staff (editorial·data_ai·ad_sales): Cognito user pool JWT + IAM staff group.
- subscriber (paid_subscriber): Cognito JWT + subscriber group.
- general_reader: Cognito Guest Identity Pool + 게스트 쿠키.
- b2b: API Gateway Usage Plan + API Key (DynamoDB lookup + Secrets Manager).

edge에서 fail-closed — 인증 실패 시 차단. (API는 헤더 누락 시에만 `editorial` fallback.)

**Q. B2B 클라이언트가 API 사용 시 정치 균형 점수도 받습니까?**

A. 네. 모든 LLM 응답에 자동 첨부. `b2b` 페르소나의 API 응답 hint에 단위 명시("KRW", "score 0-1", "ISO 주차" 등) — B2B의 자동화 dashboard 통합 직결.

### 데이터 출처

**Q. 합성 데이터는 어디서 오고, 어떻게 검증합니까?**

A. 3-tier source 태깅:
- `source="real"`: 국회 OpenAPI (의안·의원·표결·위원회·본회의).
- `source="synthetic"`: 합성 generator (Article·Reader·Advertisement·합성 시드).
- `source="external"`: 네이버 뉴스·SNS·여론조사.

모든 노드에 `source` 속성 강제 (Pydantic strict). `DataSourceBadge` 컴포넌트가 모든 페이지 상단에 노출. 합성 데이터는 정치 균형 강제(`test_insights_synthetic_balance_high`)로 ADR-0004 보장.

### 확장·통합

**Q. 우리 언론사 기존 CMS·DMP와 통합 가능?**

A. 23 시나리오 모두 REST/SSE 표준 API (응답 schema는 핵심 14개가 `docs/api-reference.md`에 정리). 헤더 `X-Persona-Id` 추가 외에는 일반 fetch + JSON parse. SSE는 `EventSource` 또는 fetch + ReadableStream(`web/lib/api-client.ts` 참조).

**Q. Bedrock 외 다른 LLM(GPT·Gemini)로 swap 가능?**

A. `api/services/bedrock.py:invoke()/invoke_stream()` 단일 진입점 (ADR-0001). swap 시 이 함수만 변경. 21 라우터는 영향 없음.

---

## 백업 시나리오 (라이브 시연 실패 대응)

| 실패 | 대응 |
|------|------|
| Bedrock API 응답 실패·timeout | `DEMO_PUBLIC_MODE=true`로 mock 응답 자동 전환. 시연자: "지금 mock 모드로 전환됐는데 응답 형식은 동일합니다." |
| OpenSearch 응답 실패 | `/api/search`가 `synthetic` source로 폴백. UI는 "데이터 출처: synthetic" 배지 노출. |
| Neptune 연결 실패 | 1-hop subgraph만 영향 — search 결과는 정상. "subgraph 시각화는 별도 인프라 작업 중"으로 안내. |
| 청중이 ADR-0004 위반 자유 질문 | 즉시 `/neutrality` 페이지로 전환 → 그 자체를 시연 도구로 활용. "방금 그 질문을 시스템이 어떻게 처리하는지 보여드리겠습니다." |
| wow-eval CI gate 실패(pass_rate < 0.85) | 운영 콘솔 `/ops/wow-quality`에서 실패 케이스 확인. 시연 중 발생 시 "이게 바로 운영 모니터링이 자동으로 잡아내는 사례"로 narrative 전환. |
| CloudFront cached 응답 | 시연 직전 `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`. 또는 `?nocache=<ts>` query string. |
| 청중이 정치 자유 질문(예: "민주당이 더 잘하나요?") | `/neutrality/score`로 즉시 채점 + `/neutrality/architecture`로 4-layer 다이어그램 노출. "이런 질문은 시스템이 채점·필터링·균형 보강해서 응답합니다." |

### 페일오버 명령어 모음

```bash
# 모든 시나리오 즉시 mock 모드로 전환 (시연 직전 fail-safe)
export DEMO_PUBLIC_MODE=true && \
  aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-api \
    --force-new-deployment

# 운영 콘솔에서 최근 trace 5개 확인 (LLM 호출 패턴 점검)
curl -s https://<cf>/api/ops/trace?limit=5 | jq

# wow-eval 즉석 재실행 (인프라 점검)
python scripts/eval_wow_queries.py --base-url https://<cf>

# CloudFront 캐시 무효화
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```

---

## 페르소나별 시연 강조 포인트 (cheat sheet)

| 페르소나 | "이 페르소나에서 가장 인상적인 것" |
|---------|---------------------------------|
| 편집국 | PDF 시그니처 2개 (K·M) + 3-stage chatbot의 후속 취재 hint 자동 생성 |
| 데이터·AI | cross-party 협력 cluster + signal_leads/legislation_leads 명시적 narrative |
| 광고·세일즈 | Agent의 자발적 광고 거절 (chosen_ad_id=null) + reasoning trace 라이브 |
| 일반 독자 | 같은 페이지의 친절한 톤 + 양당 정보 균형 + 17 시도 지도 직관 |
| 유료 구독자 | 페르소나 전환 시 extras가 "premium CTA"로 자동 변화 + PDF 리포트 |
| B2B | API 응답 자동화 hint + KRW unit + webhook 알림 + JSON 그대로 통합 |

## References

- 14 시나리오 코드·narrative: [[ADR-0005]] Phase 4 Narrative Design Choices
- 4-layer 가드레일: [[ADR-0004]] Political Neutrality Guardrails
- 6 페르소나 SSOT: `api/services/persona.py:PERSONA_REGISTRY`
- 비용 모니터링: `docs/deploy-logs/cost-estimate.md`
- API endpoint reference: `docs/api-reference.md`
- GuidedTour (in-app cheat sheet): `web/components/GuidedTour.tsx`
