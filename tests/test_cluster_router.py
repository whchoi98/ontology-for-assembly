"""시나리오 E 의원 클러스터링 검증 (Phase 4 Track 4-8).

ADR-0004: 정당 기반 클러스터링 금지 확인 - cross_party_share > 0 강제.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import cluster_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_list_clusters_returns_5():
    """5 thematic cluster seed."""
    clusters = cluster_builder.list_clusters()
    assert len(clusters) == 5


def test_clusters_sorted_by_coherence_desc():
    """coherence 내림차순 정렬."""
    clusters = cluster_builder.list_clusters()
    scores = [c.coherence_score for c in clusters]
    assert scores == sorted(scores, reverse=True)


def test_all_clusters_have_members():
    """모든 cluster는 1+ 멤버."""
    for c in cluster_builder.list_clusters():
        assert c.member_count == len(c.members)
        assert c.member_count >= 1


def test_member_activity_scores_in_range():
    """activity_score 0-1 범위."""
    for c in cluster_builder.list_clusters():
        for m in c.members:
            assert 0.0 <= m.activity_score <= 1.0


def test_all_clusters_have_dominant_topics():
    """dominant_topics 1+ 포함."""
    for c in cluster_builder.list_clusters():
        assert len(c.dominant_topics) >= 1


def test_adr_0004_clusters_cross_party():
    """ADR-0004 - 모든 cluster는 cross_party_share > 0 (단일 정당 cluster 금지)."""
    for c in cluster_builder.list_clusters():
        assert c.cross_party_share > 0, (
            f"{c.cluster_id} - cross_party_share=0은 ADR-0004 위반 가능"
        )


def test_all_clusters_have_2plus_parties():
    """각 cluster는 2+ 정당 멤버 보유 (cross-party 협력 narrative)."""
    for c in cluster_builder.list_clusters():
        assert len(c.parties_represented) >= 2, (
            f"{c.cluster_id} - {len(c.parties_represented)}개 정당만"
        )


def test_get_cluster_known():
    """기지 ID lookup."""
    c = cluster_builder.get_cluster("cluster_ai_data")
    assert c is not None
    assert "AI" in c.label or "데이터" in c.label


def test_get_cluster_unknown():
    """미존재 None."""
    assert cluster_builder.get_cluster("cluster_nope") is None


# ─── 라우터 ────────────────────────────────────────────────────────────────


def test_list_endpoint(client: TestClient):
    """GET /api/cluster."""
    response = client.get("/api/cluster")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["clusters"]) == 5
    assert len(body["persona_note"]) > 0


def test_list_clusters_response_schema(client: TestClient):
    """응답 schema - parties_represented, cross_party_share, avg_activity."""
    body = client.get("/api/cluster").json()
    first = body["clusters"][0]
    assert "parties_represented" in first
    assert "cross_party_share" in first
    assert "avg_activity" in first
    assert "insight" in first
    assert "proposed" in first["avg_activity"]


def test_detail_endpoint(client: TestClient):
    """GET /api/cluster/{id}."""
    body = client.get("/api/cluster/cluster_ai_data").json()
    assert body["cluster"]["cluster_id"] == "cluster_ai_data"


def test_detail_404(client: TestClient):
    """미존재 404."""
    response = client.get("/api/cluster/cluster_nope")
    assert response.status_code == 404


# ─── 페르소나 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 propagation."""
    headers = {"X-Persona-Id": persona_id}
    body = client.get("/api/cluster", headers=headers).json()
    assert body["persona_id"] == persona_id
    assert len(body["persona_note"]) > 0


def test_editorial_extras_follow_up(client: TestClient):
    """editorial - follow_up_hint."""
    body = client.get(
        "/api/cluster/cluster_ai_data",
        headers={"X-Persona-Id": "editorial"},
    ).json()
    assert "follow_up_hint" in body["extras"]


def test_paid_extras_premium_cta(client: TestClient):
    """paid_subscriber - premium_cta."""
    body = client.get(
        "/api/cluster/cluster_ai_data",
        headers={"X-Persona-Id": "paid_subscriber"},
    ).json()
    assert "premium_cta" in body["extras"]


def test_b2b_extras_api_hint(client: TestClient):
    """b2b - api_response_hint."""
    body = client.get(
        "/api/cluster/cluster_ai_data",
        headers={"X-Persona-Id": "b2b"},
    ).json()
    assert "api_response_hint" in body["extras"]


# ─── ADR-0004 ────────────────────────────────────────────────────────────


def test_no_ideology_terms_in_insights():
    """insight에 이념 라벨 미포함."""
    forbidden = ["보수", "진보적", "좌파", "우파", "극좌", "극우"]
    for c in cluster_builder.list_clusters():
        for term in forbidden:
            assert term not in c.insight, f"{c.cluster_id}: '{term}'"
