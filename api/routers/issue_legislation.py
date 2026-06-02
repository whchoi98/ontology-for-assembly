"""시나리오 N - 이슈×입법 상관 라우터.

엔드포인트:
- GET /api/issue-legislation              매트릭스 + top correlations + 페르소나 hint
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.services import issue_legislation_builder

router = APIRouter(prefix="/api/issue-legislation", tags=["issue-legislation"])


class ActivityIntensityModel(BaseModel):
    activity: str
    value: int
    intensity_label: str


class IssueRowModel(BaseModel):
    issue_id: str
    issue_name: str
    category: str
    activities: list[ActivityIntensityModel]
    dominant_activity: str


class CorrelationModel(BaseModel):
    issue_id: str
    issue_name: str
    activity: str
    intensity: int
    correlation_label: str
    insight: str


class MatrixResponse(BaseModel):
    persona_id: str
    activity_types: list[str]
    rows: list[IssueRowModel]
    top_correlations: list[CorrelationModel]
    sources: list[str]
    persona_note: str


def _persona_note(pid: str) -> str:
    if pid == "editorial":
        return "강한 결합 셀 (intensity≥80)은 후속 취재 우선 - 다른 활동 단계의 추적 가치."
    if pid == "data_ai":
        return "셀 강도를 정량 분석 입력으로 활용. Pearson 또는 점이 분포 분석 권장."
    if pid == "ad_sales":
        return "발의 강도가 높은 이슈는 광고 인접도가 높은 화제."
    if pid == "general_reader":
        return "어떤 주제가 어떤 형태의 입법 활동으로 이어지는지 한눈에 볼 수 있어요."
    if pid == "paid_subscriber":
        return "8×4 매트릭스 PDF 보고서 + 분기별 변화 trend export 가능 (premium)."
    if pid == "b2b":
        return "rows[].activities[].value로 4-vector 자동 추출 가능."
    return ""


@router.get("", response_model=MatrixResponse)
def get_matrix(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> MatrixResponse:
    """이슈×입법 매트릭스."""
    pid = x_persona_id or "editorial"
    matrix = issue_legislation_builder.build_matrix()
    return MatrixResponse(
        persona_id=pid,
        activity_types=list(issue_legislation_builder.ACTIVITY_TYPES),
        rows=[
            IssueRowModel(
                issue_id=r.issue_id,
                issue_name=r.issue_name,
                category=r.category,
                activities=[
                    ActivityIntensityModel(
                        activity=a.activity,
                        value=a.value,
                        intensity_label=a.intensity_label,
                    )
                    for a in r.activities
                ],
                dominant_activity=r.dominant_activity,
            )
            for r in matrix.rows
        ],
        top_correlations=[
            CorrelationModel(
                issue_id=c.issue_id,
                issue_name=c.issue_name,
                activity=c.activity,
                intensity=c.intensity,
                correlation_label=c.correlation_label,
                insight=c.insight,
            )
            for c in matrix.top_correlations
        ],
        sources=list(matrix.sources),
        persona_note=_persona_note(pid),
    )
