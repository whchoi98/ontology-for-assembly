"""시나리오 K - 표결 이상치 라우터.

엔드포인트:
- GET /api/outlier              이상치 목록 (deviation_score 내림차순)
- GET /api/outlier/{outlier_id} 단일 이상치 상세 + 정당 분포 메타

페르소나 차별:
- editorial: 후속 취재 포인트 강조
- data_ai: 통계 수치·CI 명시
- general_reader: 친절 설명
- paid_subscriber: 알림·심층
- b2b: JSON API

PDF 3페이지 시그니처 데모. 정치 균형 가드 자동 적용 - ai_label에 정당 비방 어휘 없음.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.services import outlier_detect
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/outlier", tags=["outlier"])


class DeviatingPersonModel(BaseModel):
    person_id: str
    name: str
    party: str
    choice: str
    reason_hint: Optional[str] = None


class OutlierEntryModel(BaseModel):
    outlier_id: str
    vote_id: str
    bill_id: str
    bill_title: str
    vote_date: str
    outlier_type: str
    label: str
    description: str
    deviation_score: float
    expected_pattern: str
    actual_pattern: str
    deviating_persons: list[DeviatingPersonModel]
    ai_label: str


class OutlierListResponse(BaseModel):
    persona_id: str
    scenario_code: str
    total: int
    outliers: list[OutlierEntryModel]
    persona_note: str


class OutlierDetailResponse(BaseModel):
    persona_id: str
    outlier: OutlierEntryModel
    extras: dict = Field(default_factory=dict)


# ─── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.get("", response_model=OutlierListResponse)
def list_outliers_endpoint(
    limit: int = Query(default=10, ge=1, le=50),
    outlier_type: Optional[Literal["party_line_break", "swing_vote", "cross_party"]] = None,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> OutlierListResponse:
    """이상치 목록 (페르소나별 안내 메시지 추가)."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    items = outlier_detect.list_outliers(limit=limit, outlier_type=outlier_type)
    return OutlierListResponse(
        persona_id=pid,
        scenario_code="K",
        total=len(items),
        outliers=[_to_model(o) for o in items],
        persona_note=_persona_note(pid, persona),
    )


@router.get("/{outlier_id}", response_model=OutlierDetailResponse)
def get_outlier_endpoint(
    outlier_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> OutlierDetailResponse:
    """단일 이상치 디테일."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    entry = outlier_detect.get_outlier(outlier_id)
    if entry is None:
        raise HTTPException(404, f"이상치 '{outlier_id}' 없음")
    return OutlierDetailResponse(
        persona_id=pid,
        outlier=_to_model(entry),
        extras={
            "persona_name_kr": persona.get("name_kr", ""),
            "follow_up_hint": _follow_up_hint(pid, entry),
        },
    )


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────

def _to_model(entry: outlier_detect.OutlierEntry) -> OutlierEntryModel:
    d = asdict(entry)
    return OutlierEntryModel(**d)


def _persona_note(persona_id: str, persona: dict) -> str:
    """페르소나별 화면 상단 안내."""
    hints = {
        "editorial": "후속 취재 포인트: deviation_score 높은 사안 우선. 정당 분열 보도는 자제.",
        "data_ai": "통계 메트릭: deviation_score, 정당별 일치율, swing margin. AI 라벨은 보조.",
        "ad_sales": "광고 매칭 주의: 정치 민감 표결은 Agent 광고 거절 trigger 가능.",
        "general_reader": "표결에서 의외의 결과를 보인 사례를 모았습니다. 정당 입장과 다르게 표결한 의원, 박빙으로 갈린 안건 등.",
        "paid_subscriber": "심층 분석 + 알림 설정 가능. 관심 의원 표결 이탈 시 알림.",
        "b2b": "API JSON 응답. deviation_score · party_breakdown · person_list 추출.",
    }
    return hints.get(persona_id, hints["editorial"])


def _follow_up_hint(persona_id: str, entry: outlier_detect.OutlierEntry) -> str:
    """페르소나별 후속 행동 제안."""
    if persona_id == "editorial":
        return (
            f"후속 취재: {entry.bill_title} 관련 의원 인터뷰. "
            "deviating_persons 목록의 reason_hint를 시작점으로."
        )
    if persona_id == "paid_subscriber":
        return "이 의원들을 '내 알림 목록'에 추가하면 향후 유사 표결 시 자동 알림."
    if persona_id == "b2b":
        return f"GET /api/outlier/{entry.outlier_id}.json (구조화 응답)"
    return f"deviation_score {entry.deviation_score:.2f} - 동일 카테고리 의안 추가 분석 권장."
