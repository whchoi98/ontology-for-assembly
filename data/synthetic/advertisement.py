"""합성 Advertisement + AdInventory generator - 시나리오 L (광고 매칭) 데이터.

설계 원칙:
1. 광고주별 `avoid_topics` 차별 - Agent 광고 매칭 판단에 실제 제약 부여.
   예) 핀테크는 사법·검찰 비위 콘텐츠 회피, 친환경은 국방 회피.
2. target_personas 다양화 - general_reader 위주 (B2C 광고가 무료 독자에 노출).
3. 예산은 한국 디지털 광고 시장 현실적 범위 (50만~5천만 원 월).

References:
- spec §3.4 시나리오 L 광고 매칭 매트릭스
- ADR-0004 Layer 6 (광고 매칭 거버넌스)
- data/synthetic/topics.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

from data.schemas import Advertisement, AdInventory
from data.synthetic.topics import list_topic_ids

__all__ = [
    "generate_advertisements",
    "generate_ad_inventories",
    "generate_ads_with_inventory",
    "ADVERTISER_PROFILES",
]


@dataclass(frozen=True)
class AdvertiserProfile:
    """광고주 프로파일 - 카테고리·회피 토픽·예산 범위 결정."""
    advertiser_id: str       # 익명 식별자 (예: adv_DATA_001)
    name: str                # 합성 회사명 (예: "데이터솔루션A")
    category: str            # 광고 카테고리
    avoid_topic_ids: tuple[str, ...]  # 명시 회피 토픽 (Agent가 참조)
    budget_range_krw: tuple[int, int]  # 월 예산 범위 (만 원 단위)


# 광고주 프로파일 - 합성 카탈로그.
# avoid_topics는 광고주별 평판 보호 정책: 평판 충돌 가능성이 큰 토픽.
ADVERTISER_PROFILES: tuple[AdvertiserProfile, ...] = (
    # 테크 (avoid_topics 최소)
    AdvertiserProfile("adv_DATA_001", "데이터솔루션A", "data_solutions",
                      (), (5_000_000, 50_000_000)),
    AdvertiserProfile("adv_DATA_002", "데이터솔루션B", "data_solutions",
                      (), (3_000_000, 30_000_000)),
    AdvertiserProfile("adv_CLOUD_001", "클라우드인프라A", "cloud",
                      (), (10_000_000, 80_000_000)),
    AdvertiserProfile("adv_SECURITY_001", "사이버보안A", "security",
                      ("topic_judicial",), (5_000_000, 40_000_000)),
    AdvertiserProfile("adv_COMP_001", "컴플라이언스A", "compliance",
                      ("topic_judicial",), (3_000_000, 25_000_000)),

    # 금융·핀테크 (사법·검찰 회피)
    AdvertiserProfile("adv_FIN_001", "핀테크A", "fintech",
                      ("topic_judicial", "topic_admin"), (8_000_000, 60_000_000)),
    AdvertiserProfile("adv_FIN_002", "은행B", "fintech",
                      ("topic_judicial",), (15_000_000, 100_000_000)),

    # 교육 (정치 민감 토픽 회피)
    AdvertiserProfile("adv_EDU_001", "에듀테크A", "education",
                      ("topic_judicial", "topic_defense", "topic_diplomacy"),
                      (2_000_000, 20_000_000)),

    # 친환경 (국방 회피)
    AdvertiserProfile("adv_GREEN_001", "친환경A", "sustainability",
                      ("topic_defense",), (3_000_000, 30_000_000)),
    AdvertiserProfile("adv_GREEN_002", "재생에너지A", "sustainability",
                      ("topic_defense",), (5_000_000, 40_000_000)),

    # 자동차 (국방 회피 - 군용 충돌)
    AdvertiserProfile("adv_AUTO_001", "자동차A", "automotive",
                      ("topic_defense",), (10_000_000, 80_000_000)),

    # 통신 (sgg·judicial 회피)
    AdvertiserProfile("adv_TEL_001", "통신사A", "telecom",
                      ("topic_judicial",), (15_000_000, 100_000_000)),

    # 헬스케어 (judicial 회피)
    AdvertiserProfile("adv_HC_001", "헬스케어A", "healthcare",
                      ("topic_judicial",), (4_000_000, 35_000_000)),

    # 광고대행사 (general 광고 - avoid 적음)
    AdvertiserProfile("adv_AGENCY_001", "광고대행A", "marketing",
                      (), (2_000_000, 20_000_000)),
)

# 광고 콘텐츠 요약 템플릿 (카테고리별).
CONTENT_TEMPLATES: dict[str, tuple[str, ...]] = {
    "data_solutions": (
        "기업 데이터 통합 솔루션 - {feature} 자동화",
        "데이터 분석 플랫폼 - 실시간 인사이트 제공",
    ),
    "cloud": (
        "엔터프라이즈 클라우드 인프라 - {feature} 최적화",
        "멀티 클라우드 관리 플랫폼",
    ),
    "security": (
        "사이버보안 솔루션 - 위협 탐지 자동화",
        "데이터 보안·암호화 통합 플랫폼",
    ),
    "compliance": (
        "규제 컴플라이언스 자동화 솔루션",
        "RegTech 플랫폼 - 보고서 자동 생성",
    ),
    "fintech": (
        "디지털 금융 서비스 - {feature} 간편 이용",
        "핀테크 플랫폼 - 통합 자산관리",
    ),
    "education": (
        "온라인 교육 플랫폼 - {feature} 학습 콘텐츠",
        "EdTech 솔루션 - 개인 맞춤형 학습",
    ),
    "sustainability": (
        "친환경 솔루션 - {feature} 탄소 감축",
        "재생에너지 서비스 - ESG 보고서 지원",
    ),
    "automotive": (
        "전기차 충전 인프라 - {feature} 네트워크",
        "스마트 모빌리티 서비스",
    ),
    "telecom": (
        "기업용 5G·통신 서비스 - {feature} 연결성",
        "통신 솔루션 - 클라우드 통합",
    ),
    "healthcare": (
        "헬스케어 플랫폼 - {feature} 건강 관리",
        "의료 데이터 서비스",
    ),
    "marketing": (
        "광고·마케팅 플랫폼 - {feature} 효율화",
        "디지털 마케팅 자동화",
    ),
}

FEATURE_WORDS: tuple[str, ...] = (
    "AI", "실시간", "통합", "스마트", "엔드투엔드", "자동화", "맞춤형", "엔터프라이즈",
)

# 페르소나 ID 풀 (광고가 노출 가능한 페르소나).
# editorial/data_ai/ad_sales는 내부 staff (no_ads), general_reader만 광고 노출 정책.
# 데모 데이터에서는 general_reader + paid_subscriber 일부를 타깃 (구독자도 광고 볼 수 있는 시나리오 가정).
AD_TARGETABLE_PERSONAS: tuple[str, ...] = ("general_reader", "paid_subscriber")


# ─── Advertisement generator ────────────────────────────────────────────────

def generate_advertisements(
    count: int = 500,
    seed: int = 20260513,
) -> Iterator[Advertisement]:
    """합성 Advertisement generator.

    Args:
        count: 광고 수.
        seed: RNG seed.

    Yields:
        Advertisement — Pydantic 검증된 광고 노드.
    """
    rng = random.Random(seed)
    topic_ids = list_topic_ids()

    for idx in range(count):
        profile = rng.choice(ADVERTISER_PROFILES)
        category = profile.category

        # 콘텐츠 요약 (카테고리별 템플릿)
        template = rng.choice(CONTENT_TEMPLATES[category])
        feature = rng.choice(FEATURE_WORDS)
        content_summary = template.format(feature=feature)

        # avoid_topics: 광고주 명시 회피 + 50% 확률로 추가 1개 (광고주 정책 강화)
        avoid_topics = list(profile.avoid_topic_ids)
        if rng.random() < 0.5:
            available = [t for t in topic_ids if t not in avoid_topics]
            if available:
                avoid_topics.append(rng.choice(available))

        yield Advertisement(
            ad_id=f"ad_{idx:04d}",
            advertiser=profile.name,
            category=category,
            content_summary=content_summary,
            avoid_topics=avoid_topics,
            source="synthetic",
        )


# ─── AdInventory generator ──────────────────────────────────────────────────

def generate_ad_inventories(
    advertisements: list[Advertisement],
    seed: int = 20260513,
    period_start: date | None = None,
) -> Iterator[AdInventory]:
    """광고 목록을 받아 AdInventory를 1:1 생성.

    Args:
        advertisements: 사전 생성된 Advertisement 리스트 (ad_id 참조).
        seed: RNG seed.
        period_start: 인벤토리 시작일 (None이면 2026-01-01).

    Yields:
        AdInventory — 광고당 1건 인벤토리 (budget, period, target_personas).
    """
    rng = random.Random(seed)
    start = period_start or date(2026, 1, 1)

    # advertiser → profile lookup
    profile_map = {p.name: p for p in ADVERTISER_PROFILES}

    for idx, ad in enumerate(advertisements):
        profile = profile_map.get(ad.advertiser)
        if profile is None:
            # advertiser 이름이 catalog 외라면 일반 범위 사용
            budget_min, budget_max = (1_000_000, 10_000_000)
        else:
            budget_min, budget_max = profile.budget_range_krw

        # 월 예산 → 캠페인 기간 1-12개월
        duration_months = rng.randint(1, 12)
        monthly_budget = rng.randint(budget_min, budget_max)
        total_budget = monthly_budget * duration_months

        period_end = start + timedelta(days=30 * duration_months)

        # 타깃 페르소나 1-2개 (B2C 광고)
        n_targets = rng.randint(1, len(AD_TARGETABLE_PERSONAS))
        target_personas = rng.sample(AD_TARGETABLE_PERSONAS, n_targets)

        yield AdInventory(
            inventory_id=f"inv_{idx:04d}",
            ad_id=ad.ad_id,
            budget_krw=total_budget,
            period_start=start,
            period_end=period_end,
            target_personas=target_personas,
            source="synthetic",
        )


# ─── 편의 helper ────────────────────────────────────────────────────────────

def generate_ads_with_inventory(
    count: int = 500,
    seed: int = 20260513,
    period_start: date | None = None,
) -> tuple[list[Advertisement], list[AdInventory]]:
    """광고 + 인벤토리를 한 번에 생성 (1:1 매칭 보장).

    Returns:
        (advertisements, inventories) - 같은 인덱스로 매핑된 두 리스트.
    """
    ads = list(generate_advertisements(count=count, seed=seed))
    invs = list(generate_ad_inventories(ads, seed=seed + 1, period_start=period_start))
    return ads, invs
