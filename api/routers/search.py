"""시나리오 A - 의안·의원 의미 검색 라우터.

엔드포인트:
- POST /api/search       BM25(Nori) + KNN(Cohere embed-v4) + RRF + rerank-v3
- GET  /api/search/info  검색 메타 (페르소나 cohort 정책 미리보기)

흐름:
1. cohort.select(persona_id, "A") → source 필터 결정
2. opensearch.hybrid_search(query, top_k, source_filter) 호출
3. top hit 1개에 대해 Neptune 1-hop subgraph 추출
4. 응답에 political_balance_score(이건 LLM 호출 없으면 균형 점수 자동 1.0) 첨부

페르소나 분기:
- 편집국: top_k=10, subgraph 포함
- 데이터·AI: top_k=20 (더 많은 후보), subgraph 포함
- 일반 독자: top_k=5 (입문성), subgraph 단순화
- 유료 구독자: top_k=15, subgraph 포함 + extras에 PDF export 진입점
- B2B: top_k=10, JSON 응답 우선

References:
- spec §3.1 시나리오 A
- ADR-0001 (gcc 검색 패턴 차용)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from api.services import cohort, neptune, opensearch
from api.services.persona import PERSONA_REGISTRY, get as get_persona

router = APIRouter(prefix="/api/search", tags=["search"])


# ─── Request/Response ───────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """POST /api/search 요청."""
    q: str = Field(min_length=1, max_length=500, description="검색어")
    top_k: int = Field(default=10, ge=1, le=50)
    include_subgraph: bool = Field(default=True, description="top hit 1-hop subgraph 포함")


class SearchHitModel(BaseModel):
    id: str
    score: float
    source: str
    title: str
    snippet: str
    node_type: str
    metadata: dict = Field(default_factory=dict)


class SubgraphNode(BaseModel):
    id: str
    label: str  # 노드 타입 (Bill, Person, ...)
    data: dict


class SubgraphEdge(BaseModel):
    source: str
    target: str
    type: str


class SubgraphModel(BaseModel):
    root_id: str
    nodes: list[SubgraphNode] = Field(default_factory=list)
    edges: list[SubgraphEdge] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    persona_id: str
    scenario_code: str
    cohort_used: list[str]
    hits: list[SearchHitModel]
    top_hit_subgraph: Optional[SubgraphModel] = None
    extras: dict = Field(default_factory=dict)


# ─── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("", response_model=SearchResponse)
def search(
    req: SearchRequest,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> SearchResponse:
    """하이브리드 검색 + 1-hop 그래프."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)

    # 페르소나별 top_k 조정
    adjusted_top_k = _adjust_top_k(pid, req.top_k)

    # 1. cohort 결정
    sources = cohort.select(pid, "A")

    # 2. 하이브리드 검색
    hits = opensearch.hybrid_search(
        req.q,
        top_k=adjusted_top_k,
        source_filter=sources,
    )

    # 3. top hit subgraph (요청 시)
    subgraph = None
    if req.include_subgraph and hits:
        top_hit = hits[0]
        subgraph = _build_subgraph(top_hit)

    # 4. 페르소나별 extras
    extras = _persona_extras(pid, persona, hits)

    return SearchResponse(
        query=req.q,
        persona_id=pid,
        scenario_code="A",
        cohort_used=sources,
        hits=[SearchHitModel(**vars(h)) for h in hits],
        top_hit_subgraph=subgraph,
        extras=extras,
    )


@router.get("/info")
def search_info(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> dict:
    """현재 페르소나의 검색 정책 미리보기."""
    pid = x_persona_id or "editorial"
    cohort_info = cohort.explain(pid, "A")
    return {
        "persona_id": pid,
        "scenario_code": "A",
        "default_top_k": _adjust_top_k(pid, 10),
        "cohort": cohort_info,
        "supported_node_types": ["Bill", "Person", "Article", "Statement", "SocialSignal"],
        "ranking": "BM25 (Nori) + KNN (Cohere embed-v4) + RRF + rerank-v3",
    }


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────

def _adjust_top_k(persona_id: str, requested_top_k: int) -> int:
    """페르소나별 top_k 조정.

    - 일반 독자: 입문성을 위해 작게
    - 데이터·AI: 분석 후보 풍부히
    - 그 외: 요청값 사용 (cap 50)
    """
    if persona_id == "general_reader":
        return min(requested_top_k, 5)
    if persona_id == "data_ai":
        return min(max(requested_top_k, 15), 50)
    return min(requested_top_k, 50)


def _build_subgraph(top_hit: opensearch.SearchHit) -> SubgraphModel:
    """top hit 1-hop subgraph 추출.

    노드 타입별 1-hop 패턴:
    - Bill: 발의자(Person), 토픽(Topic), 표결(Vote)
    - Person: 발의 법안(Bill), 위원회(Committee)
    - 기타: 빈 subgraph (확장 가능)
    """
    nodes: list[SubgraphNode] = []
    edges: list[SubgraphEdge] = []
    root_id = top_hit.id

    # 루트 노드
    nodes.append(SubgraphNode(
        id=top_hit.id,
        label=top_hit.node_type or "Unknown",
        data={"title": top_hit.title, "source": top_hit.source},
    ))

    if top_hit.node_type == "Bill":
        # 발의자(Person)
        person_rows = neptune.open_cypher(
            "MATCH (b:Bill {bill_id: $id})<-[:PROPOSED]-(p:Person) RETURN p LIMIT 3",
            parameters={"id": top_hit.id},
        )
        for row in person_rows:
            person = row.get("p", {})
            pid = person.get("assembly_id", "")
            if pid:
                nodes.append(SubgraphNode(
                    id=pid, label="Person",
                    data={"name": person.get("name", ""), "source": person.get("source", "real")},
                ))
                edges.append(SubgraphEdge(source=pid, target=top_hit.id, type="PROPOSED"))

        # 표결(Vote)
        vote_rows = neptune.open_cypher(
            "MATCH (b:Bill {bill_id: $id})<-[:VOTE_ON]-(v:Vote) RETURN v LIMIT 3",
            parameters={"id": top_hit.id},
        )
        for row in vote_rows:
            v = row.get("v", {})
            vid = v.get("vote_id", "")
            if vid:
                nodes.append(SubgraphNode(
                    id=vid, label="Vote",
                    data={"result": v.get("result", ""), "source": v.get("source", "real")},
                ))
                edges.append(SubgraphEdge(source=vid, target=top_hit.id, type="VOTE_ON"))

    elif top_hit.node_type == "Person":
        # 발의 법안(Bill) - 일반 mock 사용
        bill_rows = neptune.open_cypher(
            "MATCH (p:Person {assembly_id: $id})-[:PROPOSED]->(b:Bill) RETURN b LIMIT 3",
            parameters={"id": top_hit.id},
        )
        for row in bill_rows:
            b = row.get("b", {})
            bid = b.get("bill_id", "")
            if bid:
                nodes.append(SubgraphNode(
                    id=bid, label="Bill",
                    data={"title": b.get("title", ""), "source": b.get("source", "real")},
                ))
                edges.append(SubgraphEdge(source=top_hit.id, target=bid, type="PROPOSED"))

    return SubgraphModel(root_id=root_id, nodes=nodes, edges=edges)


def _persona_extras(persona_id: str, persona: dict, hits: list[opensearch.SearchHit]) -> dict:
    """페르소나별 응답 부가 정보 (UI에 표시할 진입점·도움말)."""
    extras = {
        "persona_name_kr": persona.get("name_kr", ""),
        "tone": persona.get("tone", ""),
        "ad_policy": persona.get("ad_policy", "no_ads"),
    }
    if persona_id == "general_reader":
        extras["guide_hint"] = "관련해서 더 알고 싶다면 '내 지역구 의원' 검색을 시도해보세요."
    elif persona_id == "paid_subscriber":
        extras["premium_cta"] = "PDF 리포트로 받기 (구독자 전용)"
    elif persona_id == "data_ai":
        extras["analytics_hint"] = "후보 풀이 확장됨 (top_k≥15) - 분포·통계 분석 가능."
    elif persona_id == "b2b":
        extras["api_response_hint"] = "구조화된 JSON 응답. 추가 필드는 /v1/search/extended."
    elif persona_id == "ad_sales":
        extras["coverage"] = f"검색 결과 {len(hits)}건 - 광고 매칭 후보군 확보."
    return extras
