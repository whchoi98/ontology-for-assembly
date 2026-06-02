"""외부 신호 융합 builder - 시나리오 J.

외부 시그널(네이버 뉴스 + SNS + 여론조사) × 입법 활동의 시계열 융합 분석.
PoC에서는 3가지 narrative pattern 시연:
- signal_leads: 외부 시그널이 입법보다 앞섬 (의제 → 입법 형성)
- legislation_leads: 입법 후 외부 시그널 상승 (입법 → 공론화)
- decoupled: 양자 무관 (시그널 강해도 입법 없음, 또는 반대)

References:
- spec §3.1 시나리오 J
- data.external.naver_news, data.external.poll_result, data.external.sns_signal
- ADR-0004: 시그널 ↔ 입법 연결은 사실 기술만, 인과 단정 금지
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

__all__ = [
    "WeeklyPoint",
    "FusionPattern",
    "TopicFusion",
    "list_fusions",
    "get_fusion",
    "PATTERN_LABELS",
]


FusionPattern = Literal["signal_leads", "legislation_leads", "decoupled"]


PATTERN_LABELS: dict[FusionPattern, str] = {
    "signal_leads": "외부 시그널 선행 (의제 → 입법)",
    "legislation_leads": "입법 선행 (입법 → 공론화)",
    "decoupled": "비상관 (시그널·입법 독립)",
}


@dataclass(frozen=True)
class WeeklyPoint:
    """주간 데이터 1 포인트."""
    week_iso: str        # "2026-W08"
    signal_count: int    # 뉴스 + SNS + 여론조사 응답 통합
    bill_count: int      # 발의 + 공동발의 + 표결


@dataclass(frozen=True)
class TopicFusion:
    """토픽 1개의 외부-입법 시계열 + 패턴 라벨."""
    fusion_id: str
    topic_id: str
    topic_name: str
    pattern: FusionPattern
    pattern_label: str
    weeks: list[WeeklyPoint]
    peak_signal_week: str
    peak_legislation_week: str
    lag_weeks: int               # 양수면 signal이 lag주 앞섬, 음수면 입법이 앞섬
    correlation_hint: float      # -1 ~ 1 정성 점수 (PoC mock)
    narrative: str               # 한 문단 fact 기술
    sources: list[str] = field(default_factory=list)


# ─── 시드 패턴 ─────────────────────────────────────────────────────────────


def _week_iso(w: int) -> str:
    """W{n}이 2026 W{n} 형식. 12주 시리즈 = W04~W15."""
    return f"2026-W{w:02d}"


# Pattern 1: signal leads → AI 토픽 (예: W06에 뉴스 정점 → W10에 발의)
_AI_SERIES: tuple[WeeklyPoint, ...] = tuple(
    WeeklyPoint(_week_iso(w + 4), s, b)
    for w, (s, b) in enumerate([
        (32, 0), (54, 1), (87, 1), (142, 2), (98, 1), (76, 3),
        (52, 7), (38, 9), (29, 12), (24, 8), (22, 5), (18, 3),
    ])
)

# Pattern 2: legislation leads → 환경 토픽 (W08에 발의 → W12에 뉴스 정점)
_ENV_SERIES: tuple[WeeklyPoint, ...] = tuple(
    WeeklyPoint(_week_iso(w + 4), s, b)
    for w, (s, b) in enumerate([
        (12, 1), (16, 1), (14, 2), (18, 1), (22, 6), (28, 8),
        (45, 5), (78, 3), (112, 1), (98, 1), (76, 0), (52, 0),
    ])
)

# Pattern 3: decoupled → 문화 토픽 (시그널·입법 모두 변동 있지만 무관)
_CULTURE_SERIES: tuple[WeeklyPoint, ...] = tuple(
    WeeklyPoint(_week_iso(w + 4), s, b)
    for w, (s, b) in enumerate([
        (28, 2), (45, 1), (38, 3), (52, 1), (33, 2), (48, 4),
        (29, 1), (51, 2), (42, 3), (35, 1), (39, 2), (44, 2),
    ])
)


def _peak_week(series: tuple[WeeklyPoint, ...], key: str) -> str:
    """key='signal_count' 또는 'bill_count' 의 max week."""
    if key == "signal_count":
        return max(series, key=lambda p: p.signal_count).week_iso
    return max(series, key=lambda p: p.bill_count).week_iso


def _lag_weeks(series: tuple[WeeklyPoint, ...]) -> int:
    """signal_peak - legislation_peak (week index 기준).

    양수: 시그널이 입법보다 앞섬. 음수: 입법이 앞섬. 0: 동일.
    """
    weeks = [p.week_iso for p in series]
    sig_peak = _peak_week(series, "signal_count")
    bill_peak = _peak_week(series, "bill_count")
    return weeks.index(bill_peak) - weeks.index(sig_peak)


_FUSIONS: tuple[TopicFusion, ...] = (
    TopicFusion(
        fusion_id="fusion_ai_signal_leads",
        topic_id="topic_ai",
        topic_name="AI 산업 진흥",
        pattern="signal_leads",
        pattern_label=PATTERN_LABELS["signal_leads"],
        weeks=list(_AI_SERIES),
        peak_signal_week=_peak_week(_AI_SERIES, "signal_count"),
        peak_legislation_week=_peak_week(_AI_SERIES, "bill_count"),
        lag_weeks=_lag_weeks(_AI_SERIES),
        correlation_hint=0.78,
        narrative=(
            "AI 산업 진흥 토픽 - 외부 시그널 정점(W07, 142건)이 입법 정점(W12, 12건)을 "
            "약 5주 앞섰음. 의제 형성 단계의 사회적 수요가 입법으로 흡수되는 전형적 패턴. "
            "(출처: 네이버 뉴스 검색 + 합성 SNS + 합성 여론조사 + 국회 OpenAPI 본회의 발의 데이터)"
        ),
        sources=["네이버 뉴스", "합성 SNS", "합성 여론조사", "국회 OpenAPI"],
    ),
    TopicFusion(
        fusion_id="fusion_env_legislation_leads",
        topic_id="topic_environment",
        topic_name="환경·기후",
        pattern="legislation_leads",
        pattern_label=PATTERN_LABELS["legislation_leads"],
        weeks=list(_ENV_SERIES),
        peak_signal_week=_peak_week(_ENV_SERIES, "signal_count"),
        peak_legislation_week=_peak_week(_ENV_SERIES, "bill_count"),
        lag_weeks=_lag_weeks(_ENV_SERIES),
        correlation_hint=0.71,
        narrative=(
            "환경·기후 토픽 - 입법 정점(W09, 8건)이 외부 시그널 정점(W12, 112건)을 "
            "약 3주 앞섰음. 입법 발의가 공론장의 토론을 촉발한 패턴. "
            "(출처: 국회 OpenAPI 본회의 + 네이버 뉴스 + 합성 SNS)"
        ),
        sources=["국회 OpenAPI", "네이버 뉴스", "합성 SNS"],
    ),
    TopicFusion(
        fusion_id="fusion_culture_decoupled",
        topic_id="topic_culture",
        topic_name="문화·체육",
        pattern="decoupled",
        pattern_label=PATTERN_LABELS["decoupled"],
        weeks=list(_CULTURE_SERIES),
        peak_signal_week=_peak_week(_CULTURE_SERIES, "signal_count"),
        peak_legislation_week=_peak_week(_CULTURE_SERIES, "bill_count"),
        lag_weeks=_lag_weeks(_CULTURE_SERIES),
        correlation_hint=0.18,
        narrative=(
            "문화·체육 토픽 - 외부 시그널과 입법 활동 간 상관 미발견 (correlation 0.18). "
            "시그널 변동은 이벤트성(시상식·경기 등) 트리거, 입법은 별도 일정 진행. "
            "후속 분석: 정책 영역 특성에 따른 시그널-입법 결합도 차이 검증. "
            "(출처: 네이버 뉴스 + 국회 OpenAPI)"
        ),
        sources=["네이버 뉴스", "국회 OpenAPI"],
    ),
)


# ─── 공개 API ───────────────────────────────────────────────────────────────


def list_fusions(pattern: Optional[FusionPattern] = None) -> list[TopicFusion]:
    """토픽 시그널 융합 리스트. pattern으로 필터 가능."""
    if pattern is None:
        return list(_FUSIONS)
    return [f for f in _FUSIONS if f.pattern == pattern]


def get_fusion(fusion_id: str) -> Optional[TopicFusion]:
    """단일 fusion lookup."""
    return next((f for f in _FUSIONS if f.fusion_id == fusion_id), None)
