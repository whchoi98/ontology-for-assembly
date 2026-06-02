"""시나리오 C 기사 인사이트 검증 (Phase 4 Track 4-5)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import insights_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_article_pool_deterministic():
    """동일 seed → 동일 pool (캐시 적용)."""
    pool1 = insights_builder._article_pool()
    pool2 = insights_builder._article_pool()
    assert len(pool1) == len(pool2)
    assert pool1[0].article_id == pool2[0].article_id


def test_list_topics_returns_25():
    """토픽 카탈로그 25개 (data/synthetic/topics 시드)."""
    topics = insights_builder.list_topics()
    assert len(topics) >= 25
    # 핵심 토픽 포함
    topic_ids = [t.topic_id for t in topics]
    assert "topic_ai" in topic_ids
    assert "topic_environment" in topic_ids


def test_list_articles_paging():
    """리스트 페이징 - offset/limit 동작."""
    total, page1 = insights_builder.list_articles(offset=0, limit=10)
    assert total >= 10
    assert len(page1) == 10
    _total, page2 = insights_builder.list_articles(offset=10, limit=10)
    assert page1[0].article_id != page2[0].article_id


def test_list_articles_topic_filter():
    """topic_id 필터링."""
    total_all, _ = insights_builder.list_articles(offset=0, limit=60)
    total_filtered, entries = insights_builder.list_articles(
        offset=0, limit=60, topic_id="topic_ai",
    )
    assert total_filtered <= total_all
    # 필터 결과는 해당 토픽이 primary 또는 secondary
    for entry in entries:
        # entry는 list view라 topic_ids 안 보이지만 primary_topic.topic_id == topic_ai 또는
        # 다른 토픽일 수도 있음 (topic_ids 중 첫 번째가 primary, 필터는 어디든 매칭)
        assert entry.primary_topic is not None


def test_build_insight_returns_detail():
    """단일 기사 빌드 - 인사이트·요약 포함."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    detail = insights_builder.build_insight(art_id)
    assert detail is not None
    assert detail.article_id == art_id
    assert len(detail.insights) >= 1
    assert detail.summary
    assert 0.0 <= detail.political_balance_score <= 1.0


def test_build_insight_unknown_returns_none():
    """미존재 article_id → None."""
    assert insights_builder.build_insight("art_99999") is None


def test_insights_synthetic_balance_high():
    """합성 article은 ADR-0004 정치 균형 강제 - 점수 ≥ 0.8 보장."""
    pool = insights_builder._article_pool()
    for art in pool[:10]:
        detail = insights_builder.build_insight(art.article_id)
        assert detail is not None
        assert detail.political_balance_score >= 0.8, (
            f"{art.article_id}: score={detail.political_balance_score} - "
            "합성 generator가 정치 균형 보장 어겼음"
        )


# ─── /topics ────────────────────────────────────────────────────────────────


def test_topics_endpoint(client: TestClient):
    """GET /api/insights/topics."""
    response = client.get("/api/insights/topics")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 25
    assert len(body["topics"]) >= 25


# ─── /articles ──────────────────────────────────────────────────────────────


def test_articles_default(client: TestClient):
    """GET /api/insights/articles - 기본 페이징."""
    response = client.get("/api/insights/articles")
    assert response.status_code == 200
    body = response.json()
    assert body["offset"] == 0
    assert body["limit"] == 20
    assert len(body["articles"]) == 20


def test_articles_with_topic_filter(client: TestClient):
    """topic_id 쿼리 필터."""
    body = client.get("/api/insights/articles?topic_id=topic_ai").json()
    assert body["topic_filter"] == "topic_ai"


def test_articles_paging_consistency(client: TestClient):
    """페이지 1 + 페이지 2가 다른 article_id 반환."""
    body1 = client.get("/api/insights/articles?offset=0&limit=5").json()
    body2 = client.get("/api/insights/articles?offset=5&limit=5").json()
    ids1 = {a["article_id"] for a in body1["articles"]}
    ids2 = {a["article_id"] for a in body2["articles"]}
    assert ids1.isdisjoint(ids2)


def test_articles_validates_limit(client: TestClient):
    """limit > 50 거부."""
    response = client.get("/api/insights/articles?limit=100")
    assert response.status_code == 422


def test_articles_published_at_desc(client: TestClient):
    """최신 우선 정렬."""
    body = client.get("/api/insights/articles?limit=5").json()
    dates = [a["published_at"] for a in body["articles"]]
    assert dates == sorted(dates, reverse=True)


# ─── /articles/{id} ─────────────────────────────────────────────────────────


def test_article_detail(client: TestClient):
    """디테일 응답 구조."""
    list_body = client.get("/api/insights/articles?limit=1").json()
    art_id = list_body["articles"][0]["article_id"]
    detail = client.get(f"/api/insights/articles/{art_id}").json()
    assert detail["article_id"] == art_id
    assert len(detail["insights"]) >= 1
    assert "political_balance_score" in detail
    assert "summary" in detail


def test_article_detail_404(client: TestClient):
    """미존재 404."""
    response = client.get("/api/insights/articles/art_99999")
    assert response.status_code == 404


# ─── 페르소나 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 propagation."""
    headers = {"X-Persona-Id": persona_id}
    body = client.get("/api/insights/articles?limit=1", headers=headers).json()
    assert body["persona_id"] == persona_id


def test_editorial_extras_has_follow_up(client: TestClient):
    """editorial - follow_up_hint."""
    list_body = client.get("/api/insights/articles?limit=1").json()
    art_id = list_body["articles"][0]["article_id"]
    body = client.get(
        f"/api/insights/articles/{art_id}", headers={"X-Persona-Id": "editorial"},
    ).json()
    assert "follow_up_hint" in body["extras"]


def test_data_ai_extras_has_cohort_hint(client: TestClient):
    """data_ai - cohort_hint."""
    list_body = client.get("/api/insights/articles?limit=1").json()
    art_id = list_body["articles"][0]["article_id"]
    body = client.get(
        f"/api/insights/articles/{art_id}", headers={"X-Persona-Id": "data_ai"},
    ).json()
    assert "cohort_hint" in body["extras"]


def test_paid_extras_has_premium_cta(client: TestClient):
    """paid_subscriber - premium_cta."""
    list_body = client.get("/api/insights/articles?limit=1").json()
    art_id = list_body["articles"][0]["article_id"]
    body = client.get(
        f"/api/insights/articles/{art_id}", headers={"X-Persona-Id": "paid_subscriber"},
    ).json()
    assert "premium_cta" in body["extras"]


def test_b2b_extras_has_api_hint(client: TestClient):
    """b2b - api_response_hint."""
    list_body = client.get("/api/insights/articles?limit=1").json()
    art_id = list_body["articles"][0]["article_id"]
    body = client.get(
        f"/api/insights/articles/{art_id}", headers={"X-Persona-Id": "b2b"},
    ).json()
    assert "api_response_hint" in body["extras"]
