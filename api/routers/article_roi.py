"""시나리오 G - 기사 ROI 라우터.

엔드포인트:
- GET /api/article-roi                 ROI 내림차순 페이징
- GET /api/article-roi/{article_id}    단일 기사 ROI 디테일 + 6 페르소나 KPI
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.services import article_roi_builder

router = APIRouter(prefix="/api/article-roi", tags=["article-roi"])


class RoiMetricsModel(BaseModel):
    cost_won: int
    reach_pv: int
    reach_share: int
    avg_dwell_sec: int
    conv_value_won: int
    roi_pct: float


class PersonaKpiModel(BaseModel):
    persona_id: str
    name_kr: str
    kpi_label: str
    kpi_value: str
    note: str


class RoiEntryModel(BaseModel):
    article_id: str
    title: str
    primary_topic: Optional[str] = None
    metrics: RoiMetricsModel
    persona_kpis: list[PersonaKpiModel]
    sources: list[str]


class RoiListResponse(BaseModel):
    persona_id: str
    total: int
    offset: int
    limit: int
    entries: list[RoiEntryModel]
    persona_note: str


class RoiDetailResponse(BaseModel):
    persona_id: str
    entry: RoiEntryModel
    extras: dict = Field(default_factory=dict)


def _to_entry_model(e: article_roi_builder.RoiEntry) -> RoiEntryModel:
    return RoiEntryModel(
        article_id=e.article_id,
        title=e.title,
        primary_topic=e.primary_topic,
        metrics=RoiMetricsModel(**e.metrics.__dict__),
        persona_kpis=[PersonaKpiModel(**k.__dict__) for k in e.persona_kpis],
        sources=list(e.sources),
    )


def _persona_note(pid: str) -> str:
    if pid == "editorial":
        return "ROI 상위 기사의 후속 취재 패턴 분석 - 재발견 의제 탐색."
    if pid == "data_ai":
        return "기사별 conv_value_won = 모델 lift × CTR 환산. dataset 입력으로 활용 가능."
    if pid == "ad_sales":
        return "reach_pv × 광고 CPM이 매출 직결. ROI 상위 기사의 인접 인벤토리 매칭 권장."
    if pid == "general_reader":
        return "기사들이 얼마나 많이 읽혔는지, 어떤 가치를 만들었는지 한눈에 볼 수 있어요."
    if pid == "paid_subscriber":
        return "ROI 상위 기사는 구독 가치가 높은 콘텐츠. PDF compilation 추천."
    if pid == "b2b":
        return "응답의 metrics.* 키로 자동 dashboard 통합 가능 (KRW unit 명시)."
    return ""


def _persona_extras(pid: str, entry: article_roi_builder.RoiEntry) -> dict:
    base = {}
    if pid == "editorial":
        base["follow_up_hint"] = (
            f"공유 {entry.metrics.reach_share}건 ↔ 잠재 후속 취재 ~{max(1, entry.metrics.reach_share // 50)}건."
        )
    elif pid == "ad_sales":
        base["ad_revenue_hint"] = (
            f"CPM 2000원 기준 광고 매출 ~{entry.metrics.reach_pv * 2 // 1000:,}천원."
        )
    elif pid == "paid_subscriber":
        base["premium_cta"] = (
            f"ROI {entry.metrics.roi_pct:.1f}% - top 기사 모음 PDF dossier (premium)"
        )
    elif pid == "b2b":
        base["api_response_hint"] = "metrics.conv_value_won은 KRW. 단위 변환 자동화 가능."
    return base


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("", response_model=RoiListResponse)
def list_roi(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> RoiListResponse:
    """ROI 내림차순 페이징."""
    pid = x_persona_id or "editorial"
    total, entries = article_roi_builder.list_roi(offset=offset, limit=limit)
    return RoiListResponse(
        persona_id=pid,
        total=total,
        offset=offset,
        limit=limit,
        entries=[_to_entry_model(e) for e in entries],
        persona_note=_persona_note(pid),
    )


@router.get("/{article_id}", response_model=RoiDetailResponse)
def get_roi(
    article_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> RoiDetailResponse:
    """단일 기사 ROI 디테일."""
    pid = x_persona_id or "editorial"
    entry = article_roi_builder.get_roi(article_id)
    if entry is None:
        raise HTTPException(404, f"기사 '{article_id}' 없음")
    return RoiDetailResponse(
        persona_id=pid,
        entry=_to_entry_model(entry),
        extras=_persona_extras(pid, entry),
    )
