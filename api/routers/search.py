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
    """top hit 1-hop subgraph — objects.py의 합성 로직 재사용 (실제 값 채워짐).

    사용자 신고: search top-hit subgraph에 실제 값 안 나옴 (Neptune mock이 빈 list 반환).
    Fix: objects_catalog + member_directory의 실 데이터 + 합성 1-hop hop builder 사용.
    Bill→Person(발의자)/Topic/Article/Committee, Person→Bill/Committee/Vote/Topic 등 풍부화.
    """
    from api.routers.objects import _try_build_subgraph  # lazy: 순환 import 회피
    from api.services import objects_catalog, member_directory as md

    cls = top_hit.node_type or "Unknown"

    # objects_catalog에서 실 instance data 찾기
    matched: dict = {}
    if cls in ("Bill", "Person", "Vote", "Topic", "Article"):
        items, _ = objects_catalog.list_instances(cls, limit=500)
        meta = objects_catalog.get_class_meta(cls)
        id_field = meta.get("display", {}).get("id", "id")
        matched = next((it for it in items if str(it.get(id_field, "")) == top_hit.id), {})

    # Person fallback: member_directory에서 lookup
    if not matched and cls == "Person":
        m = md.get_member(md.resolve_id(top_hit.id))
        if m is not None:
            matched = {
                "source": "real",
                "assembly_id": m.assembly_id, "name": m.name,
                "party_id": m.party, "district_id": m.district,
                "profile_image_url": m.profile_image_url,
            }

    if not matched:
        # 최소 fallback — root node만
        return SubgraphModel(
            root_id=top_hit.id,
            nodes=[SubgraphNode(id=top_hit.id, label=cls,
                                data={"title": top_hit.title, "source": top_hit.source})],
            edges=[],
        )

    # objects.py의 합성 builder 재사용 (Bill/Topic/Vote/Person 모두 풍부 1-hop)
    sg = _try_build_subgraph(cls, top_hit.id, matched) or {
        "root_id": top_hit.id, "nodes": [], "edges": [],
    }
    return SubgraphModel(
        root_id=sg["root_id"],
        nodes=[SubgraphNode(id=n["id"], label=n["label"], data=n.get("data") or {})
               for n in sg["nodes"]],
        edges=[SubgraphEdge(source=e["source"], target=e["target"], type=e["type"])
               for e in sg["edges"]],
    )


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
