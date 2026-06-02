"""시나리오 F 의원 룩어라이크 검증 (Phase 4 Track 4-9)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import lookalike_builder, cluster_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_list_seeds_returns_all_cluster_members():
    """seeds 수 == cluster 멤버 합."""
    seeds = lookalike_builder.list_seeds()
    total_members = sum(c.member_count for c in cluster_builder.list_clusters())
    assert len(seeds) == total_members


def test_build_lookalikes_hub_returns_candidates():
    """MONA_001 (허브) → top-5 후보 반환."""
    result = lookalike_builder.build_lookalikes("MONA_001", top_k=5)
    assert result is not None
    assert result.seed_person_id == "MONA_001"
    assert len(result.candidates) == 5
    # similarity 내림차순
    sims = [c.similarity for c in result.candidates]
    assert sims == sorted(sims, reverse=True)


def test_build_lookalikes_unknown_returns_none():
    """미등록 person_id → None."""
    assert lookalike_builder.build_lookalikes("MONA_999") is None


def test_build_lookalikes_excludes_self():
    """결과에 seed 본인 미포함."""
    result = lookalike_builder.build_lookalikes("MONA_001", top_k=15)
    assert result is not None
    pids = {c.person_id for c in result.candidates}
    assert "MONA_001" not in pids


def test_same_cluster_member_has_higher_similarity():
    """동일 cluster 멤버가 다른 cluster 멤버보다 similarity 높음."""
    result = lookalike_builder.build_lookalikes("MONA_001", top_k=15)
    assert result is not None
    same = [c for c in result.candidates if c.cluster_id == result.seed_cluster_id]
    other = [c for c in result.candidates if c.cluster_id != result.seed_cluster_id]
    if same and other:
        assert min(c.similarity for c in same) >= max(c.similarity for c in other) - 0.05


def test_cross_party_signal_when_party_differs():
    """seed cluster + 다른 정당 후보는 cross_party_signal=True."""
    result = lookalike_builder.build_lookalikes("MONA_001", top_k=15)
    assert result is not None
    for c in result.candidates:
        same_cluster = c.cluster_id == result.seed_cluster_id
        different_party = c.party != result.seed_party
        if same_cluster and different_party:
            assert c.cross_party_signal is True


def test_top_k_respects_limit():
    """top_k는 후보 수 상한."""
    result = lookalike_builder.build_lookalikes("MONA_001", top_k=3)
    assert result is not None
    assert len(result.candidates) == 3


def test_factors_present_for_each_candidate():
    """각 candidate는 factors 1+ 포함."""
    result = lookalike_builder.build_lookalikes("MONA_001")
    assert result is not None
    for c in result.candidates:
        assert len(c.factors) >= 1


# ─── 라우터 ────────────────────────────────────────────────────────────────


def test_seeds_endpoint(client: TestClient):
    """GET /api/lookalike/seeds."""
    response = client.get("/api/lookalike/seeds")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 25  # 5 cluster × 평균 5-8 멤버
    assert len(body["seeds"]) == body["total"]


def test_get_lookalikes_endpoint(client: TestClient):
    """GET /api/lookalike/{person_id}."""
    body = client.get("/api/lookalike/MONA_001").json()
    assert body["seed_person_id"] == "MONA_001"
    assert len(body["candidates"]) == 5
    assert body["seed_cluster_id"]


def test_get_lookalikes_top_k_query(client: TestClient):
    """top_k 쿼리 파라미터."""
    body = client.get("/api/lookalike/MONA_001?top_k=3").json()
    assert len(body["candidates"]) == 3


def test_get_lookalikes_top_k_validation(client: TestClient):
    """top_k > 15 거부."""
    response = client.get("/api/lookalike/MONA_001?top_k=100")
    assert response.status_code == 422


def test_get_lookalikes_404(client: TestClient):
    """미등록 person_id 404."""
    response = client.get("/api/lookalike/MONA_999")
    assert response.status_code == 404


# ─── 페르소나 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 propagation."""
    headers = {"X-Persona-Id": persona_id}
    body = client.get("/api/lookalike/MONA_001", headers=headers).json()
    assert body["persona_id"] == persona_id


def test_editorial_extras_follow_up(client: TestClient):
    body = client.get(
        "/api/lookalike/MONA_001",
        headers={"X-Persona-Id": "editorial"},
    ).json()
    assert "follow_up_hint" in body["extras"]


def test_data_ai_extras_analysis_hint(client: TestClient):
    body = client.get(
        "/api/lookalike/MONA_001",
        headers={"X-Persona-Id": "data_ai"},
    ).json()
    assert "analysis_hint" in body["extras"]


def test_b2b_extras_api_hint(client: TestClient):
    body = client.get(
        "/api/lookalike/MONA_001",
        headers={"X-Persona-Id": "b2b"},
    ).json()
    assert "api_response_hint" in body["extras"]


# ─── narrative ────────────────────────────────────────────────────────────


def test_narrative_includes_cross_party_count(client: TestClient):
    """cross_party 후보가 있으면 narrative에 cross-party 언급."""
    body = client.get("/api/lookalike/MONA_001").json()
    cross_count = sum(1 for c in body["candidates"] if c["cross_party_signal"])
    if cross_count > 0:
        assert "cross-party" in body["narrative"] or "다른 정당" in body["narrative"]


def test_narrative_includes_source_attribution(client: TestClient):
    """narrative 또는 sources에 출처 명시."""
    body = client.get("/api/lookalike/MONA_001").json()
    sources_or_narrative = body["narrative"] + ' '.join(body["sources"])
    assert "출처" in sources_or_narrative or "합성" in sources_or_narrative
