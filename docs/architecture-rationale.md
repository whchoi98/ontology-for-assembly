# Architecture Rationale — RAG vs Knowledge Graph + Agent

**문서 목적**: 본 PoC가 *순수 RAG*에 머무르지 않고 *Knowledge Graph (Neptune) + Agent Tool Use*까지 확장한 이유, 그리고 OpenSearch Serverless (AOSS)와 Neptune의 역할 분담을 정리.

**관련 문서**:
- ADR-0001 (gcc 아키텍처 차용)
- ADR-0004 (정치 중립성 가드레일)
- `docs/data-sources.md` (데이터 참조 매트릭스)
- `CLAUDE.md` (프로젝트 메모리)

> **핵심 메시지**: "RAG를 사용 안 한다"가 아니라 **"RAG만 쓰지 않는다"**.
> RAG는 *기본*이고, Knowledge Graph + Agent Tool Use는 *진화*입니다.
> 3단계 진화 비교 (Chatbot → Agent → Agentic AI)는 *RAG의 한계*와 *KG+Agent의 가치*를
> 청중에게 *체감으로 전달*하기 위한 의도된 narrative입니다.

---

## 1. RAG는 사용합니다 — 위치 정확히 짚기

| 사용 위치 | 패턴 | 구성 |
|---|---|---|
| **시나리오 A** (의미 검색) | Hybrid RAG | BM25(Nori) top-50 + Cohere KNN top-50 → RRF fusion (k=60) → Cohere rerank-v3 top-10 |
| **시나리오 B Stage 1** (Chatbot) | 단순 RAG | OpenSearch top-5 + Bedrock 단일 호출 → "한계 노출" 시연 |
| **데이터 fetch backbone** | RAG-style retrieval | 모든 시나리오의 *citation·출처 검증* 섹션 |

→ "RAG를 사용 안 한다"가 아니라 **"RAG만 쓰지 않는다"** 가 정확.

---

## 2. *그럼에도* Knowledge Graph + Agent를 추가한 이유

### RAG 단독의 *3가지 한계* — 데모 narrative

| 질문 | RAG로 가능? | 왜 안 되는가 |
|---|:--:|---|
| "AI 산업 진흥 의안 검색해줘" | ✓ | 텍스트 의미 검색은 RAG의 본분 |
| **"의원 영향력 1위는 누구?"** | ✗ | 정량 *aggregation·ranking* 필요 — RAG는 검색만 가능 |
| **"강경숙 ↔ 김기현 관계는?"** | ✗ | 그래프 *multi-hop traversal* 필요 |
| **"정당 응집도 99%인 근거?"** | ✗ | 28,528 표결의 *cohort majority 계산* 필요 |
| **"이 의원과 유사 활동 패턴 의원?"** | ✗ | CO_PROPOSED_WITH cohort 가중치 합산 필요 |
| **"swing voter 누구?"** | ✗ | 정당 majority alignment 일치율 계산 필요 |

이런 질문은 *RAG의 retrieval 패러다임*으로는 답할 수 없습니다. *계산·집계·관계 traversal*이 필요합니다.

### 3단계 진화 narrative (시나리오 B의 핵심 메시지)

```
Stage 1: RAG (Chatbot)         "못 한다" 정직하게 답함
   ↓
Stage 2: Agent (Tool Use)      필요한 도구를 호출해서 답함
   ↓
Stage 3: Agentic (Multi-agent) 자율 계획 + 다단계 분석
```

**라이브 데모 검증된 예시**:

```
사용자: "의원 영향력 1위는?"

Stage 1 (RAG)      → "RAG는 cohort 가중치 합산·ranking algorithm 실행 불가.
                       Agent/Agentic mode 필요."
Stage 2 (Agent)    → "1위 윤준병 (더불어민주당) — cohort 3,258, 발의 55건..."
                       (get_influence_rank tool 호출 → real Neptune 결과)
Stage 3 (Agentic)  → Stage 2 + Planner/Graph/Analyst/Editor 4 에이전트 trace
```

→ **같은 질문에 *3가지 다른 답*** → *RAG의 한계 + KG의 가치*를 즉시 체감.

---

## 3. Neptune (GraphDB) vs OpenSearch (AOSS) 역할 분담

### 두 시스템의 *paradigm 차이*

| 구분 | OpenSearch Serverless (AOSS) | Amazon Neptune (GraphDB) |
|:--|---|---|
| **Data model** | Inverted index + vector | Property graph (node + edge) |
| **Query language** | DSL (BM25, KNN) | openCypher / Gremlin |
| **최적 query** | "*무엇*과 유사한가" (textual similarity) | "*어떻게* 연결되어 있는가" (relation traversal) |
| **응답 unit** | 정렬된 문서 list | 그래프 path / subgraph |
| **scale** | 텍스트 백만 건 sub-second | 엣지 수억 multi-hop sub-second |

### 이 PoC의 *역할 분담*

```
┌─ OpenSearch Serverless (AOSS) ──────────────────┐
│  적재: 의안 텍스트·기사 본문·발언록             │
│  인덱싱: Nori tokenizer (BM25) + embed-v4 (KNN) │
│  활용:                                            │
│    - 시나리오 A: "AI 산업 진흥법" 의안 검색      │
│    - 시나리오 B Stage 1: RAG 텍스트 retrieval    │
│    - 시나리오 F·D: 유사 의안·기사 매칭           │
│  특기: *텍스트 의미적 유사도*                     │
└──────────────────────────────────────────────────┘

┌─ Amazon Neptune (Graph DB) ─────────────────────┐
│  적재: 74,249 real edges                          │
│    - PROPOSED (의원 → 의안)                      │
│    - CO_PROPOSED (공동발의)                       │
│    - CO_PROPOSED_WITH (의원 ↔ 의원 cohort)       │
│    - VOTED (의원 → 의안, value)                  │
│    - MEMBER_OF (의원 → 위원회)                   │
│    - BELONGS_TO (의원 → 정당)                    │
│  활용:                                            │
│    - 시나리오 O: 의원 ↔ 의원 5차원 cross-tab    │
│    - 시나리오 T·V: 정당 응집도·표결 cluster      │
│    - 시나리오 U: 의원 영향력 (cohort 가중치)     │
│    - 시나리오 W: swing voter detection           │
│    - 시나리오 K: 표결 이상치 감지                 │
│    - 시나리오 M: 의원 timeline aggregation       │
│    - 시나리오 F: 룩어라이크 cohort               │
│  특기: *관계 traversal·집계·aggregation*          │
└──────────────────────────────────────────────────┘
```

### Hybrid 패턴 (두 시스템 *교차 활용*)

| 시나리오 | 흐름 |
|---|---|
| **A 의미 검색** | OpenSearch 검색 → Neptune 1-hop 그래프 expand (의안 → 발의자) |
| **F 룩어라이크** | Neptune CO_PROPOSED_WITH cohort 추출 → OpenSearch 유사 의안 매칭 |
| **B Stage 2 Agent** | search_bills (OpenSearch) + get_proposers (Neptune) + cosponsor_network (Neptune) + analyze_votes (Neptune) |
| **M 의원 여정** | Neptune full timeline → 외부 신호 J overlay |
| **N 이슈 × 입법** | 토픽 trend (OpenSearch) ↔ 의안 발의 (Neptune) cross-correlation |

→ **둘 다 필요**: OpenSearch는 *what* (무슨 내용), Neptune은 *who/how* (누가, 어떻게 연결).

---

## 4. 왜 *이 조합*이 PoC narrative의 핵심인가

### 한국 언론사 시연 메시지

> "지금 시중의 챗봇은 *단순 텍스트 검색* (RAG) 뿐입니다.
> 하지만 **언론 데이터는 *관계*가 핵심**입니다 —
> 누가 누구와 같이 발의했고, 어떤 정당과 어떤 표결을 했고, 어느 위원회 소속이고...
> 이런 *관계 차원*은 RAG로 답할 수 없습니다.
> **Knowledge Graph (Neptune) + Agent Tool Use**가 *진짜 분석*을 가능하게 합니다."

### 시연 시 사용자 체험 흐름

1. **Stage 1 (RAG)**: "정당 응집도 알려줘" → "**RAG는 표결 majority 계산 불가**. Agent mode 시도하세요" *(정직한 한계 노출)*
2. **Stage 2 (Agent)**: 같은 질문 → `get_party_cohesion` tool 호출 → "8 정당 평균 99%, 더불어민주당 99%·국민의힘 88%..." *(real Neptune Cypher 실행)*
3. **Stage 3 (Agentic)**: 같은 질문 → 4 에이전트 trace + 더 깊은 분석 narrative *(자율 multi-step)*

→ 같은 질문에 *3가지 다른 답*을 보여줘서 *RAG의 한계 + KG의 가치*를 즉시 체감.

---

## 5. 정리 — "왜 이 architecture인가"

| 구성요소 | 역할 | 단독으로 충분한가 |
|---|---|:--:|
| **OpenSearch (AOSS)** | 텍스트 의미 검색 (RAG) | ✗ (관계·집계 불가) |
| **Neptune (Graph DB)** | 관계 traversal·cohort·aggregation | ✗ (텍스트 의미 검색 약함) |
| **Bedrock (LLM)** | 자연어 생성·페르소나 어조 | ✗ (사실 계산 불가) |
| **AgentCore (Tool Use)** | LLM이 정확한 도구 선택·호출 | ✗ (LLM이 자체 reasoning만으론 부정확) |

**→ 4개의 *상호보완*이 PoC의 architecture 핵심.**

**→ RAG는 *기본*이고, Knowledge Graph + Agent는 *진화*입니다.**

---

## 6. RAG의 한계 — *왜* RAG 단독이 안 되는가 (기술적 deep-dive)

### RAG paradigm 본질

```
사용자 질문 → embedding/keyword 매칭 → 유사 문서 top-K → LLM context 주입 → 자연어 답
```

이 흐름은 **textual similarity**가 본질입니다. *단어가 유사한 문서를 찾아 LLM에 context로 주는 패턴*.

### RAG가 *못 하는* 것

1. **Aggregation·계산**:
   - "정당별 평균 응집도?" → 28K 표결을 *aggregate* 해야 함. RAG는 *문서 list*만 반환
   - "공동발의 cohort top 10?" → CO_PROPOSED_WITH 엣지 *sum* 필요. RAG는 *count·sum 불가*
2. **Multi-hop traversal**:
   - "강경숙과 표결 패턴 비슷한 의원의 정당 분포?" → 2-hop graph walk 필요. RAG는 *direct lookup만*
3. **시점·구조 query**:
   - "1분기 burst → 2분기 통과 lag?" → time-window aggregation 필요
   - "정당 내 swing voter ratio?" → conditional aggregation 필요
4. **Fact-based 정량 답변**:
   - LLM이 textual context로부터 *추정*은 가능하지만 *정확한 ranking·percentile은 hallucination 위험*

### 본 PoC가 이 한계를 해결한 방법

| 한계 | 해결책 |
|---|---|
| Aggregation | Neptune Cypher `count(...)`, `sum(...)`, `WITH ... aggregate` |
| Multi-hop | Neptune `MATCH path` traversal (1-hop, 2-hop, 3-hop) |
| 시점·구조 | Neptune + Python window functions (cohort analysis) |
| 정확한 정량 | *Tool Use* — LLM이 `get_influence_rank` 같은 *결정적 도구* 호출 |

---

## 7. Hybrid 패턴의 *4가지 archetype*

### Archetype 1: 텍스트 검색 우선
```
Query → OpenSearch (text similarity) → top-K 문서 → LLM 답
```
→ 시나리오 A "AI 산업 진흥법" 같은 *내용 검색* 질문

### Archetype 2: 관계 분석 우선
```
Query → Neptune (graph traversal) → cohort/subgraph → LLM narrative
```
→ 시나리오 O "강경숙 ↔ 김기현 관계" 같은 *연결 분석*

### Archetype 3: Cross-feed (OS→Neptune)
```
Query → OpenSearch top-K → Neptune으로 1-hop graph expand → LLM 답
```
→ 시나리오 A의 *의안 검색 → 발의자/공동발의자 표시*

### Archetype 4: Cross-feed (Neptune→OS)
```
Query → Neptune cohort 추출 → OpenSearch로 유사 의안 매칭 → LLM 답
```
→ 시나리오 F 룩어라이크의 *cohort 추출 → 활동 패턴 매칭*

---

## 8. PoC 단계의 의사결정 history

| 시점 | 결정 | 이유 |
|---|---|---|
| 초기 design | RAG 기반 챗봇 1개 | 가장 간단·시연 친화 |
| 1차 review | "RAG만으론 *관계 narrative* 부족" 인식 | 언론사 데이터는 *who/how*가 핵심 |
| 2차 design | Neptune Knowledge Graph 추가 | *관계 차원*의 분석 가능 |
| 3차 design | Agent Tool Use 패턴 추가 | LLM이 *정확한 도구*를 자율 선택 |
| 4차 design | Multi-agent Agentic 추가 | *자율 multi-step* narrative 시연 |
| 최종 narrative | **3단계 진화 비교** | 같은 질문에 *3가지 다른 답* — 시각적·체감적 차이 |

→ "RAG → KG → Agent → Agentic"는 *기술 진화*이자 *시연 narrative*의 핵심.

---

## 9. 비교 — 다른 옵션 검토

### Option A: Pure RAG (탈락)
- 장점: 단순·구현 빠름
- 단점: *aggregation·관계 분석 불가* → 시나리오 K·M·O·T·U·V·W 구현 불가
- 결정: ✗ (PoC 메시지 약화)

### Option B: Pure Graph DB (탈락)
- 장점: 관계 분석 강력
- 단점: *텍스트 의미 검색 약함* → 시나리오 A·D·G 약함
- 결정: ✗

### Option C: RAG + Graph DB 병행, no Agent (부분 채택)
- 장점: 두 paradigm의 장점
- 단점: *LLM이 어느 도구를 쓸지 모름* → 사용자가 *수동*으로 선택해야 함
- 결정: 부분 채택 (시나리오 A·D 수준)

### Option D: RAG + Graph DB + Agent Tool Use (✓ **최종 채택**)
- 장점: *LLM이 자율적으로* OpenSearch/Neptune 도구 선택·호출
- 시연 가치: *진짜 Agent* 시연 가능
- 결정: ✓ (PoC 핵심 architecture)

### Option E: + Multi-agent Agentic (✓ Stage 3 추가)
- 장점: *Planner→Graph→Analyst→Editor* 4 에이전트 자율 협업 시연
- 시연 가치: *AgentCore의 자율 협업 능력* 강조
- 결정: ✓ (시연의 climax)

---

## 10. 핵심 메시지 정리

> **RAG는 *과거*, KG+Agent는 *현재와 미래*입니다.**
>
> - RAG 단독으로는 *언론사의 진짜 needs*(관계·집계·정량 분석)에 답할 수 없음
> - Knowledge Graph(Neptune)는 *관계 차원*을, Agent Tool Use는 *정확한 계산*을 해결
> - 3단계 진화 비교 (Chatbot → Agent → Agentic) = *기술 진화*와 *시연 narrative*를 동시에 전달
> - OpenSearch (AOSS)와 Neptune은 *경쟁*이 아닌 *상호 보완* — paradigm이 다름
> - 본 PoC는 둘 다 *적재적소* 사용하는 *hybrid architecture* 시연

---

## 11. 후속 개선 후보

| Phase | 작업 |
|---|---|
| Phase 5 polish | Bedrock Converse API의 *real Tool Use*로 전환 (현재 PoC는 simulated tool call) |
| Phase 6 | OpenSearch와 Neptune의 *unified query API* (Agent이 자동 라우팅) |
| Phase 7 | *Multi-modal RAG* — 의안 PDF·인포그래픽·동영상 검색 |
| Phase 8 | *Federated graph* — 외부 KG (예: WikiData) cross-join |

---

## 12. 4개 service의 호출 처리 관계 — 실제 시퀀스

> **상세 시퀀스·dispatch 매트릭스는 별도 문서 [`docs/call-flow.md`](./call-flow.md) 참조.**
> 본 섹션은 *요약*과 *핵심 메시지*만 포함.

### 4개 service 역할 정리

| Service | 역할 | "무엇을 결정하는가" |
|---|---|---|
| **Bedrock LLM (Sonnet 4.6)** | reasoning · 자연어 생성 · *어느 도구를 쓸지 판단* | "이 질문엔 KNN 검색? 아니면 Cypher 집계?" |
| **AgentCore** | tool dispatcher · session memory · trace 관리 | "LLM의 tool call을 실제 service 호출로 변환" |
| **OpenSearch (AOSS)** | 텍스트 의미 검색 (BM25 + KNN) | "이 query와 유사한 *문서 top-K*" |
| **Neptune (Graph DB)** | 관계 traversal · cohort 집계 | "이 person의 *cohort·표결·이웃*" |

### 호출 패러다임 비교

```
RAG paradigm:        Query → Retrieve → Generate
                     (LLM 1회, Store 1회)

Agent paradigm:      Query → LLM-decide-tool → Tool-execute → LLM-generate
                     (LLM 2-3회, Store N회)

Agentic paradigm:    Query → Planner → Graph → Analyst → Editor (multi-step LLM)
                     (LLM 4회+, Store N회, 자율 multi-step)
```

### 핵심 메시지

| 질문 | 답 |
|---|---|
| AgentCore는 데이터를 가지나? | ✗ (conductor 역할, 데이터는 AOSS/Neptune에 있음) |
| LLM은 도구를 직접 호출하나? | ✗ (LLM은 *어느 도구 쓸지만 응답*, AgentCore가 실제 호출) |
| AOSS와 Neptune은 경쟁하나? | ✗ (paradigm이 다름, 상호 보완) |
| RAG는 어디 들어가나? | OpenSearch retrieval pipeline (BM25+KNN+RRF+rerank) |
| Agent와 RAG의 차이는? | RAG는 *고정 흐름*, Agent는 *LLM이 도구 선택* |

→ **AgentCore = conductor, LLM = decision-maker, AOSS·Neptune = data store.**
→ **상세 시퀀스 다이어그램·tool dispatch 매트릭스·case별 trace는 [`docs/call-flow.md`](./call-flow.md) 참조.**
