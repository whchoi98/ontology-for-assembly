"""페르소나 SSOT 노출 라우터.

GET /api/personas       → 6 페르소나 메타 전체 (Sidebar·홈·GuidedTour가 fetch)
GET /api/personas/{id}  → 단일 페르소나 디테일

PERSONA_REGISTRY (api/services/persona.py)가 SSOT. 본 라우터는 read-only 노출.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services.persona import PERSONA_REGISTRY, TIER_GROUP_KR, TIER_GROUP_ORDER

router = APIRouter(prefix="/api/personas", tags=["personas"])


class PersonaDetailModel(BaseModel):
    persona_id: str
    name_kr: str
    tier: str
    tier_group_kr: str
    kpi_focus: list[str]
    tone: str
    scenario_priority: list[str]
    default_cohort: list[str]
    ad_policy: str
    system_prompt_suffix: str = Field(
        ...,
        description="LLM 호출 시 자동 첨부되는 어조·관심사 가이드 (NEUTRALITY_GUARD에 추가됨).",
    )


class PersonaGroupModel(BaseModel):
    tier: str
    tier_group_kr: str
    personas: list[PersonaDetailModel]


class PersonaListResponse(BaseModel):
    total: int
    personas: list[PersonaDetailModel]
    groups: list[PersonaGroupModel] = Field(
        default_factory=list,
        description="미디어/신문사 내부용·구독자용(무료)·유료 구독자용·B2B 4단 그룹화",
    )


def _to_model(persona_id: str) -> PersonaDetailModel:
    p = PERSONA_REGISTRY[persona_id]  # type: ignore[index]
    return PersonaDetailModel(
        persona_id=persona_id,
        name_kr=p["name_kr"],
        tier=p["tier"],
        tier_group_kr=TIER_GROUP_KR.get(p["tier"], p["tier"]),
        kpi_focus=list(p["kpi_focus"]),
        tone=p["tone"],
        scenario_priority=list(p["scenario_priority"]),
        default_cohort=list(p["default_cohort"]),
        ad_policy=p["ad_policy"],
        system_prompt_suffix=p["system_prompt_suffix"],
    )


@router.get("", response_model=PersonaListResponse)
def list_personas() -> PersonaListResponse:
    """6 페르소나 SSOT + tier 그룹 매핑 (UI 헤더 분리용)."""
    personas = [_to_model(pid) for pid in PERSONA_REGISTRY.keys()]
    groups: list[PersonaGroupModel] = []
    for tier in TIER_GROUP_ORDER:
        members = [m for m in personas if m.tier == tier]
        if members:
            groups.append(PersonaGroupModel(
                tier=tier, tier_group_kr=TIER_GROUP_KR[tier], personas=members,
            ))
    return PersonaListResponse(total=len(personas), personas=personas, groups=groups)


@router.get("/{persona_id}", response_model=PersonaDetailModel)
def get_persona(persona_id: str) -> PersonaDetailModel:
    """단일 페르소나 디테일."""
    if persona_id not in PERSONA_REGISTRY:
        raise HTTPException(
            404,
            f"persona '{persona_id}' 없음. 등록된 ID: {list(PERSONA_REGISTRY.keys())}",
        )
    return _to_model(persona_id)
