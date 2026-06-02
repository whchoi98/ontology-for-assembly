"""시나리오 F - 의원 룩어라이크 라우터.

엔드포인트:
- GET /api/lookalike/seeds              가능한 seed 의원 목록 (UI dropdown용)
- GET /api/lookalike/{person_id}        seed → top-k 유사 의원 + narrative

페르소나 차별:
- editorial: 공동발의 네트워크 후속 취재
- data_ai: production은 임베딩 vector + neptune kNN
- general_reader: "비슷한 활동을 하는 다른 의원"으로 친절 안내
- paid_subscriber: PDF 비교 리포트
- b2b: similarity 점수 자동화 가능
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.services import lookalike_builder
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/lookalike", tags=["lookalike"])


class LookalikeCandidateModel(BaseModel):
    person_id: str
    name: str
    party: str
    district: str
    similarity: float
    cluster_id: str
    cluster_label: str
    activity_score: float
    factors: list[str]
    cross_party_signal: bool


class LookalikeResultModel(BaseModel):
    persona_id: str
    seed_person_id: str
    seed_name: str
    seed_party: str
    seed_cluster_id: Optional[str] = None
    seed_cluster_label: Optional[str] = None
    candidates: list[LookalikeCandidateModel]
    narrative: str
    sources: list[str]
    extras: dict = Field(default_factory=dict)


class SeedListResponse(BaseModel):
    persona_id: str
    total: int
    seeds: list[dict]


def _to_candidate_model(c: lookalike_builder.LookalikeCandidate) -> LookalikeCandidateModel:
    return LookalikeCandidateModel(
        person_id=c.person_id,
        name=c.name,
        party=c.party,
        district=c.district,
        similarity=c.similarity,
        cluster_id=c.cluster_id,
        cluster_label=c.cluster_label,
        activity_score=c.activity_score,
        factors=list(c.factors),
        cross_party_signal=c.cross_party_signal,
    )


def _persona_extras(pid: str, persona: dict, result: lookalike_builder.LookalikeResult) -> dict:
    base = {
        "persona_name_kr": persona.get("name_kr", ""),
        "tone": persona.get("tone", ""),
    }
    cross_party = sum(1 for c in result.candidates if c.cross_party_signal)
    if pid == "editorial":
        base["follow_up_hint"] = (
            f"{result.seed_name} 의원의 유사 패턴 후보 중 {cross_party}명이 cross-party. "
            "공동발의 네트워크 + 위원회 공동 활동 추적 권장."
        )
    elif pid == "data_ai":
        base["analysis_hint"] = (
            "PoC는 결정적 score (cluster 0.6 + activity 0.3 + cross-party 0.1). "
            "Production은 Cohere embed-v4 의원 활동 vector + neptune kNN top-k."
        )
    elif pid == "paid_subscriber":
        base["premium_cta"] = (
            f"{result.seed_name} vs 유사 후보 {len(result.candidates)}명 "
            "다차원 비교 PDF (premium)"
        )
    elif pid == "b2b":
        base["api_response_hint"] = (
            "candidates[].similarity로 ranking 또는 임계 필터 자동화 가능."
        )
    return base


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("/seeds", response_model=SeedListResponse)
def list_seeds(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> SeedListResponse:
    """seed 의원 목록."""
    pid = x_persona_id or "editorial"
    seeds = lookalike_builder.list_seeds()
    return SeedListResponse(persona_id=pid, total=len(seeds), seeds=seeds)


@router.get("/{person_id}", response_model=LookalikeResultModel)
def get_lookalikes(
    person_id: str,
    top_k: int = Query(5, ge=1, le=15),
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> LookalikeResultModel:
    """seed 의원 → top-k 유사 의원."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    result = lookalike_builder.build_lookalikes(person_id, top_k=top_k)
    if result is None:
        raise HTTPException(404, f"의원 '{person_id}' 미등록 (cluster seeds 외)")

    return LookalikeResultModel(
        persona_id=pid,
        seed_person_id=result.seed_person_id,
        seed_name=result.seed_name,
        seed_party=result.seed_party,
        seed_cluster_id=result.seed_cluster_id,
        seed_cluster_label=result.seed_cluster_label,
        candidates=[_to_candidate_model(c) for c in result.candidates],
        narrative=result.narrative,
        sources=list(result.sources),
        extras=_persona_extras(pid, persona, result),
    )
