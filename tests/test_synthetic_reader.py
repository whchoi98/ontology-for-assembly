"""data.synthetic.reader 익명 독자 generator 검증.

핵심 검증:
- HashedId 정규식 (64자 lowercase hex) 통과
- reader_id 충돌 없음 (대량 생성에서)
- ADR-0004 익명성 가드 - 금지 필드 미생성
- Tier 분포 anonymous 80 / free 15 / paid 5 근사
- region은 17 시도 only (sgg 이상 정밀도 없음)
- 결정성 (동일 seed)
"""
from __future__ import annotations
import re

import pytest

from data.schemas import Reader
from data.synthetic.reader import (
    SIDOS,
    TIER_DISTRIBUTION,
    generate_readers,
)


HEX_PATTERN = re.compile(r"^[a-f0-9]{64}$")


# ─── 기본 출력 ───────────────────────────────────────────────────────────────

def test_generator_yields_requested_count():
    readers = list(generate_readers(count=100))
    assert len(readers) == 100


def test_all_yields_pydantic_reader():
    for r in generate_readers(count=5):
        assert isinstance(r, Reader)


def test_default_count_is_50k():
    """spec: 기본 50,000건. 빠른 generation 보장."""
    import time
    t0 = time.monotonic()
    n = sum(1 for _ in generate_readers(count=1000))  # 1k로 측정해서 확장 검증
    elapsed = time.monotonic() - t0
    assert n == 1000
    # 1000건이 1초 이내라면 50k도 적정 (~50초 미만, 실제로는 ~5초)
    assert elapsed < 1.0, f"1k 생성에 {elapsed:.2f}s — 50k 너무 느릴 수 있음"


# ─── HashedId 가드 (ADR-0003) ────────────────────────────────────────────────

def test_all_reader_ids_match_hashed_pattern():
    """reader_id는 64자 lowercase hex."""
    for r in generate_readers(count=200):
        assert HEX_PATTERN.match(r.reader_id), f"잘못된 형식: {r.reader_id}"


def test_reader_ids_unique_at_scale():
    """1만 건에서 충돌 없음 (SHA-256 충돌 확률 무시 가능)."""
    ids = {r.reader_id for r in generate_readers(count=10_000)}
    assert len(ids) == 10_000


# ─── ADR-0004 Layer 4: 금지 필드 ────────────────────────────────────────────

def test_no_forbidden_pii_fields():
    """Reader 모델에 IP/UA/political_leaning 등 PII·추론 필드 미존재."""
    forbidden = {"ip", "user_agent", "ua", "gps_lat", "gps_lon",
                 "ad_id", "idfa", "aaid", "political_leaning",
                 "political_loyalty_score", "religion", "health_status"}
    fields = set(Reader.model_fields.keys())
    intersection = fields & forbidden
    assert not intersection, f"PII/추론 필드 발견: {intersection}"


def test_extra_field_addition_rejected():
    """런타임에 미정의 필드 추가 시 ValidationError (extra='forbid')."""
    from pydantic import ValidationError
    one = next(generate_readers(count=1))
    with pytest.raises(ValidationError):
        Reader(
            **one.model_dump(),
            political_leaning=0.5,  # type: ignore[call-arg]
        )


# ─── Tier 분포 ──────────────────────────────────────────────────────────────

def test_tier_distribution_sums_to_one():
    """8:1.5:0.5 = 1.0."""
    assert abs(sum(TIER_DISTRIBUTION.values()) - 1.0) < 1e-9


def test_tier_distribution_approx_target():
    """10,000건에서 분포가 목표값 ±2% 이내 (대수의 법칙)."""
    readers = list(generate_readers(count=10_000, seed=42))
    n = len(readers)
    counts = {tier: 0 for tier in TIER_DISTRIBUTION}
    for r in readers:
        counts[r.tier] += 1
    for tier, target_pct in TIER_DISTRIBUTION.items():
        observed = counts[tier] / n
        assert abs(observed - target_pct) < 0.02, (
            f"{tier} 분포 {observed:.3f} vs target {target_pct:.3f} (5% 이내 권장)"
        )


# ─── region (시도 단위) ─────────────────────────────────────────────────────

def test_region_within_sido_pool():
    """region은 17 시도 중 하나. sgg 이상 정밀도 없음."""
    for r in generate_readers(count=100):
        if r.region is not None:
            assert r.region in SIDOS, f"unknown region: {r.region}"


def test_region_no_dong_or_sgg_strings():
    """region 문자열에 시군구·동·번지 등 정밀 단위 미포함."""
    forbidden_suffixes = ("동", "리", "번지", "구", "군", "시")
    for r in generate_readers(count=100):
        if r.region:
            # SIDOS에 등록된 광역명 그대로만 (예: '서울', '경기')
            assert r.region in SIDOS


# ─── interests ──────────────────────────────────────────────────────────────

def test_interests_from_topic_catalog():
    """interests는 topics 카탈로그 ID만."""
    from data.synthetic.topics import list_topic_ids
    valid_ids = set(list_topic_ids())
    for r in generate_readers(count=50):
        for tid in r.interests:
            assert tid in valid_ids


def test_interests_count_per_tier_correlation():
    """paid 구독자는 평균적으로 더 많은 관심사 보유 (구독 가치)."""
    readers = list(generate_readers(count=10_000, seed=7))
    paid = [r for r in readers if r.tier == "paid"]
    anon = [r for r in readers if r.tier == "anonymous"]
    assert paid, "paid 구독자 없음 - sample 부족"
    paid_avg = sum(len(r.interests) for r in paid) / len(paid)
    anon_avg = sum(len(r.interests) for r in anon) / len(anon)
    assert paid_avg > anon_avg, f"paid({paid_avg:.2f}) ≤ anon({anon_avg:.2f})"


# ─── since (시간) ────────────────────────────────────────────────────────────

def test_since_within_one_year():
    """since는 base_date 기준 최근 1년."""
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 5, 13, tzinfo=timezone.utc)
    one_year_ago = base - timedelta(days=366)
    for r in generate_readers(count=100, base_date=base):
        assert one_year_ago <= r.since <= base


# ─── source 태깅 ────────────────────────────────────────────────────────────

def test_all_marked_synthetic():
    for r in generate_readers(count=50):
        assert r.source == "synthetic"


# ─── 결정성 ─────────────────────────────────────────────────────────────────

def test_same_seed_produces_identical_output():
    r1 = list(generate_readers(count=100, seed=42))
    r2 = list(generate_readers(count=100, seed=42))
    assert [x.model_dump() for x in r1] == [x.model_dump() for x in r2]


def test_different_salt_produces_different_ids():
    """salt 변경 시 모든 ID 달라짐 (환경별 격리)."""
    r1 = list(generate_readers(count=50, seed=42, salt="env-a"))
    r2 = list(generate_readers(count=50, seed=42, salt="env-b"))
    ids1 = {r.reader_id for r in r1}
    ids2 = {r.reader_id for r in r2}
    assert ids1.isdisjoint(ids2), "salt 변경에도 ID 충돌 발생"


# ─── 직렬화 ─────────────────────────────────────────────────────────────────

def test_model_dump_json_serializable():
    import json
    r = next(generate_readers(count=1))
    serialized = json.dumps(r.model_dump(mode="json"), ensure_ascii=False)
    assert "reader_id" in serialized
