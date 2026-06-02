"""시나리오 J - 외부 신호 융합 라우터.

엔드포인트:
- GET /api/external-signal           3 패턴 fusion 목록 (필터: pattern)
- GET /api/external-signal/{id}      단일 fusion 디테일 + 시계열 + 페르소나 hint

페르소나 차별:
- editorial: 의제 형성/공론화 후속 취재
- data_ai: 모델링 입력 hint
- ad_sales: 토픽 lead time을 광고 캠페인에 활용
- general_reader: 친절한 비유
- paid_subscriber: PDF 트렌드 리포트
- b2b: 시계열 자동화 hint
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.services import signal_fusion_builder
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/external-signal", tags=["external-signal"])


class WeeklyPointModel(BaseModel):
    week_iso: str
    signal_count: int
    bill_count: int


class TopicFusionModel(BaseModel):
    fusion_id: str
    topic_id: str
    topic_name: str
    pattern: str
    pattern_label: str
    weeks: list[WeeklyPointModel]
    peak_signal_week: str
    peak_legislation_week: str
    lag_weeks: int
    correlation_hint: float
    narrative: str
    sources: list[str]


class ListResponse(BaseModel):
    persona_id: str
    scenario_code: str = "J"
    total: int
    pattern_filter: Optional[str] = None
    fusions: list[TopicFusionModel]
    persona_note: str


class DetailResponse(BaseModel):
    persona_id: str
    fusion: TopicFusionModel
    extras: dict = Field(default_factory=dict)


def _to_fusion_model(f: signal_fusion_builder.TopicFusion) -> TopicFusionModel:
    return TopicFusionModel(
        fusion_id=f.fusion_id,
        topic_id=f.topic_id,
        topic_name=f.topic_name,
        pattern=f.pattern,
        pattern_label=f.pattern_label,
        weeks=[WeeklyPointModel(**p.__dict__) for p in f.weeks],
        peak_signal_week=f.peak_signal_week,
        peak_legislation_week=f.peak_legislation_week,
        lag_weeks=f.lag_weeks,
        correlation_hint=f.correlation_hint,
        narrative=f.narrative,
        sources=list(f.sources),
    )


def _persona_note(pid: str) -> str:
    if pid == "editorial":
        return "외부 시그널 → 입법 lag 패턴은 의제 형성 단계의 사회 수요 forecast 도구."
    if pid == "data_ai":
        return "12주 시계열 + 패턴 라벨은 supervised classification model 학습 데이터로 활용 가능."
    if pid == "ad_sales":
        return "signal_leads 토픽은 시그널 정점 직전에 광고 캠페인 매칭이 유효."
    if pid == "general_reader":
        return "뉴스에서 화제 된 주제가 실제 입법으로 어떻게 이어지는지 12주 시계열로 볼 수 있어요."
    if pid == "paid_subscriber":
        return "3 패턴 비교 + 12주 PDF 트렌드 리포트 export 가능 (premium)."
    if pid == "b2b":
        return "응답의 weeks[].signal_count/bill_count로 자체 시계열 모델 입력 자동 추출 가능."
    return ""


def _persona_extras(pid: str, persona: dict, fusion: signal_fusion_builder.TopicFusion) -> dict:
    base = {
        "persona_name_kr": persona.get("name_kr", ""),
        "tone": persona.get("tone", ""),
    }
    if pid == "editorial":
        base["follow_up_hint"] = (
            f"후속 취재: {fusion.topic_name} - 시그널 정점({fusion.peak_signal_week}) → "
            f"입법 정점({fusion.peak_legislation_week}), lag {fusion.lag_weeks}주. "
            "lag 주간 동안의 정책 발언·위원회 활동 검증 권장."
        )
    elif pid == "data_ai":
        base["analysis_hint"] = (
            f"correlation hint {fusion.correlation_hint:.2f}는 PoC 정성 값. "
            "Production에서는 Granger causality test 권장."
        )
    elif pid == "paid_subscriber":
        base["premium_cta"] = (
            f"{fusion.topic_name} 12주 trend PDF + 다음 4주 forecast (premium)"
        )
    elif pid == "b2b":
        base["api_response_hint"] = "weeks 배열은 ISO 주차 sorted - 시계열 lib 바로 입력 가능."
    return base


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("", response_model=ListResponse)
def list_fusions(
    pattern: Optional[str] = Query(None, pattern=r"^(signal_leads|legislation_leads|decoupled)$"),
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ListResponse:
    """3 패턴 fusion 목록."""
    pid = x_persona_id or "editorial"
    fusions = signal_fusion_builder.list_fusions(pattern=pattern)
    return ListResponse(
        persona_id=pid,
        total=len(fusions),
        pattern_filter=pattern,
        fusions=[_to_fusion_model(f) for f in fusions],
        persona_note=_persona_note(pid),
    )


@router.get("/{fusion_id}", response_model=DetailResponse)
def get_fusion_detail(
    fusion_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> DetailResponse:
    """단일 fusion 디테일 + 페르소나 extras."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    f = signal_fusion_builder.get_fusion(fusion_id)
    if f is None:
        raise HTTPException(404, f"fusion '{fusion_id}' 없음")
    return DetailResponse(
        persona_id=pid,
        fusion=_to_fusion_model(f),
        extras=_persona_extras(pid, persona, f),
    )
