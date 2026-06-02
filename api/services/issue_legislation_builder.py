"""이슈×입법 상관 builder - 시나리오 N.

매크로 이슈(8개) × 입법 활동 유형(4개) 매트릭스 + 상관 강도 라벨링. 결과는 발의·
표결·발언·위원회 4 활동이 각 이슈에 얼마나 결합되는지의 시각화.

PoC: 결정적 시드 + intensity-based 정성 라벨. Production: pandas DataFrame +
실 의안 데이터 cross-tab.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ActivityIntensity",
    "IssueRow",
    "Correlation",
    "IssueLegislationMatrix",
    "build_matrix",
    "ACTIVITY_TYPES",
    "MACRO_ISSUES",
]


# 4 활동 유형 - 컬럼 헤더.
ACTIVITY_TYPES: tuple[str, ...] = ("proposed", "voted", "statements", "committee_activity")

# 8 매크로 이슈 - 행 헤더. data/synthetic/topics.py에서 합산·요약.
MACRO_ISSUES: tuple[tuple[str, str, str], ...] = (
    ("issue_ai_data", "AI·데이터 진흥", "산업"),
    ("issue_welfare", "사회복지·청년", "사회"),
    ("issue_finance", "금융·재정", "경제"),
    ("issue_environment", "환경·기후", "환경"),
    ("issue_industry", "산업·중소기업", "경제"),
    ("issue_health", "보건의료", "사회"),
    ("issue_legal", "법무·사법", "법무"),
    ("issue_culture", "문화·교육", "문화"),
)


# 정성 강도 라벨 (intensity → label).
def _intensity_label(value: int) -> str:
    if value >= 80:
        return "매우 높음"
    if value >= 50:
        return "높음"
    if value >= 25:
        return "보통"
    return "낮음"


@dataclass(frozen=True)
class ActivityIntensity:
    """1 활동 유형의 강도."""
    activity: str       # ACTIVITY_TYPES 중 1
    value: int          # 합산 카운트
    intensity_label: str  # "매우 높음" / "높음" / "보통" / "낮음"


@dataclass(frozen=True)
class IssueRow:
    """1 이슈의 4 활동 강도 row."""
    issue_id: str
    issue_name: str
    category: str
    activities: list[ActivityIntensity]
    dominant_activity: str  # 가장 높은 활동 유형


@dataclass(frozen=True)
class Correlation:
    """이슈 × 활동 상관 1건."""
    issue_id: str
    issue_name: str
    activity: str
    intensity: int
    correlation_label: str   # "강한 결합", "보통 결합", "약한 결합"
    insight: str


@dataclass(frozen=True)
class IssueLegislationMatrix:
    """매트릭스 전체."""
    rows: list[IssueRow]
    top_correlations: list[Correlation]
    sources: list[str] = field(default_factory=list)


# ─── 시드 매트릭스 (8 × 4) ─────────────────────────────────────────────────
# 정량은 22대 임기 분포 근사 - 합성 시드. ADR-0004: 정당 카운트 없음.
# rows × cols matrix: [이슈][활동] = intensity (0-100)

_MATRIX_SEED: dict[str, dict[str, int]] = {
    "issue_ai_data":     {"proposed": 89, "voted": 42, "statements": 67, "committee_activity": 78},
    "issue_welfare":     {"proposed": 62, "voted": 84, "statements": 58, "committee_activity": 71},
    "issue_finance":     {"proposed": 47, "voted": 68, "statements": 34, "committee_activity": 55},
    "issue_environment": {"proposed": 38, "voted": 31, "statements": 73, "committee_activity": 48},
    "issue_industry":    {"proposed": 54, "voted": 47, "statements": 41, "committee_activity": 62},
    "issue_health":      {"proposed": 41, "voted": 76, "statements": 52, "committee_activity": 68},
    "issue_legal":       {"proposed": 33, "voted": 89, "statements": 47, "committee_activity": 81},
    "issue_culture":     {"proposed": 24, "voted": 38, "statements": 28, "committee_activity": 32},
}


def _correlation_label(intensity: int) -> str:
    if intensity >= 80:
        return "강한 결합"
    if intensity >= 50:
        return "보통 결합"
    return "약한 결합"


def _build_correlation_insight(issue: str, activity: str, intensity: int) -> str:
    """top correlation 한 줄 인사이트."""
    activity_kr = {
        "proposed": "발의",
        "voted": "표결",
        "statements": "발언",
        "committee_activity": "위원회 활동",
    }.get(activity, activity)
    if intensity >= 80:
        return (
            f"{issue} 이슈가 {activity_kr} 단계에서 가장 활발 (intensity {intensity}). "
            "후속 분석: 같은 이슈 내 다른 활동 단계와의 시차."
        )
    return (
        f"{issue} 이슈의 {activity_kr} 결합 강도 보통 (intensity {intensity}). "
        "조합 분석으로 입법 라이프사이클 단계 식별 가능."
    )


def build_matrix() -> IssueLegislationMatrix:
    """전체 매트릭스 + top correlations."""
    rows: list[IssueRow] = []
    all_pairs: list[Correlation] = []

    for issue_id, issue_name, category in MACRO_ISSUES:
        activities_seed = _MATRIX_SEED.get(issue_id, {})
        activities = [
            ActivityIntensity(
                activity=act,
                value=activities_seed.get(act, 0),
                intensity_label=_intensity_label(activities_seed.get(act, 0)),
            )
            for act in ACTIVITY_TYPES
        ]
        dominant = max(activities, key=lambda a: a.value).activity
        rows.append(IssueRow(
            issue_id=issue_id,
            issue_name=issue_name,
            category=category,
            activities=activities,
            dominant_activity=dominant,
        ))

        for ai in activities:
            all_pairs.append(Correlation(
                issue_id=issue_id,
                issue_name=issue_name,
                activity=ai.activity,
                intensity=ai.value,
                correlation_label=_correlation_label(ai.value),
                insight=_build_correlation_insight(issue_name, ai.activity, ai.value),
            ))

    # top 5 강한 상관
    all_pairs.sort(key=lambda c: -c.intensity)
    top = all_pairs[:5]

    return IssueLegislationMatrix(
        rows=rows,
        top_correlations=top,
        sources=["합성 시드 (22대 임기 분포 근사)", "data/synthetic/topics.py 카탈로그"],
    )
