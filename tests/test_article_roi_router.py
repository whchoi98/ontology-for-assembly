"""시나리오 G 기사 ROI 검증 (Phase 4 Track 4-11)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import article_roi_builder, insights_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_list_roi_returns_all():
    """offset 0 + 큰 limit → 전체 풀."""
    total, entries = article_roi_builder.list_roi(offset=0, limit=100)
    pool_size = len(insights_builder._article_pool())
    assert total == pool_size
    assert len(entries) == pool_size


def test_list_roi_sorted_desc():
    """ROI 내림차순."""
    _, entries = article_roi_builder.list_roi(offset=0, limit=100)
    rois = [e.metrics.roi_pct for e in entries]
    assert rois == sorted(rois, reverse=True)


def test_get_roi_known():
    """기지 article_id."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    entry = article_roi_builder.get_roi(art_id)
    assert entry is not None
    assert entry.article_id == art_id
    assert len(entry.persona_kpis) == 6


def test_get_roi_unknown():
    """미존재 None."""
    assert article_roi_builder.get_roi("art_99999") is None


def test_metrics_deterministic():
    """같은 article_id에 대해 동일 metric (재현 가능)."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    e1 = article_roi_builder.get_roi(art_id)
    e2 = article_roi_builder.get_roi(art_id)
    assert e1 is not None and e2 is not None
    assert e1.metrics.cost_won == e2.metrics.cost_won
    assert e1.metrics.reach_pv == e2.metrics.reach_pv


def test_metrics_ranges():
    """모든 metric이 합리적 범위 안."""
    _, entries = article_roi_builder.list_roi(offset=0, limit=100)
    for e in entries:
        assert 80_000 <= e.metrics.cost_won <= 200_000
        assert 1_000 <= e.metrics.reach_pv <= 50_000
        assert 5 <= e.metrics.reach_share <= 500
        assert 30 <= e.metrics.avg_dwell_sec <= 240
        assert e.metrics.conv_value_won > 0


def test_persona_kpis_6():
    """모든 entry는 6 페르소나 KPI 보유."""
    _, entries = article_roi_builder.list_roi(offset=0, limit=10)
    for e in entries:
        pids = {k.persona_id for k in e.persona_kpis}
        assert pids == {
            "editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b",
        }


# ─── 라우터 ────────────────────────────────────────────────────────────────


def test_list_endpoint(client: TestClient):
    """GET /api/article-roi."""
    response = client.get("/api/article-roi")
    assert response.status_code == 200
    body = response.json()
    assert body["offset"] == 0
    assert body["limit"] == 20
    assert len(body["entries"]) == 20


def test_list_paging(client: TestClient):
    """페이지 별 다른 article_id."""
    body1 = client.get("/api/article-roi?offset=0&limit=10").json()
    body2 = client.get("/api/article-roi?offset=10&limit=10").json()
    ids1 = {e["article_id"] for e in body1["entries"]}
    ids2 = {e["article_id"] for e in body2["entries"]}
    assert ids1.isdisjoint(ids2)


def test_list_limit_validation(client: TestClient):
    """limit > 50 거부."""
    response = client.get("/api/article-roi?limit=100")
    assert response.status_code == 422


def test_detail_endpoint(client: TestClient):
    """GET /{article_id}."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    body = client.get(f"/api/article-roi/{art_id}").json()
    assert body["entry"]["article_id"] == art_id
    assert "extras" in body


def test_detail_404(client: TestClient):
    """미존재 404."""
    response = client.get("/api/article-roi/art_99999")
    assert response.status_code == 404


# ─── 페르소나 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 propagation + note 생성."""
    headers = {"X-Persona-Id": persona_id}
    body = client.get("/api/article-roi", headers=headers).json()
    assert body["persona_id"] == persona_id
    assert len(body["persona_note"]) > 0


def test_editorial_extras(client: TestClient):
    """editorial - follow_up_hint."""
    pool = insights_builder._article_pool()
    body = client.get(
        f"/api/article-roi/{pool[0].article_id}",
        headers={"X-Persona-Id": "editorial"},
    ).json()
    assert "follow_up_hint" in body["extras"]


def test_ad_sales_extras(client: TestClient):
    """ad_sales - ad_revenue_hint."""
    pool = insights_builder._article_pool()
    body = client.get(
        f"/api/article-roi/{pool[0].article_id}",
        headers={"X-Persona-Id": "ad_sales"},
    ).json()
    assert "ad_revenue_hint" in body["extras"]


def test_b2b_extras_includes_unit_hint(client: TestClient):
    """b2b - api_response_hint, KRW 단위 명시."""
    pool = insights_builder._article_pool()
    body = client.get(
        f"/api/article-roi/{pool[0].article_id}",
        headers={"X-Persona-Id": "b2b"},
    ).json()
    assert "api_response_hint" in body["extras"]
    assert "KRW" in body["extras"]["api_response_hint"]
