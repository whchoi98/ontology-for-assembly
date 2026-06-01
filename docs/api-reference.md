# API Reference

`ontology-for-assembly` FastAPI 백엔드의 23 시나리오(A–W) + 운영 라우터 참조. 21 라우터 wired (`api/main.py`). 시나리오 ≠ 라우터: P·Q·R·S는 전용 라우터 없이 `members.py` + 범용 `insight_generic.py`로 백킹.

모든 endpoint는 선택적 `X-Persona-Id` 헤더(`editorial` / `data_ai` / `ad_sales` / `general_reader` / `paid_subscriber` / `b2b`)를 받음. 미지정 시 `editorial` fallback. 페르소나는 응답의 `persona_id` 필드에 echo + 일부 endpoint에 `extras`·`persona_hint` 부가 정보 추가.

기본 URL: 로컬 `http://localhost:8080`, 배포 CloudFront `https://<dist>.cloudfront.net`.

## 헬스 체크

| Method | Path | 응답 |
|--------|------|------|
| GET | `/healthz` | `{"status":"ok","service":"ontology-for-assembly","version":"0.1.0"}` |
| GET | `/api/healthz` | `{"status":"ok","service":"api"}` |

## 시나리오 A — 의미 검색

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| POST | `/api/search` | `{"q":"AI 입법","top_k":5,"include_subgraph":false}` | `{"hits":[{title,snippet,score,...}],"subgraph":{"nodes":[],"edges":[]}}` |

OpenSearch BM25(Nori) + Cohere KNN + RRF fusion + Cohere rerank-v3.

## 시나리오 B — 3-stage 챗봇

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| POST | `/api/chat` | `{"query":"...","mode":"compare"}` | `{"results":{"chatbot":{...},"agent":{...},"agentic":{...}}}` |
| POST | `/api/chat/stream` | 동일 | SSE stream — events: `phase`/`log`/`result`/`done` (15 이벤트 sequence) |

3 stage(Chatbot RAG / Agent Tool Use / Agentic 4 에이전트) 사이드바이사이드 비교. 모든 stage 응답에 `political_balance_score` 자동 첨부.

## 시나리오 C — 기사 인사이트

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/insights/topics` | — | `{"topics":[{topic_id,name,category}]}` (25 시드) |
| GET | `/api/insights/articles` | query: `offset, limit, topic_id` | `{"articles":[...],"total":N,"topic_filter":...}` |
| GET | `/api/insights/articles/{article_id}` | path: `article_id` | `{summary, insights:[bullet x 3-5], political_balance_score, ...}` |

합성 article 풀(60건) + 토픽 필터링. published_at 내림차순. `@lru_cache(maxsize=1)` 결정적 풀.

## 시나리오 D — 페르소나 매칭

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/persona-match/matrix` | — | `{matrix, weights:{topic_affinity:0.6,kpi_keyword:0.25,tone_fit:0.15}}` |
| GET | `/api/persona-match/article/{article_id}` | path | `{scores:[{persona_id,score,topic_affinity,kpi_keyword_match,tone_fit,reasons}], top_persona_id, rationale}` |
| POST | `/api/persona-match/text` | `{"text":"...","topic_category_hints":["산업"]}` | 위와 동일 |

6 페르소나 × 6 카테고리 affinity 매트릭스(0-5). 가중 합 = topic_affinity(0.6) + kpi_keyword(0.25) + tone_fit(0.15). ad_sales는 balance≥0.95에서 만점 — 광고 안전성 우선.

## 시나리오 E — 의원 클러스터링

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/cluster` | — | `{clusters:[...], persona_note}` (5 cluster, coherence desc) |
| GET | `/api/cluster/{cluster_id}` | path | `{cluster:{members,parties_represented,cross_party_share,avg_activity,insight}, extras}` |

5 thematic cluster. 정파 기반 grouping 금지(ADR-0004) — 모든 cluster가 2+ 정당. `cross_party_share`로 정파 분산도 노출.

## 시나리오 F — 룩어라이크

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/lookalike/seeds` | — | `{seeds:[{person_id,name,party,district,cluster_label}]}` |
| GET | `/api/lookalike/{person_id}` | path + query: `top_k` (1-15) | `{seed_*, candidates:[{similarity,factors,cross_party_signal}], narrative, sources}` |

cluster match(0.6) + activity proximity(0.3) + cross-party bonus(0.1). same cluster + 다른 정당 = `cross_party_signal=true`.

## 시나리오 G — 기사 ROI

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/article-roi` | query: `offset, limit` | `{entries:[{metrics,persona_kpis}], total}` (ROI desc) |
| GET | `/api/article-roi/{article_id}` | path | `{entry:{metrics:{cost_won,reach_pv,reach_share,avg_dwell_sec,conv_value_won,roi_pct},persona_kpis x 6}}` |

Hash-seeded 결정적 ROI 시뮬레이션. 6 페르소나 KPI 변환 — 편집국(후속 취재 건수) / 데이터(학습 토큰) / 광고(CPM 매출) / 일반 독자(공유율) / 유료(구독 전환) / B2B(API 가치).

## 시나리오 H — 지역구 지도

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/district-map/summary` | — | `{sido:[{key,name_kr,kostat_code,grid_row,grid_col,member_count,parties,activity,density_label}], total_members}` |
| GET | `/api/district-map/{sido_key}` | path: `seoul/busan/...` | `{sido, members, summary, extras}` |

17 KOSTAT 시도 + 22대 254 지역구 분포 시드. `density_label`은 정성 4 tier만(정파 색 금지).

## 시나리오 I — 편향·중립성

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/neutrality/architecture` | — | `{layers:[{layer,name,where,description}], party_catalog, weights}` |
| GET | `/api/neutrality/samples` | — | `{samples:[{label:'낮음/중간/양호/우수',score,components}], threshold}` |
| POST | `/api/neutrality/score` | `{"text":"..."}` (10-4000자) | `{score, alarm, components, interpretation, blocked_topics}` |
| GET | `/api/neutrality/recent` | query: `limit` | `{traces:[...], counters:{total_invocations,avg_balance_score,...}}` |

ADR-0004 4-layer 가드레일 시연. `political_balance_score` 가중 합 — 정당 균형(0.5) + 인용(0.3) + 단정 표현 감점(0.2). 임계 0.8.

## 시나리오 J — 외부 신호 융합

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/external-signal` | query: `pattern` (signal_leads/legislation_leads/decoupled) | `{fusions:[...]}` |
| GET | `/api/external-signal/{fusion_id}` | path | `{fusion:{weeks[12],peak_signal_week,peak_legislation_week,lag_weeks,correlation_hint,narrative}, extras}` |

3 narrative 패턴 + 12주 시계열(W04-W15). lag_weeks 부호로 선후 관계 표시.

## 시나리오 K — 표결 이상치

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/outlier` | query: `limit, outlier_type` (party_line_break/swing_vote/cross_party) | `{outliers:[...], total, persona_note}` |
| GET | `/api/outlier/{outlier_id}` | path | `{outlier:{deviating_persons,deviation_score,ai_label,...}, extras}` |

3 이상치 유형, deviation_score 0.68-0.82 시드. `ai_label`에 정당 비방 어휘 금지(테스트 강제).

## 시나리오 L — 광고 매칭 매트릭스

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| POST | `/api/ad-match` | `{"article_id":"art_safe_normal","mode":"compare"}` | `{results:{keyword:{...},embedding:{...},agent:{...}}, governance_summary}` |

3-way 비교. Agent만 비위 의혹·비극·미성년 피해 콘텐츠에서 광고 거절(`chosen_ad_id=null`, reason starts with "skip"). 별도 Lambda(`AD_MATCH_MODE` env로 모드 전환).

## 시나리오 M — 의원 정치 여정

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/journey/persons` | — | `{available_persons:[{person_id,name,party,district,highlighted}]}` |
| GET | `/api/journey/{person_id}` | path | `{events:[{date,event_type,title,description,related_id}], stats, summary, extras}` |

5 event_type: `proposed/co_proposed/voted/statement/committee_join`. MONA_001(허브) 8 이벤트 + 기타 MONA_* 3 이벤트.

## 시나리오 N — 이슈 × 입법 상관

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/issue-legislation` | — | `{rows:[{issue_id,issue_name,activities[4]}], top_correlations[5], activity_types}` |

8 매크로 이슈 × 4 활동(proposed/voted/statements/committee_activity) heatmap. 셀에 정당 카운트 없음(ADR-0004 강제).

## 시나리오 O — 인물 관계 분석

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| GET | `/api/relations/{a}/{b}` | path: 두 인물 assembly_id | `{person_a, person_b, shared:{committees,bills,votes}, path, narrative}` |

두 의원 간 공유 위원회·공동 발의·표결 동조 등 그래프 관계 경로.

## 시나리오 P·Q·R·S — 범용 인사이트 (insight_generic)

| Method | Path | 입력 | 응답 |
|--------|------|------|------|
| POST | `/api/insight` | `{"slug":"committee-heatmap","context":{...}}` | `{summary, insights, political_balance_score, ...}` |

프론트 페이지(`petition-map`·`committee-heatmap`·`promise-tracker`·`topic-burst`)가 `members.py` 데이터를 가져온 뒤 slug별 focus 프롬프트로 LLM narrative 생성. context는 WAF 8KB 제한 대비 1–2KB trim 필수.

## 시나리오 T·U·V·W — 고급 인사이트 (insights_advanced)

| Method | Path | 응답 |
|--------|------|------|
| GET | `/api/insights/party-cohesion` | 정당별 표결 응집도 (real edges Cypher) |
| GET | `/api/insights/influence-rank` | 의원 영향력 랭킹 |
| GET | `/api/insights/voting-cluster` | 표결 패턴 cluster |
| GET | `/api/insights/swing-voters` | 정당 line 이탈 swing voter |

Phase 4f — 74K real Neptune edges 기반 Cypher 집계.

## 의원 디렉토리 (members)

| Method | Path | 응답 |
|--------|------|------|
| GET | `/api/members` | 의원 리스트 (286명 · 9 지표) |
| GET | `/api/members/ranking/{metric}` | 지표별 랭킹 |
| GET | `/api/members/{assembly_id}` | 의원 단일 정보 |
| GET | `/api/members/{assembly_id}/news` | 의원 관련 뉴스 |

## Object Explorer + Ontology 메타

| Method | Path | 응답 |
|--------|------|------|
| GET | `/api/ontology/classes` | 31 클래스 메타 (7 그룹) |
| GET | `/api/ontology/{class_name}` | 단일 클래스 메타 + 관계 |
| GET | `/api/objects/{class_name}` | 페이징 인스턴스 리스트 |
| GET | `/api/objects/{class_name}/{id}` | 단일 객체 + 1-hop subgraph |
| GET | `/api/objects/{class_name}/{id}/insight` | 객체 LLM 인사이트 |

15 구현 클래스 + 16 placeholder. subgraph는 참조 필드(proposer_id, bill_id, topic_ids 등)에서 자동 추론.

## 운영 콘솔

| Method | Path | 응답 |
|--------|------|------|
| GET | `/api/ops/ingest` | 데이터 적재 상태 |
| GET | `/api/ops/guardrail` | 가드레일 통계 (호출·차단·알람 누적) |
| GET | `/api/ops/memory` | AgentCore Memory 카운트 |
| GET | `/api/ops/wow-quality` | wow-eval 84 케이스 결과 (`.harness-eval/latest.json`) |
| GET | `/api/ops/trace` | 최근 LLM 호출 trace 링버퍼 |
| GET | `/api/personas` | `PERSONA_REGISTRY` SSOT — 6 페르소나 메타 |

## 공통 패턴

### 페르소나 헤더

```bash
curl -H "X-Persona-Id: editorial" http://localhost:8080/api/cluster
```

페르소나는 응답에 다음 영향:
- `persona_id` 필드 echo (모든 endpoint)
- `extras` / `persona_note` / `persona_hint` (시나리오별 부가 정보)
- 일부 시나리오는 페르소나에 따라 정렬·필터·hint 변경
- LLM 응답 어조(`system_prompt_suffix` 자동 첨부)

### SSE 이벤트 스키마

```
{"type":"phase","data":{"stage":"chatbot","start_ms":12}}
{"type":"log","data":{"tool":"search","args":{...}}}
{"type":"result","data":{"text":"...","political_balance_score":0.92}}
{"type":"done","data":{"total_ms":1543}}
```

### 정치 균형 점수

모든 LLM 호출 응답에 자동 첨부:

```json
{
  "political_balance_score": 0.85,
  "balance_components": {
    "party_mention_balance": 0.90,
    "citation_score": 1.0,
    "assertion_penalty": 0.80,
    "parties_mentioned": ["더불어민주당","국민의힘"],
    "total_party_mentions": 6,
    "citation_count": 3,
    "assertion_count": 1
  }
}
```

`< 0.8`일 경우 UI 노란색 경고 + 운영 콘솔 알람.

## 인증 (production)

- staff (editorial/data_ai/ad_sales): Cognito user pool JWT
- subscriber (paid_subscriber): Cognito user pool JWT (subscriber group)
- general_reader: Cognito Guest Identity Pool + 게스트 쿠키
- b2b: API Gateway Usage Plan + API Key (DynamoDB lookup)

위 인증은 **edge**(Lambda@Edge JWT + API Gateway Usage Plan/API Key)에서 강제된다. FastAPI 계층 자체에는 인증 미들웨어가 없으며 upstream을 신뢰한다(사실상 demo-public). 분기 정의는 `infra-cdk/lib/edge-stack.ts`.

## References

- 시나리오 narrative 디자인: [[ADR-0005]] Phase 4 Narrative Design Choices
- ADR-0004 가드레일 4-layer: `docs/decisions/0004-political-neutrality-guardrails.md`
- 페르소나 SSOT: `api/services/persona.py:PERSONA_REGISTRY`
- 시나리오 spec (base 14): `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` (구현은 23 시나리오 A–W로 확장)
