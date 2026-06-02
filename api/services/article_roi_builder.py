"""기사 ROI builder - 시나리오 G.

기사별 비용·도달·전환 metric + 페르소나별 KPI 변환. insights_builder의 합성 풀
재활용 - article_id별로 결정적 ROI 시뮬레이션.

PoC: hash 기반 결정적 metric (재현 가능). Production: 운영 메트릭 + 광고 매출
+ 구독 갱신 데이터 join.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from api.services import insights_builder

__all__ = [
    "RoiMetrics",
    "RoiEntry",
    "list_roi",
    "get_roi",
]


@dataclass(frozen=True)
class RoiMetrics:
    """단일 기사의 ROI 지표 집합."""
    cost_won: int             # 제작 비용 (KRW)
    reach_pv: int             # 페이지뷰
    reach_share: int          # 공유 수
    avg_dwell_sec: int        # 평균 체류 시간 (초)
    conv_value_won: int       # 전환 가치 (구독·광고·B2B 누적)
    roi_pct: float            # (conv - cost) / cost * 100


@dataclass(frozen=True)
class PersonaKpi:
    """페르소나별 KPI 1건."""
    persona_id: str
    name_kr: str
    kpi_label: str            # "후속 취재 건수", "광고 매출" 등
    kpi_value: str            # 사용자에게 표시할 값
    note: str                 # 해석 한 줄


@dataclass(frozen=True)
class RoiEntry:
    """1 기사의 ROI + 페르소나 KPI."""
    article_id: str
    title: str
    primary_topic: Optional[str]
    metrics: RoiMetrics
    persona_kpis: list[PersonaKpi]
    sources: list[str] = field(default_factory=list)


# ─── 결정적 metric 시뮬레이션 ─────────────────────────────────────────────


def _seed_from_id(article_id: str) -> int:
    """article_id → 결정적 정수 (시드)."""
    return sum(ord(c) for c in article_id)


def _compute_metrics(article_id: str, ref_persons: int, ref_bills: int) -> RoiMetrics:
    """ROI metric 결정적 계산.

    Returns:
        - cost_won: 80,000-200,000원 범위
        - reach_pv: 1,000-50,000
        - reach_share: 5-500
        - dwell: 30-240초
        - conv_value_won: 비용·도달의 함수
    """
    s = _seed_from_id(article_id)
    cost = 80_000 + (s % 121) * 1_000  # 80K - 200K
    pv = 1_000 + (s * 7) % 49_001         # 1K - 50K
    share = 5 + (s * 13) % 495            # 5 - 500
    dwell = 30 + (s * 17) % 211           # 30 - 240
    # 전환 가치: pv·share·참조 entity 수에 비례
    conv = int(
        pv * 8                            # PV * 단가 8원
        + share * 200                     # 공유당 200원
        + (ref_persons + ref_bills) * 4000  # 참조 entity별 4K (B2B 가치)
        + (dwell - 30) * 50               # 체류 시간 보너스
    )
    roi = ((conv - cost) / cost) * 100 if cost > 0 else 0.0
    return RoiMetrics(
        cost_won=cost, reach_pv=pv, reach_share=share, avg_dwell_sec=dwell,
        conv_value_won=conv, roi_pct=round(roi, 1),
    )


_PERSONA_NAMES = {
    "editorial": "편집국",
    "data_ai": "데이터·AI",
    "ad_sales": "광고 영업",
    "general_reader": "일반 독자",
    "paid_subscriber": "유료 구독자",
    "b2b": "B2B 고객",
}


def _persona_kpis_for(metrics: RoiMetrics) -> list[PersonaKpi]:
    """페르소나별 KPI 변환."""
    return [
        PersonaKpi(
            persona_id="editorial",
            name_kr=_PERSONA_NAMES["editorial"],
            kpi_label="후속 취재 가능 건수",
            kpi_value=f"~{max(1, metrics.reach_share // 50)} 건",
            note="공유 수 50건당 후속 취재 1건 발굴 가정.",
        ),
        PersonaKpi(
            persona_id="data_ai",
            name_kr=_PERSONA_NAMES["data_ai"],
            kpi_label="모델 학습 가치",
            kpi_value=f"{metrics.avg_dwell_sec * 7} 토큰-equiv",
            note="평균 체류 시간 × 7 = supervised feedback 토큰 equiv.",
        ),
        PersonaKpi(
            persona_id="ad_sales",
            name_kr=_PERSONA_NAMES["ad_sales"],
            kpi_label="광고 매출 (CPM 환산)",
            kpi_value=f"{metrics.reach_pv * 2 // 1000} 천원",
            note="PV * 2,000원/1000PV CPM 가정.",
        ),
        PersonaKpi(
            persona_id="general_reader",
            name_kr=_PERSONA_NAMES["general_reader"],
            kpi_label="공유율",
            kpi_value=f"{(metrics.reach_share / max(1, metrics.reach_pv)) * 100:.2f}%",
            note="공유 수 / PV.",
        ),
        PersonaKpi(
            persona_id="paid_subscriber",
            name_kr=_PERSONA_NAMES["paid_subscriber"],
            kpi_label="구독 전환 추정",
            kpi_value=f"{max(0, metrics.avg_dwell_sec // 60)} 명",
            note="체류 1분당 1명 구독 전환 가정 (PoC).",
        ),
        PersonaKpi(
            persona_id="b2b",
            name_kr=_PERSONA_NAMES["b2b"],
            kpi_label="API 호출 가치",
            kpi_value=f"{metrics.conv_value_won // 1000:,} 천원",
            note="conv_value_won의 1/1000 = API 라이센스 환산 (PoC).",
        ),
    ]


# ─── 공개 API ───────────────────────────────────────────────────────────────


def list_roi(*, offset: int = 0, limit: int = 20) -> tuple[int, list[RoiEntry]]:
    """ROI 내림차순 페이징."""
    pool = insights_builder._article_pool()
    entries: list[RoiEntry] = []
    for art in pool:
        m = _compute_metrics(
            art.article_id,
            ref_persons=len(art.referenced_person_ids),
            ref_bills=len(art.referenced_bill_ids),
        )
        primary_topic = None
        if art.topic_ids:
            t = insights_builder._topic_for(art.topic_ids[0])
            primary_topic = t.name if t else None
        entries.append(RoiEntry(
            article_id=art.article_id,
            title=art.title,
            primary_topic=primary_topic,
            metrics=m,
            persona_kpis=_persona_kpis_for(m),
            sources=["합성 article 풀", "결정적 ROI 시뮬레이션 (hash-seeded)"],
        ))
    entries.sort(key=lambda e: -e.metrics.roi_pct)
    return len(entries), entries[offset:offset + limit]


def get_roi(article_id: str) -> Optional[RoiEntry]:
    """단일 기사 ROI - 디테일."""
    pool = insights_builder._article_pool()
    art = next((a for a in pool if a.article_id == article_id), None)
    if art is None:
        return None
    m = _compute_metrics(
        art.article_id,
        ref_persons=len(art.referenced_person_ids),
        ref_bills=len(art.referenced_bill_ids),
    )
    primary_topic = None
    if art.topic_ids:
        t = insights_builder._topic_for(art.topic_ids[0])
        primary_topic = t.name if t else None
    return RoiEntry(
        article_id=art.article_id,
        title=art.title,
        primary_topic=primary_topic,
        metrics=m,
        persona_kpis=_persona_kpis_for(m),
        sources=["합성 article 풀", "결정적 ROI 시뮬레이션 (hash-seeded)"],
    )
