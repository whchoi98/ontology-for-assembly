---
name: cypher-conventions
description: openCypher conventions specific to this project — parameter passing, naming, performance, and the Assembly domain class/relationship taxonomy. Use when writing or reviewing Cypher queries in api/services/ or api/routers/.
---

# openCypher Conventions

## Parameter passing (Critical)

**Always** use keyword-only `parameters={...}`, never f-string interpolate user input:

```python
# ✅ 올바름
result = neptune.open_cypher(
    "MATCH (p:Person {assembly_id: $id})-[:PROPOSED]->(b:Bill) RETURN b",
    parameters={"id": person_id},
)

# ❌ Cypher injection 위험
result = neptune.open_cypher(
    f"MATCH (p:Person {{assembly_id: '{person_id}'}})-[:PROPOSED]->(b:Bill) RETURN b"
)
```

`api/services/neptune.py:open_cypher` signature는 `(query: str, *, parameters: dict | None = None)` — `parameters`는 keyword-only.

## Naming

- 노드 라벨: PascalCase (`Person`, `Bill`, `AdMatchDecision`).
- 관계 타입: SCREAMING_SNAKE_CASE (`PROPOSED`, `CO_PROPOSED`, `LIKELY_ALIGNED_WITH`).
- 변수: 짧고 명확하게 (`p`, `b`, `v` for person/bill/vote — 한 글자 OK in short queries).
- 파라미터: snake_case (`$person_id`, `$start_date`).

## 25+ 클래스 taxonomy (자주 쓰는 패턴)

```cypher
// 의원의 입법 활동 일대기
MATCH (p:Person {assembly_id: $id})
OPTIONAL MATCH (p)-[:PROPOSED]->(b:Bill)
OPTIONAL MATCH (p)-[:VOTED]->(v:Vote)-[:ON]->(b)
OPTIONAL MATCH (p)-[:SAID]->(s:Statement)
RETURN p, collect(distinct b) AS bills, collect(distinct v) AS votes, collect(distinct s) AS statements

// 공동발의 네트워크 1-hop
MATCH (p:Person {assembly_id: $id})-[:PROPOSED|CO_PROPOSED]->(b:Bill)<-[:CO_PROPOSED]-(other:Person)
WHERE p <> other
RETURN other, count(b) AS shared_bills
ORDER BY shared_bills DESC LIMIT 20

// 표결 일치율 (정당 간)
MATCH (p1:Person)-[:BELONGS_TO]->(:Party {name: $party1})
MATCH (p2:Person)-[:BELONGS_TO]->(:Party {name: $party2})
MATCH (p1)-[:VOTED {choice: $choice}]->(v:Vote)<-[:VOTED {choice: $choice}]-(p2)
RETURN count(v) AS agreement_count

// 광고 매칭 결정 trace
MATCH (a:Article {article_id: $aid})-[:CONSIDERED]->(d:AdMatchDecision)
RETURN d.mode, d.score, d.reason_text, d.chosen_ad_id
```

## Performance

- 큰 컬렉션은 `LIMIT` + `ORDER BY` 명시. unbounded `collect()` 금지.
- 1-hop 우선, 2-hop 이상은 명시적 path 변수 + `WHERE`.
- `OPTIONAL MATCH`로 nullable 관계 처리.
- 자주 조회되는 속성에 Neptune lookup index 활용 (e.g. `Person.assembly_id`).

## SSE streaming 패턴

장시간 쿼리는 `phase` SSE event로 진행 알림:

```python
async def cosponsor_network(person_id: str) -> AsyncIterator[SSEEvent]:
    yield {"type": "phase", "data": {"step": "fetch_proposed_bills"}}
    bills = await neptune.open_cypher("...", parameters={"id": person_id})
    yield {"type": "phase", "data": {"step": "fetch_cosponsors"}}
    # ...
    yield {"type": "final", "data": {"result": graph}}
```

## 금지 사항

- 사용자 입력 f-string interpolation (`f"... {user_input} ..."`)
- 라벨/관계 타입에 사용자 입력 (`MATCH (n:{user_label})` ← 금지)
- `MATCH (n) RETURN n` (전체 그래프 스캔, 모니터링 발견 즉시 중단)
- `*` 가변 길이 path 무제한 (`-[*]->`) — 항상 `-[*1..3]->` 등 상한
- `Reader.political_leaning` 등 정치 성향 추론 속성 생성·읽기 — SECURITY.md §3 위반

## 데이터 출처 필터링

페르소나·시나리오별 cohort 필터링:

```cypher
// 유료 구독자에게는 real source만
MATCH (b:Bill {source: 'real'})
WHERE b.proposed_date > $since
RETURN b

// 일반 독자에게는 모든 source 허용 (배지로 구분)
MATCH (b:Bill) RETURN b, b.source AS provenance
```

`api/services/cohort.py:select(persona_id, scenario_code)`의 결과를 항상 WHERE 절에 반영.
