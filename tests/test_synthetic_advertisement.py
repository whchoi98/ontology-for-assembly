"""data.synthetic.advertisement Advertisement + AdInventory generator 검증.

핵심:
- 광고주별 avoid_topics 정합성 (카탈로그 ADVERTISER_PROFILES와 일치)
- AdInventory가 Advertisement.ad_id를 정확히 참조
- 예산이 광고주 카탈로그 범위 내
- target_personas는 광고 노출 정책 페르소나만 (general_reader / paid_subscriber)
- 결정성 (동일 seed)
"""
from __future__ import annotations
import pytest

from data.schemas import Advertisement, AdInventory
from data.synthetic.advertisement import (
    AD_TARGETABLE_PERSONAS,
    ADVERTISER_PROFILES,
    generate_ad_inventories,
    generate_ads_with_inventory,
    generate_advertisements,
)


# ─── Advertisement 기본 ──────────────────────────────────────────────────────

def test_generator_yields_requested_count():
    ads = list(generate_advertisements(count=20))
    assert len(ads) == 20


def test_default_count_is_500():
    """spec: 합성 광고 약 500건."""
    ads = list(generate_advertisements())
    assert len(ads) == 500


def test_all_yields_pydantic_advertisement():
    for a in generate_advertisements(count=5):
        assert isinstance(a, Advertisement)


def test_ad_id_unique():
    ids = [a.ad_id for a in generate_advertisements(count=200)]
    assert len(ids) == len(set(ids))


def test_ad_id_pattern():
    for a in generate_advertisements(count=5):
        assert a.ad_id.startswith("ad_")


def test_advertiser_from_catalog():
    catalog_names = {p.name for p in ADVERTISER_PROFILES}
    for a in generate_advertisements(count=50):
        assert a.advertiser in catalog_names


def test_category_consistent_with_advertiser():
    """광고주별 카테고리는 catalog와 일치 (1:1 매핑)."""
    profile_map = {p.name: p for p in ADVERTISER_PROFILES}
    for a in generate_advertisements(count=100):
        assert a.category == profile_map[a.advertiser].category


def test_avoid_topics_include_advertiser_defaults():
    """광고주 catalog의 avoid_topic_ids는 항상 포함."""
    profile_map = {p.name: p for p in ADVERTISER_PROFILES}
    for a in generate_advertisements(count=200):
        required_avoids = set(profile_map[a.advertiser].avoid_topic_ids)
        assert required_avoids.issubset(set(a.avoid_topics)), (
            f"{a.ad_id} ({a.advertiser}): catalog avoid 누락 "
            f"({required_avoids - set(a.avoid_topics)})"
        )


def test_content_summary_not_empty():
    for a in generate_advertisements(count=10):
        assert a.content_summary.strip()


def test_source_synthetic():
    for a in generate_advertisements(count=20):
        assert a.source == "synthetic"


# ─── AdInventory ─────────────────────────────────────────────────────────────

def test_inventory_one_to_one_with_ad():
    """1 광고 = 1 인벤토리."""
    ads, invs = generate_ads_with_inventory(count=30)
    assert len(ads) == len(invs)


def test_inventory_ad_id_references_existing_ad():
    """AdInventory.ad_id가 Advertisement.ad_id와 매칭."""
    ads, invs = generate_ads_with_inventory(count=50)
    ad_ids = {a.ad_id for a in ads}
    for inv in invs:
        assert inv.ad_id in ad_ids


def test_inventory_id_unique():
    ads, invs = generate_ads_with_inventory(count=100)
    inv_ids = [inv.inventory_id for inv in invs]
    assert len(inv_ids) == len(set(inv_ids))


def test_inventory_budget_positive():
    ads, invs = generate_ads_with_inventory(count=50)
    for inv in invs:
        assert inv.budget_krw > 0


def test_inventory_period_valid():
    ads, invs = generate_ads_with_inventory(count=50)
    for inv in invs:
        assert inv.period_end > inv.period_start


def test_inventory_budget_within_profile_range():
    """예산은 광고주 catalog 월 예산 × 기간 범위."""
    profile_map = {p.name: p for p in ADVERTISER_PROFILES}
    ads, invs = generate_ads_with_inventory(count=100)
    ad_map = {a.ad_id: a for a in ads}
    for inv in invs:
        ad = ad_map[inv.ad_id]
        profile = profile_map[ad.advertiser]
        min_monthly, max_monthly = profile.budget_range_krw
        # 1~12 개월이므로 total은 min_monthly × 1 ~ max_monthly × 12
        assert min_monthly * 1 <= inv.budget_krw <= max_monthly * 12


def test_inventory_target_personas_within_pool():
    """target_personas는 광고 노출 정책 페르소나만 (general_reader / paid_subscriber)."""
    ads, invs = generate_ads_with_inventory(count=100)
    valid = set(AD_TARGETABLE_PERSONAS)
    for inv in invs:
        for pid in inv.target_personas:
            assert pid in valid, f"{inv.inventory_id}: {pid}는 광고 타깃 불가"


def test_inventory_does_not_target_staff():
    """staff 페르소나(editorial/data_ai/ad_sales)는 광고 노출 없음 - target에 미포함."""
    ads, invs = generate_ads_with_inventory(count=200)
    staff_personas = {"editorial", "data_ai", "ad_sales", "b2b"}
    for inv in invs:
        assert staff_personas.isdisjoint(set(inv.target_personas)), (
            f"{inv.inventory_id}: staff·b2b 페르소나가 광고 타깃에 포함"
        )


# ─── 결정성 ─────────────────────────────────────────────────────────────────

def test_same_seed_produces_identical_advertisements():
    a1 = list(generate_advertisements(count=30, seed=42))
    a2 = list(generate_advertisements(count=30, seed=42))
    assert [x.model_dump() for x in a1] == [x.model_dump() for x in a2]


def test_same_seed_produces_identical_inventories():
    ads = list(generate_advertisements(count=30, seed=42))
    i1 = list(generate_ad_inventories(ads, seed=42))
    i2 = list(generate_ad_inventories(ads, seed=42))
    assert [x.model_dump(mode="json") for x in i1] == [x.model_dump(mode="json") for x in i2]


# ─── 카테고리 다양성 ────────────────────────────────────────────────────────

def test_multiple_categories_represented():
    """500건에서 최소 5개 카테고리 등장 (다양성)."""
    cats = {a.category for a in generate_advertisements(count=500)}
    assert len(cats) >= 5
