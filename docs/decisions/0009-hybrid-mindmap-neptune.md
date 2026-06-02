# ADR 0009 — Hybrid 마인드맵: depth=1 in-memory + depth≥2 Neptune

- Status: Accepted (구현 완료, 2026-05-15)
- Date: 2026-05-15
- Related: [[ADR-0001]] (gcc 아키텍처 차용), [[ADR-0006]] (공유 VPC + Neptune private subnet)

## Context

[[ADR-0008]]의 marketing demo 가치 (Public ALB 제거 + WAF + SSE) 와는 다른 축의 문제: **마인드맵 시각화가 진짜 graph traversal 인가, 아니면 Python dict iteration 인가?**

초기 구현(`api/routers/objects.py:_try_build_subgraph`)은:
- `objects_catalog.list_instances()`에서 fixture 받음
- `instance_data["proposer_id"]` 같은 *직접 reference field*만 따라감
- 1-hop subgraph만 가능 (depth ≥ 2는 frontend `dbltap` 누적으로 시뮬레이션)

문제 발견 (2026-05-15 시연 리허설):
1. 의원 마인드맵에서 *2-hop 협력 패턴* (예: A 의원과 자주 같이 발의하는 의원들의 또 다른 공동발의자) 확인 불가
2. 매 expand마다 backend 호출 (N-hop 조회에 N+1 round-trip)
3. *데이터 신선도*: `objects_catalog` 인-메모리 fixture는 서버 재시작 전까지 고정

Neptune은 이미 [[ADR-0001]]에서 채택, [[ADR-0006]] 공유 VPC private subnet에 배포, 265 nodes 적재 완료. 하지만 마인드맵 path에서 사용 안 함.

## Decision

**Hybrid 패턴 — depth 파라미터로 데이터 소스 분기**:

```
GET /api/objects/{class_name}/{instance_id}?depth=N
```

| depth | 소스 | latency | 사용 케이스 |
|---|---|---|---|
| `1` (default) | `objects_catalog` in-memory reference field 추적 | <5ms | 첫 화면 — 즉각 응답 |
| `2-3` | `services/neptune.open_cypher()` MATCH path *1..N | 50-300ms | 사용자 dbltap = "더 깊이 보고 싶다" 시그널 |
| `≥4` | 422 Pydantic validation error | - | unbounded traversal 방지 |

### 코드 분기

`api/routers/objects.py:get_object()`:
```python
if depth == 1:
    subgraph = _try_build_subgraph(class_name, instance_id, matched)
else:
    subgraph = _try_build_neptune_subgraph(class_name, instance_id, depth) \
        or _try_build_subgraph(class_name, instance_id, matched)  # fallback
```

Frontend `web/components/CytoscapeView.tsx:expandNode()`:
```typescript
// dbltap = "더 깊이 보고 싶다" 시그널 → depth=2
const resp = await fetch(`/api/objects/${typeSlug}/${nodeId}?depth=2`);
```

### Cypher query (안전망 적용)

```cypher
MATCH path = (root {id: $id})-[r:PROPOSED|CO_PROPOSED|VOTED|VOTE_ON|ABOUT|MENTIONS|REFERENCES|BELONGS_TO|CANDIDATE|CHOSE|OVERSEES*1..2]-(neighbor)
WHERE all(rel IN relationships(path) WHERE NOT type(rel) STARTS WITH '_internal_')
RETURN nodes(path) AS path_nodes, relationships(path) AS path_rels
LIMIT 50
```

3중 안전망:
1. **Relationship type whitelist** (`_SAFE_HOP_TYPES`): `MEMBER_OF` 의도적 제외 — 위원회 expand 폭발 (위원회당 ~15명) 회피
2. **Depth cap**: Pydantic `Query(ge=1, le=3)` 422 validation
3. **LIMIT 50**: 마인드맵 시각화 가독성 + Neptune 응답 크기 제한

### Fallback chain

```
depth≥2 요청
    ↓
Neptune open_cypher 시도
    ↓ (CypherError or empty)
in-memory _try_build_subgraph fallback
    ↓ (참조 없음)
None (subgraph 없음 → 노드만 표시)
```

`DEMO_PUBLIC_MODE=true`에서는 `neptune._demo_mode()`가 mock으로 응답 → 데모 안정성 보존.

## Trade-off 매트릭스

| 차원 | depth=1 (in-memory) | depth≥2 (Neptune) |
|---|---|---|
| 응답 지연 | <5ms | 50-300ms |
| Multi-hop 가능 | ✗ (frontend 누적 필요) | ✓ (path *1..N) |
| N-hop scaling | O(N×fetch) round-trip | O(1) 한 query |
| 데이터 신선도 | `objects_catalog` 재시작 전까지 고정 | data/load.py 적재 결과 즉시 |
| Scale ceiling | ~수천 노드 | 수억 노드 (r6g.large) |
| 비용 | $0 | $250/월 (r6g.large dev) |
| Demo failsafe | 항상 작동 | `DEMO_PUBLIC_MODE` mock fallback 필요 |
| Cypher injection | 무관 | `parameters={}` 키워드 강제 + type whitelist |

## 거부된 대안

### A. 항상 Neptune (depth=1도 Cypher)

- **장점**: 데이터 일관성 단순화
- **거부 이유**: 첫 화면 응답 latency 50-300ms → demo first impression 손해. PoC에서 "느린 페이지"는 narrative kill.

### B. 항상 in-memory (depth=N도 Python recursion)

- **장점**: 비용 0, 안정
- **거부 이유**: 진짜 graph DB 사용 시연 가치 손실. *"AWS Bedrock + AgentCore + Neptune"* PoC narrative에서 Neptune이 데이터 적재만 하고 query는 안 함 → 헛스택 인상.

### C. Neptune 전용 endpoint 분리 (`/api/graph/{id}?depth=N`)

- **장점**: 깔끔한 API 책임 분리
- **거부 이유**: 같은 객체에 대해 두 endpoint가 다른 응답 형식 반환 → frontend 라우팅 분기 추가 필요. PoC 단계에선 단일 endpoint + 파라미터가 단순.

## Validation

검증 결과 (2026-05-15):
```
depth=1: status=200 subgraph_nodes=2          (in-memory, ~3ms)
depth=2: status=200 subgraph_nodes=2          (Neptune mock or in-memory fallback)
depth=3: status=200                            (Neptune mock)
depth=4: status=422                            (Pydantic cap)
```

## 미해결 / 후속

1. **EXPLAIN 기반 query plan 최적화**: 데이터 100k+ 노드 적재 후 Cypher index 검토
2. **Neptune read replica**: 마인드맵 read-only path는 reader endpoint로 분리 가능 (현재 writer 단일)
3. **CloudWatch 메트릭**: depth≥2 호출 시 `neptune_query_duration_ms` 히스토그램 + `fallback_invoked_count`
4. **Frontend caching**: 같은 노드 dbltap 반복 시 IndexedDB cache (LRU 100 nodes)

## References

- 코드: `api/routers/objects.py:get_object`, `api/routers/objects.py:_try_build_neptune_subgraph`, `web/components/CytoscapeView.tsx:expandNode`
- Neptune wrapper: `api/services/neptune.py:open_cypher`
- Cypher 안전 패턴: `_SAFE_HOP_TYPES` whitelist + `LIMIT 50` + `Query(ge=1, le=3)`
