"""data.synthetic.article 기사 generator 검증.

검증 범위:
- 결정적 출력 (동일 seed → 동일 결과)
- Pydantic Article 모델 strict validation 통과
- source="synthetic" 강제
- 정치 균형 (양당 언급 시 빈도 균형)
- 출처 인용 포함
- 단정 가치 판단 표현 없음
"""
from __future__ import annotations
import pytest

from data.schemas import Article
from data.synthetic.article import (
    AUTHOR_POOL,
    BILL_ID_POOL,
    PERSON_ID_POOL,
    generate_articles,
)


# ─── 기본 출력 ───────────────────────────────────────────────────────────────

def test_generator_yields_requested_count():
    """count 인자만큼 정확히 생성."""
    articles = list(generate_articles(count=10))
    assert len(articles) == 10


def test_default_count_is_2000():
    """기본 2,000건 (spec)."""
    articles = list(generate_articles())
    assert len(articles) == 2000


def test_all_yields_pydantic_article():
    """모두 Pydantic Article 인스턴스."""
    for a in generate_articles(count=5):
        assert isinstance(a, Article)


# ─── source 태깅 ────────────────────────────────────────────────────────────

def test_all_articles_marked_synthetic():
    """DataSourceBadge 호환 - source="synthetic"."""
    for a in generate_articles(count=20):
        assert a.source == "synthetic"


# ─── 결정성 (deterministic) ──────────────────────────────────────────────────

def test_same_seed_produces_identical_output():
    """동일 seed → 동일 결과 (재현성)."""
    a1 = list(generate_articles(count=10, seed=42))
    a2 = list(generate_articles(count=10, seed=42))
    assert [x.model_dump() for x in a1] == [x.model_dump() for x in a2]


def test_different_seed_produces_different_output():
    """다른 seed → 다른 결과."""
    a1 = list(generate_articles(count=10, seed=42))
    a2 = list(generate_articles(count=10, seed=43))
    # 제목 중 적어도 하나는 달라야 함
    assert [x.title for x in a1] != [x.title for x in a2]


# ─── 필수 필드 ──────────────────────────────────────────────────────────────

def test_article_id_unique():
    """article_id 중복 없음."""
    ids = [a.article_id for a in generate_articles(count=100)]
    assert len(ids) == len(set(ids))


def test_article_id_pattern():
    """art_NNNNN 형식."""
    for a in generate_articles(count=5):
        assert a.article_id.startswith("art_")
        assert len(a.article_id) == 9  # art_ + 5자리


def test_title_not_empty():
    for a in generate_articles(count=5):
        assert a.title.strip()


def test_content_not_empty():
    for a in generate_articles(count=5):
        assert len(a.content) > 50  # 의미 있는 길이


def test_author_from_pool():
    for a in generate_articles(count=20):
        assert a.author in AUTHOR_POOL


def test_topic_ids_non_empty():
    """기사는 1-3개 토픽."""
    for a in generate_articles(count=20):
        assert 1 <= len(a.topic_ids) <= 3


def test_referenced_persons_within_pool():
    """참조 의원은 PERSON_ID_POOL 내부."""
    for a in generate_articles(count=20):
        for pid in a.referenced_person_ids:
            assert pid in PERSON_ID_POOL


def test_referenced_bills_within_pool():
    for a in generate_articles(count=20):
        for bid in a.referenced_bill_ids:
            assert bid in BILL_ID_POOL


# ─── 정치 중립성 (ADR-0004) ──────────────────────────────────────────────────

def test_content_has_source_citation():
    """모든 기사 본문에 출처 인용 포함."""
    for a in generate_articles(count=30):
        assert "출처:" in a.content or "OpenAPI" in a.content


def test_content_no_value_judgment():
    """단정 가치 판단 표현 미포함."""
    forbidden = ["잘못했다", "실패했다", "무능", "쓰레기", "엉터리"]
    for a in generate_articles(count=50):
        for word in forbidden:
            assert word not in a.content, f"{a.article_id}: '{word}' 포함"


def test_content_party_balance_when_mentioned():
    """양당이 언급된다면 빈도가 균형 (±2건 이내)."""
    import re
    pattern_dem = re.compile(r"더불어민주당\s*(\d+)건")
    pattern_ppp = re.compile(r"국민의힘\s*(\d+)건")
    for a in generate_articles(count=50, seed=99):
        m_dem = pattern_dem.search(a.content)
        m_ppp = pattern_ppp.search(a.content)
        if m_dem and m_ppp:
            n_dem = int(m_dem.group(1))
            n_ppp = int(m_ppp.group(1))
            assert abs(n_dem - n_ppp) <= 2, (
                f"{a.article_id}: 정당 균형 깨짐 ({n_dem} vs {n_ppp})"
            )


def test_political_balance_score_meets_threshold():
    """모든 기사가 guardrails 알람 임계(0.8) 통과."""
    from api.services.guardrails import political_balance_score, ALARM_THRESHOLD
    low_score = []
    for a in generate_articles(count=50, seed=7):
        score, _ = political_balance_score(a.content)
        if score < ALARM_THRESHOLD:
            low_score.append((a.article_id, score))
    assert not low_score, f"임계 미달 기사: {low_score[:3]}"


# ─── 시간 분포 ──────────────────────────────────────────────────────────────

def test_published_at_within_one_year():
    """기사 published_at은 base_date 기준 최근 1년 이내."""
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 5, 13, tzinfo=timezone.utc)
    one_year_ago = base - timedelta(days=366)
    for a in generate_articles(count=50, base_date=base):
        assert one_year_ago <= a.published_at <= base


# ─── Pydantic strict ────────────────────────────────────────────────────────

def test_model_dump_serializable():
    """JSON 직렬화 가능."""
    import json
    a = next(generate_articles(count=1))
    serialized = json.dumps(a.model_dump(mode="json"), ensure_ascii=False)
    assert serialized
