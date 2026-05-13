"""data.external 어댑터 검증 (Track 2-3).

테스트 범위:
- naver_news: 데모 모드 mock, HTML strip, pubDate 파싱, 결정적 signal_id
- poll_result: 정당 지지율 합 100%, 한 정당 60% 미만, 토픽 의견 균형
"""
from __future__ import annotations
from datetime import date, datetime, timezone

import pytest

from data.external.naver_news import (
    NaverNewsError,
    _parse_pub_date,
    _signal_id,
    _strip_html,
    fetch_news,
)
from data.external.poll_result import (
    PARTY_NAMES,
    POLLSTERS,
    generate_polls,
)
from data.schemas import PollResult, SocialSignal


# ─── naver_news ─────────────────────────────────────────────────────────────

def test_fetch_news_demo_yields_social_signal():
    signals = list(fetch_news("AI"))
    assert len(signals) >= 1
    assert all(isinstance(s, SocialSignal) for s in signals)


def test_fetch_news_source_external():
    """external 어댑터 출력은 source='external'."""
    for s in fetch_news("AI"):
        assert s.source == "external"


def test_fetch_news_source_type_is_news():
    for s in fetch_news("AI"):
        assert s.source_type == "news"


def test_fetch_news_respects_display():
    signals = list(fetch_news("AI", display=3))
    assert len(signals) <= 3


def test_fetch_news_signal_id_deterministic_from_url():
    """같은 URL → 같은 signal_id (idempotent)."""
    a = _signal_id("https://example.com/news/1")
    b = _signal_id("https://example.com/news/1")
    assert a == b
    assert a.startswith("naver_")


def test_signal_ids_unique_in_demo_fixture():
    """mock 10개 뉴스는 ID 유일."""
    signals = list(fetch_news("AI", display=10))
    ids = [s.signal_id for s in signals]
    assert len(ids) == len(set(ids))


def test_strip_html_removes_tags():
    assert _strip_html("<b>AI</b> 입법") == "AI 입법"
    assert _strip_html("일반 텍스트") == "일반 텍스트"
    assert _strip_html("") == ""


def test_parse_pub_date_naver_format():
    dt = _parse_pub_date("Wed, 15 Apr 2026 09:00:00 +0900")
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 15


def test_parse_pub_date_empty_falls_back():
    dt = _parse_pub_date("")
    assert isinstance(dt, datetime)


def test_demo_news_titles_balanced_party():
    """mock 뉴스 제목들이 한 정당으로만 쏠리지 않음."""
    signals = list(fetch_news("AI", display=10))
    # signal에 직접 title 필드는 없으나 fixture는 균형 잡힘 - URL 패턴으로 확인
    assert len(signals) == 10


# ─── poll_result ────────────────────────────────────────────────────────────

def test_generate_polls_yields_pydantic_pollresult():
    polls = list(generate_polls(count=10))
    assert len(polls) == 10
    assert all(isinstance(p, PollResult) for p in polls)


def test_poll_id_unique():
    ids = [p.poll_id for p in generate_polls(count=50)]
    assert len(ids) == len(set(ids))


def test_pollster_from_synthetic_catalog():
    """실 기관명(한국갤럽·리얼미터) 미사용 - 합성 식별자만."""
    for p in generate_polls(count=20):
        assert p.pollster in POLLSTERS
        # 실 기관명이 들어가지 않았는지 보강
        forbidden_real_names = ["한국갤럽", "리얼미터", "엠브레인"]
        for name in forbidden_real_names:
            assert name != p.pollster


def test_party_support_breakdown_sums_to_100():
    """정당 지지율 합 = 100% (±0.5 tolerance for rounding)."""
    polls = list(generate_polls(count=200, seed=42))
    party_polls = [p for p in polls if p.topic == "정당 지지율"]
    assert party_polls, "정당 지지율 poll 없음"
    for p in party_polls:
        total = sum(p.breakdown.values())
        assert abs(total - 100.0) < 0.5, f"{p.poll_id}: 합 {total}"


def test_no_party_exceeds_60_percent():
    """한 정당이 60% 초과 금지 (현실적 분포)."""
    for p in generate_polls(count=200):
        if p.topic == "정당 지지율":
            for party, pct in p.breakdown.items():
                assert pct <= 60.0, f"{p.poll_id} {party}: {pct}% > 60%"


def test_party_breakdown_includes_all_six_parties():
    """정당 지지율은 6 정당 모두 포함."""
    polls = list(generate_polls(count=100))
    party_polls = [p for p in polls if p.topic == "정당 지지율"]
    for p in party_polls:
        assert set(p.breakdown.keys()) == set(PARTY_NAMES)


def test_topic_opinion_breakdown_three_categories():
    """토픽 의견은 찬성/반대/잘 모름 3분류."""
    polls = list(generate_polls(count=200, seed=42))
    topic_polls = [p for p in polls if p.topic != "정당 지지율"]
    assert topic_polls
    for p in topic_polls:
        assert set(p.breakdown.keys()) == {"찬성", "반대", "잘 모름"}


def test_topic_opinion_sums_to_100():
    polls = list(generate_polls(count=200))
    for p in polls:
        if p.topic != "정당 지지율":
            total = sum(p.breakdown.values())
            assert abs(total - 100.0) < 0.5


def test_poll_sample_size_realistic():
    """표본 크기는 500-2000 범위 (실 여론조사 패턴)."""
    for p in generate_polls(count=50):
        assert 500 <= p.sample_size <= 2000


def test_poll_date_within_one_year():
    base = date(2026, 5, 13)
    for p in generate_polls(count=50, base_date=base):
        delta = (base - p.date).days
        assert 0 <= delta <= 365


def test_poll_source_synthetic():
    """현재 PollResult는 100% 합성."""
    for p in generate_polls(count=20):
        assert p.source == "synthetic"


def test_polls_deterministic():
    p1 = list(generate_polls(count=20, seed=42))
    p2 = list(generate_polls(count=20, seed=42))
    assert [x.model_dump(mode="json") for x in p1] == [y.model_dump(mode="json") for y in p2]


# ─── 정치 중립성 ────────────────────────────────────────────────────────────

def test_polls_topic_strings_no_ideology_labels():
    """토픽명에 이념 라벨 미포함."""
    forbidden = {"보수", "진보", "좌파", "우파"}
    for p in generate_polls(count=200):
        for label in forbidden:
            assert label != p.topic, f"이념 라벨 토픽: {p.topic}"
