"""api.services.opensearch hybrid_search 검증.

테스트 범위:
- DEMO_PUBLIC_MODE mock 결과
- top_k 제한 적용
- source_filter (cohort.select 결과) 적용
- 모든 hit이 source 태깅 + node_type
- SearchHit 모양 (id, score, source, title, snippet, node_type, metadata)
- 정치 중립성 (mock 응답에 정당 비방 없음)
"""
from __future__ import annotations
import pytest

from api.services import opensearch as os_svc


def test_hybrid_search_returns_list_of_hits():
    """hybrid_search → list[SearchHit]."""
    hits = os_svc.hybrid_search("AI 입법", top_k=10)
    assert isinstance(hits, list)
    assert all(isinstance(h, os_svc.SearchHit) for h in hits)


def test_hybrid_search_default_top_k():
    """기본 top_k=10."""
    hits = os_svc.hybrid_search("AI")
    assert len(hits) <= 10


def test_hybrid_search_respects_top_k_3():
    """top_k=3이면 최대 3개."""
    hits = os_svc.hybrid_search("AI", top_k=3)
    assert len(hits) <= 3


def test_hybrid_search_results_sorted_by_score_desc():
    """score 내림차순 정렬."""
    hits = os_svc.hybrid_search("AI 산업", top_k=10)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


# ─── SearchHit 모양 ──────────────────────────────────────────────────────────

def test_search_hit_required_fields():
    """SearchHit에 id, score, source, title, snippet, node_type 모두 있어야 한다."""
    hits = os_svc.hybrid_search("AI", top_k=1)
    assert len(hits) >= 1
    h = hits[0]
    assert h.id
    assert h.score >= 0.0
    assert h.source in ("real", "synthetic", "external")
    assert h.title
    assert isinstance(h.snippet, str)
    assert isinstance(h.metadata, dict)


def test_search_hit_node_type_diverse():
    """mock 결과에 다양한 node_type (Bill, Person, Article 등)."""
    hits = os_svc.hybrid_search("AI", top_k=10)
    node_types = {h.node_type for h in hits if h.node_type}
    # 최소 3종류 이상
    assert len(node_types) >= 3


# ─── source_filter (cohort 적용) ─────────────────────────────────────────────

def test_source_filter_real_only():
    """source_filter=['real'] → real source hit만."""
    hits = os_svc.hybrid_search("AI", top_k=10, source_filter=["real"])
    for h in hits:
        assert h.source == "real"


def test_source_filter_real_and_external():
    """source_filter=['real', 'external'] → real 또는 external."""
    hits = os_svc.hybrid_search("AI", top_k=10, source_filter=["real", "external"])
    for h in hits:
        assert h.source in ("real", "external")


def test_source_filter_none_returns_all_sources():
    """source_filter=None → 모든 source 반환."""
    hits = os_svc.hybrid_search("AI", top_k=10, source_filter=None)
    sources = {h.source for h in hits}
    # mock에 3종 모두 있으므로 적어도 2종 이상
    assert len(sources) >= 2


def test_source_filter_wildcard_returns_all():
    """source_filter=['*'] → no filter."""
    hits = os_svc.hybrid_search("AI", top_k=10, source_filter=["*"])
    sources = {h.source for h in hits}
    assert len(sources) >= 2


def test_source_filter_synthetic_only():
    """source_filter=['synthetic'] (예: 광고 매칭 시나리오)."""
    hits = os_svc.hybrid_search("AI", top_k=10, source_filter=["synthetic"])
    for h in hits:
        assert h.source == "synthetic"


# ─── 정치 중립성 (mock 내용) ────────────────────────────────────────────────

def test_mock_results_have_no_party_attack_text():
    """mock 응답에 정당 비방 결합 패턴이 없어야 한다 (ADR-0004)."""
    hits = os_svc.hybrid_search("정치", top_k=10)
    forbidden_combos = ["무능", "부패", "쓰레기", "악마"]
    for h in hits:
        for word in forbidden_combos:
            assert word not in h.title
            assert word not in h.snippet


# ─── 통합 (cohort 연동) ──────────────────────────────────────────────────────

def test_integration_with_cohort_select():
    """cohort.select() → hybrid_search source_filter 흐름."""
    from api.services import cohort
    # editorial 페르소나의 시나리오 K (real만)
    cohort_sources = cohort.select("editorial", "K")
    hits = os_svc.hybrid_search("표결", top_k=10, source_filter=cohort_sources)
    for h in hits:
        assert h.source == "real"


# ─── SearchError ────────────────────────────────────────────────────────────

def test_search_error_is_runtime_error():
    assert issubclass(os_svc.SearchError, RuntimeError)
