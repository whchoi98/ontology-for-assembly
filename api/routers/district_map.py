"""시나리오 H - 지역구 지도 라우터.

엔드포인트:
- GET /api/district-map/summary       17 시도 stats (choropleth 데이터)
- GET /api/district-map/{sido_key}    단일 시도 디테일 (의원 리스트 + 활동 stats)

페르소나 차별:
- editorial: 후속 취재 hint
- data_ai: 데이터 분석 도구 추천
- ad_sales: 지역 광고 인벤토리 link
- general_reader: 친절한 안내
- paid_subscriber: PDF 지도 export
- b2b: GeoJSON 응답 hint
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.services import district_map_builder
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/district-map", tags=["district-map"])


class SidoStatsModel(BaseModel):
    key: str
    name_kr: str
    short_kr: str
    kostat_code: str
    grid_row: int
    grid_col: int
    member_count: int
    parties: dict[str, int]
    activity: dict[str, int]
    density_label: str


class SidoMemberModel(BaseModel):
    person_id: str
    name: str
    party: str
    district: str
    activity_summary: str


class SummaryResponse(BaseModel):
    persona_id: str
    total_members: int
    total_districts: int
    sido: list[SidoStatsModel]
    persona_hint: str


class DetailResponse(BaseModel):
    persona_id: str
    sido: SidoStatsModel
    members: list[SidoMemberModel]
    summary: str
    extras: dict = Field(default_factory=dict)


def _to_sido_stats_model(s: district_map_builder.SidoStats) -> SidoStatsModel:
    return SidoStatsModel(
        key=s.key, name_kr=s.name_kr, short_kr=s.short_kr,
        kostat_code=s.kostat_code, grid_row=s.grid_row, grid_col=s.grid_col,
        member_count=s.member_count, parties=s.parties, activity=s.activity,
        density_label=s.density_label,
    )


def _persona_hint(pid: str, persona: dict) -> str:
    """페르소나별 hint 메시지."""
    if pid == "editorial":
        return "지역구 활동 격차를 후속 취재. 발의 ↑·표결 일치율 ↓ 시도 추적 권장."
    if pid == "data_ai":
        return "시도별 stats CSV export 가능. 정당-시도 cross-tab 추가 분석 권장."
    if pid == "ad_sales":
        return "수도권(서울·경기·인천) 지역 광고 인벤토리 우선 매칭 권장."
    if pid == "general_reader":
        return "내 지역 의원의 활동을 한눈에 볼 수 있어요. 시도를 선택하면 상세."
    if pid == "paid_subscriber":
        return "17 시도 PDF 지도 + 정당 분포 표 다운로드 가능 (premium)."
    if pid == "b2b":
        return "GeoJSON 변환 시 properties.kostat_code로 join 가능."
    return ""


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> SummaryResponse:
    """17 시도 stats (choropleth 데이터)."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    sido_list = district_map_builder.build_summary()
    total_members = sum(s.member_count for s in sido_list)
    return SummaryResponse(
        persona_id=pid,
        total_members=total_members,
        total_districts=len(sido_list),
        sido=[_to_sido_stats_model(s) for s in sido_list],
        persona_hint=_persona_hint(pid, persona),
    )


@router.get("/{sido_key}", response_model=DetailResponse)
def get_detail(
    sido_key: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> DetailResponse:
    """단일 시도 디테일."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    detail = district_map_builder.build_detail(sido_key)
    if detail is None:
        raise HTTPException(404, f"시도 '{sido_key}' 미등록 (KOSTAT 17 시도 외)")

    extras = {"persona_name_kr": persona.get("name_kr", ""), "tone": persona.get("tone", "")}
    if pid == "editorial":
        extras["follow_up_hint"] = (
            f"{detail.sido.name_kr} 후속 취재: 발의 {detail.sido.activity.get('proposed', 0)}건 + "
            f"표결 {detail.sido.activity.get('voted', 0)}건 - 활성도 패턴 분석."
        )
    elif pid == "paid_subscriber":
        extras["premium_cta"] = f"{detail.sido.name_kr} 의원별 활동 비교 + PDF 보고서 (premium)"
    elif pid == "general_reader":
        extras["guide_hint"] = (
            f"{detail.sido.name_kr}에는 {detail.sido.member_count}명의 의원이 있어요. "
            "활동 요약을 클릭하면 더 자세한 정보를 볼 수 있어요."
        )
    elif pid == "b2b":
        extras["api_response_hint"] = "응답 JSON의 sido.kostat_code + activity 활용 가능."

    return DetailResponse(
        persona_id=pid,
        sido=_to_sido_stats_model(detail.sido),
        members=[
            SidoMemberModel(
                person_id=m.person_id, name=m.name, party=m.party,
                district=m.district, activity_summary=m.activity_summary,
            )
            for m in detail.members
        ],
        summary=detail.summary,
        extras=extras,
    )
