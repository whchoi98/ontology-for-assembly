# AOSS · Neptune · Bedrock LLM · AgentCore 호출 처리 관계

**문서 목적**: 4개 service (AOSS · Neptune · Bedrock LLM · AgentCore)가 *어떻게 협업해서* 단일 사용자 query를 처리하는지 시퀀스·dispatch 매트릭스로 정리.

**관련 문서**:
- `docs/architecture-rationale.md` (왜 이 architecture인가 — RAG vs KG+Agent)
- `docs/data-sources.md` (데이터 참조 매트릭스)
- ADR-0001 (gcc 아키텍처 차용)
- `CLAUDE.md` (프로젝트 메모리)

> **핵심 메시지**: 4개 service의 호출 관계는 **AgentCore가 conductor(지휘자)**,
> LLM·OpenSearch·Neptune이 각각 *연주자*인 *오케스트라 패턴*입니다.
> AgentCore는 직접 데이터를 가지지 않고, **LLM의 reasoning + tool dispatch**로
> 두 데이터 store를 *적재적소 호출*합니다.

---

## 1. 4개 service의 역할 정리

| Service | 역할 | "무엇을 결정하는가" |
|---|---|---|
| **Bedrock LLM (Sonnet 4.6)** | reasoning · 자연어 생성 · *어느 도구를 쓸지 판단* | "이 질문엔 KNN 검색? 아니면 Cypher 집계?" |
| **AgentCore** | tool dispatcher · session memory · trace 관리 | "LLM의 tool call을 실제 service 호출로 변환" |
| **OpenSearch (AOSS)** | 텍스트 의미 검색 (BM25 + KNN) | "이 query와 유사한 *문서 top-K*" |
| **Neptune (Graph DB)** | 관계 traversal · cohort 집계 | "이 person의 *cohort·표결·이웃*" |

> **단순 RAG**는 LLM↔Store *1:1*, **Agent**는 *AgentCore가 LLM에게 "어느 도구를 쓸지 묻고" 그 답을 받아 실행*하는 *2-step interaction loop*입니다.

---

## 2. 호출 시퀀스 — 3 Stage 비교

### Stage 1 (RAG · 단순) — *LLM ↔ AOSS 직접 호출*

```
사용자 query
   │
   ▼
┌─ FastAPI Router (api/services/three_stage.py:stage1_chatbot) ─┐
│  1. OpenSearch hybrid_search(query, top_k=5)                  │
│     → BM25(Nori) + KNN(Cohere embed-v4) + RRF                │
│  2. Bedrock.invoke(query + context_text)                      │
│     → Sonnet 4.6 단일 호출, tool use 없음                     │
│  3. response 반환                                              │
└────────────────────────────────────────────────────────────────┘

🔑 특징: AgentCore 미사용, Neptune 미사용. RAG paradigm 그대로.
   한계: 정량 계산·집계·관계 traversal 불가.
```

### Stage 2 (Agent · Tool Use) — *AgentCore가 conductor*

```
사용자 query: "의원 영향력 1위는?"
   │
   ▼
┌─ AgentCore Runtime (Tool Use loop) ──────────────────────────┐
│                                                                │
│  ① Bedrock LLM에게 system_prompt + 사용 가능 TOOL_SPECS 전달  │
│     "사용 가능 도구: search_bills, get_proposers,             │
│                     get_influence_rank, cosponsor_network..."  │
│                                                                │
│  ② LLM 응답: 'tool_use' → {                                   │
│       name: "get_influence_rank", input: {limit: 5}           │
│     }                                                          │
│                                                                │
│  ③ AgentCore dispatch → /api/insights/influence-rank          │
│       → Neptune Cypher 실행                                    │
│       → real 결과 반환 (윤준병 1위 ...)                        │
│                                                                │
│  ④ tool_result를 다시 LLM에게 전달                            │
│                                                                │
│  ⑤ LLM 최종 답변 생성 (real data 인용)                        │
│                                                                │
└────────────────────────────────────────────────────────────────┘

🔑 특징: AgentCore가 LLM↔Tool간 *반복 loop* 관리.
        LLM이 "어느 도구"를 결정 → AgentCore가 실제 호출 → 결과 → LLM이 답변 작성.
```

### Stage 3 (Agentic · Multi-agent) — *Planner→Graph→Analyst→Editor 4 에이전트*

```
사용자 query
   │
   ▼
┌─ AgentCore Multi-agent Pipeline ─────────────────────────────┐
│                                                                │
│  ① Planner LLM    → 하위 과제 N개 분해 plan 생성              │
│                                                                │
│  ② Graph Agent    → OpenSearch search_bills + Neptune queries│
│                     + (영향력 query 감지 시) get_influence_rank│
│                     → graph_summary                            │
│                                                                │
│  ③ Analyst LLM    → graph_summary 해석 + 가설 생성            │
│                                                                │
│  ④ Editor LLM     → Planner+Graph+Analyst 종합 → 최종 기사     │
│                                                                │
└────────────────────────────────────────────────────────────────┘

🔑 특징: 4개 LLM call이 *순차 의존* — 각자 role + system_prompt.
        AgentCore Memory가 step간 *컨텍스트 전달*.
        시연 가치 최강 (자율 multi-step orchestration 시연).
```

---

## 3. 도구별 dispatch 매트릭스 (시나리오 B 챗봇)

| Tool Name | 어느 service 호출 | 언제 호출되는가 |
|---|---|---|
| `search_bills` | **AOSS** (BM25+KNN+RRF) | 모든 질문 (default retrieval) |
| `get_proposers` | **Neptune** (PROPOSED edges) | 의안의 발의자 lookup |
| `cosponsor_network` | **Neptune** (CO_PROPOSED_WITH) | "공동발의" keyword |
| `analyze_votes` | **Neptune** (VOTED edges) | "표결" keyword |
| `get_influence_rank` | **Neptune** (`/api/insights/influence-rank`) | "영향력" keyword |
| `get_party_cohesion` | **Neptune** (`/api/insights/party-cohesion`) | "응집도" keyword |
| `get_swing_voters` | **Neptune** (`/api/insights/swing-voters`) | "swing" / "이탈" keyword |
| `district_member_lookup` | **member_directory** (286명 fixture) | "분당갑 의원" 같은 지역구 query |
| `member_journey_lookup` | **Neptune** (`/api/journey/{id}`) | "김은혜 이력" 같은 의원 이름 query |

→ **AgentCore = 도구 dispatcher**.
→ **LLM = 어느 도구 쓸지 판단**.
→ **OpenSearch / Neptune = 실제 데이터 store**.

---

## 4. 전체 architecture 흐름도

```
                        사용자 (브라우저)
                              │
                              ▼
                  CloudFront → ALB → FastAPI (ECS)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           AgentCore Runtime (Bedrock Converse API)              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Bedrock LLM (Sonnet 4.6)                                  │  │
│  │    - 사용자 query 이해                                     │  │
│  │    - 도구 선택 (tool_use 응답)                            │  │
│  │    - tool_result 받아 최종 답변 작성                       │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                          │                                       │
│                          ▼ tool_use dispatch                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Tool Registry (TOOL_SPECS)                                │  │
│  │   ┌─────────────────────┬──────────────────────────────┐  │  │
│  │   │ Text Tools          │ Graph Tools                   │  │  │
│  │   │ - search_bills      │ - get_proposers              │  │  │
│  │   │ - semantic_search   │ - cosponsor_network          │  │  │
│  │   │                     │ - analyze_votes              │  │  │
│  │   │                     │ - get_influence_rank         │  │  │
│  │   │                     │ - get_party_cohesion         │  │  │
│  │   │                     │ - get_swing_voters           │  │  │
│  │   │                     │ - member_journey_lookup      │  │  │
│  │   │                     │ - district_member_lookup     │  │  │
│  │   └──────────┬──────────┴─────────────┬────────────────┘  │  │
│  │              │                          │                   │  │
│  └──────────────│──────────────────────────│───────────────────┘  │
│                 │                          │                       │
│                 ▼                          ▼                       │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│  │  AgentCore Memory    │  │  AgentCore Code Interpreter      │  │
│  │  (session/long-term) │  │  (Firecracker microVM)           │  │
│  │  - 사용자 context    │  │  - matplotlib chart 생성          │  │
│  │  - 페르소나 prefs    │  │  - pandas analysis (시나리오 C·G) │  │
│  └──────────────────────┘  └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                 │                          │
                 ▼                          ▼
┌──────────────────────────┐  ┌──────────────────────────────────┐
│  OpenSearch Serverless   │  │  Amazon Neptune                   │
│  (AOSS)                  │  │  (Graph DB)                       │
│                          │  │                                    │
│  - 의안 텍스트 인덱스    │  │  - 74,249 real edges              │
│  - Nori (BM25)           │  │  - PROPOSED, CO_PROPOSED_WITH,    │
│  - Cohere embed-v4 (KNN) │  │    VOTED, MEMBER_OF, BELONGS_TO   │
│  - RRF fusion + rerank   │  │  - openCypher via boto3 SDK       │
│                          │  │                                    │
│  paradigm:               │  │  paradigm:                         │
│  "what is similar?"      │  │  "who connects to whom, and how?" │
└──────────────────────────┘  └──────────────────────────────────┘
```

---

## 5. 호출 처리 *3가지 시나리오별 trace*

### Case A: 텍스트 검색만 필요 ("AI 산업 진흥법 검색")

```
1. AgentCore → LLM: "tools=[search_bills, ...]"
2. LLM → AgentCore: tool_use(search_bills, {query: "AI 산업 진흥"})
3. AgentCore → AOSS: BM25+KNN+RRF+rerank
4. AOSS → AgentCore: top-10 의안 list
5. AgentCore → LLM: tool_result(10 items)
6. LLM → 사용자: "관련 의안 10건: ..." 자연어 답

호출: LLM 2회, AOSS 1회, Neptune 0회
```

### Case B: 관계 분석 필요 ("강경숙 ↔ 김기현 관계")

```
1. AgentCore → LLM: "tools=[...]"
2. LLM → AgentCore: tool_use(get_relation, {a: "강경숙", b: "김기현"})
3. AgentCore → Neptune:
   MATCH (pa)-[r1]-(b:Bill)-[r2]-(pb)
   + MATCH (pa)-[v1:VOTED]->(b)<-[v2:VOTED]-(pb)
   + MATCH (pa)-[:MEMBER_OF]->(c)<-[:MEMBER_OF]-(pb)
4. Neptune → AgentCore: metrics + narrative
5. AgentCore → LLM: tool_result(metrics)
6. LLM → 사용자: "강경숙(조국혁신당) ↔ 김기현(국민의힘) — ..."

호출: LLM 2회, AOSS 0회, Neptune 1~4회 (multi-query)
```

### Case C: Hybrid ("AI 의안에 누가 같이 참여했나?")

```
1. AgentCore → LLM: "tools=[...]"
2. LLM → AgentCore: tool_use(search_bills, {query: "AI"})
3. AgentCore → AOSS: 의안 top-K
4. AgentCore → LLM: tool_result(bills)
5. LLM → AgentCore: tool_use(cosponsor_network, {bill_id: B1})
6. AgentCore → Neptune: 공동발의자 cohort
7. AgentCore → LLM: tool_result(cohort)
8. LLM → 사용자: "AI 의안 5건 중 가장 협력한 의원은..."

호출: LLM 3회, AOSS 1회, Neptune 1회
```

---

## 6. 호출 비용·성능 특성

| Service | 호출 latency | 호출 비용 | 호출 빈도 |
|---|---|---|---|
| **Bedrock LLM** | 1-5초 (streaming) | 가장 비쌈 (input+output tokens) | 시나리오당 1-5회 |
| **AgentCore** | <50ms overhead | 무시 가능 | 모든 호출 통과 |
| **OpenSearch** | 50-200ms | 중간 (서버리스 OCU) | 시나리오 A·D·F·B Stage 1 |
| **Neptune** | 50-300ms (1-hop) | 중간 (DB instance) | 시나리오 K·M·O·T·U·V·W |

→ **LLM 호출 최소화가 성능·비용 최적화 핵심**.
   AgentCore의 tool_use 패턴은 *LLM이 자율 도구 선택*을 통해 *불필요한 LLM round-trip 회피*.

---

## 7. 호출 패러다임 비교

```
RAG paradigm:        Query → Retrieve → Generate
                     (LLM 1회, Store 1회)

Agent paradigm:      Query → LLM-decide-tool → Tool-execute → LLM-generate
                     (LLM 2-3회, Store N회)

Agentic paradigm:    Query → Planner → Graph → Analyst → Editor (multi-step LLM)
                     (LLM 4회+, Store N회, 자율 multi-step)
```

---

## 8. 핵심 정리

| 질문 | 답 |
|---|---|
| **AgentCore는 데이터를 가지나?** | ✗ (conductor 역할, 데이터는 AOSS/Neptune에 있음) |
| **LLM은 도구를 직접 호출하나?** | ✗ (LLM은 *어느 도구 쓸지만 응답*, AgentCore가 실제 호출) |
| **AOSS와 Neptune은 경쟁하나?** | ✗ (paradigm이 다름, 상호 보완) |
| **RAG는 어디 들어가나?** | OpenSearch retrieval pipeline (BM25+KNN+RRF+rerank) |
| **Agent와 RAG의 차이는?** | RAG는 *고정 흐름*, Agent는 *LLM이 도구 선택* |

---

## 9. 운영 모니터링 (옵저버빌리티)

| 모니터링 대상 | 위치 | 확인 방법 |
|---|---|---|
| LLM 호출 횟수·token 사용 | CloudWatch Bedrock metrics | `/aws/bedrock/anthropic.claude-sonnet-4-6` |
| Tool 호출 trace | `/api/ops` 운영 콘솔 | `_TRACE_BUF` 링버퍼 |
| AOSS query 지연 | CloudWatch OS Serverless | OCU 사용량 |
| Neptune query 지연 | CloudWatch Neptune metrics | `MainRequestQueuePendingRequests` |
| Guardrails 차단 발생 | CloudWatch Bedrock Guardrails | blocked count |
| political_balance_score | UI 노란 경고 + `/ops` alert | `< 0.8`이면 UI 표시 |

---

## 10. 시연 narrative 활용

본 호출 흐름은 *3단계 진화 비교*의 *기술적 backbone*입니다:

- **Stage 1 (RAG)**: AOSS만 호출 → 한계 즉시 노출
- **Stage 2 (Agent)**: AgentCore가 LLM↔Tool 반복 dispatch → 정확한 도구 자동 선택
- **Stage 3 (Agentic)**: 4 에이전트 자율 협업 → 자율 multi-step orchestration

→ 같은 질문에 *3가지 서로 다른 호출 패턴*이 *서로 다른 답*을 만들어내는 모습이
*PoC narrative의 시각적·체감적 climax*.
