"""시나리오 E - 의원 클러스터링 라우터.

엔드포인트:
- GET /api/cluster          5 thematic 클러스터 (coherence 내림차순)
- GET /api/cluster/{id}     단일 cluster 디테일 + 페르소나 extras

ADR-0004: 정당 기반 클러스터링 금지. 토픽 활동 기반만. cross_party_share로
정파 분산도 노출 - cross-party 협력 cluster 발굴 narrative.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.services import cluster_builder
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/cluster", tags=["cluster"])


class ClusterMemberModel(BaseModel):
    person_id: str
    name: str
    party: str
    district: str
    activity_score: float


class ClusterEntryModel(BaseModel):
    cluster_id: str
    label: str
    dominant_topics: list[str]
    description: str
    member_count: int
    members: list[ClusterMemberModel]
    parties_represented: list[str]
    cross_party_share: float
    avg_activity: dict[str, float]
    coherence_score: float
    insight: str


class ClusterListResponse(BaseModel):
    persona_id: str
    total: int
    clusters: list[ClusterEntryModel]
    persona_note: str


class ClusterDetailResponse(BaseModel):
    persona_id: str
    cluster: ClusterEntryModel
    extras: dict = Field(default_factory=dict)


def _to_cluster_model(c: cluster_builder.ClusterEntry) -> ClusterEntryModel:
    return ClusterEntryModel(
        cluster_id=c.cluster_id,
        label=c.label,
        dominant_topics=list(c.dominant_topics),
        description=c.description,
        member_count=c.member_count,
        members=[
            ClusterMemberModel(
                person_id=m.person_id, name=m.name, party=m.party,
                district=m.district, activity_score=m.activity_score,
            )
            for m in c.members
        ],
        parties_represented=list(c.parties_represented),
        cross_party_share=round(c.cross_party_share, 3),
        avg_activity=dict(c.avg_activity),
        coherence_score=round(c.coherence_score, 3),
        insight=c.insight,
    )


def _persona_note(pid: str) -> str:
    if pid == "editorial":
        return "cluster cross_party_share가 높은 그룹은 협력 의제 발굴 후속 취재 가치 ↑."
    if pid == "data_ai":
        return (
            "활동 vector 임베딩 + K-means로 production 재현 가능. PoC는 thematic seed."
        )
    if pid == "ad_sales":
        return "데이터·AI 그룹과 경제·산업 그룹은 광고 인접도 높은 segment."
    if pid == "general_reader":
        return "같은 정당이라도 활동 패턴이 다르고, 다른 정당이라도 같이 활동하는 그룹이 있어요."
    if pid == "paid_subscriber":
        return "cluster별 의원 deep-dive PDF 보고서 + cross-cluster 비교 가능 (premium)."
    if pid == "b2b":
        return "cluster members[].activity_score는 ranking 기반 분석 입력으로 활용 가능."
    return ""


def _persona_extras(pid: str, persona: dict, cluster: cluster_builder.ClusterEntry) -> dict:
    base = {
        "persona_name_kr": persona.get("name_kr", ""),
        "tone": persona.get("tone", ""),
    }
    if pid == "editorial":
        base["follow_up_hint"] = (
            f"{cluster.label} cluster - cross_party_share {cluster.cross_party_share:.2f}, "
            f"멤버 {cluster.member_count}명. 후속 취재: 클러스터 내 공동발의 네트워크 추적."
        )
    elif pid == "paid_subscriber":
        base["premium_cta"] = (
            f"{cluster.label} 멤버 {cluster.member_count}명 PDF 보고서 + 의원 정치 여정 동시 export"
        )
    elif pid == "b2b":
        base["api_response_hint"] = (
            "cluster_id를 의원 정치 여정(/api/journey)·표결 이상치(/api/outlier) endpoint에 연결 가능."
        )
    return base


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("", response_model=ClusterListResponse)
def list_clusters(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ClusterListResponse:
    """5 thematic 클러스터 목록 (coherence 내림차순)."""
    pid = x_persona_id or "editorial"
    clusters = cluster_builder.list_clusters()
    return ClusterListResponse(
        persona_id=pid,
        total=len(clusters),
        clusters=[_to_cluster_model(c) for c in clusters],
        persona_note=_persona_note(pid),
    )


@router.get("/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster_detail(
    cluster_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ClusterDetailResponse:
    """단일 cluster 디테일."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    c = cluster_builder.get_cluster(cluster_id)
    if c is None:
        raise HTTPException(404, f"cluster '{cluster_id}' 없음")
    return ClusterDetailResponse(
        persona_id=pid,
        cluster=_to_cluster_model(c),
        extras=_persona_extras(pid, persona, c),
    )
