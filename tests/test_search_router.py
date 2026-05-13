"""시나리오 A 검색 라우터 검증.

테스트 범위:
- POST /api/search 기본 응답 모양
- 페르소나별 top_k 조정 (general_reader 5, data_ai 15+, 기본 10)
- cohort.select 결과가 cohort_used에 반영
- include_subgraph=true → top hit 1-hop subgraph
- 유효성 검증 (query 빈/길이, top_k 범위)
- GET /api/search/info 메타데이터
- 6 페르소나 모두 처리
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── POST /api/search ───────────────────────────────────────────────────────

def test_search_basic_returns_hits(client):
    response = client.post("/api/search", json={"q": "AI 입법"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "AI 입법"
    assert body["scenario_code"] == "A"
    assert body["persona_id"] == "editorial"
    assert "hits" in body
    assert len(body["hits"]) >= 1


def test_search_default_persona_editorial(client):
    response = client.post("/api/search", json={"q": "법안"})
    assert response.json()["persona_id"] == "editorial"


@pytest.mark.parametrize("pid", ["editorial", "data_ai", "ad_sales",
                                  "general_reader", "paid_subscriber", "b2b"])
def test_search_handles_six_personas(client, pid):
    response = client.post(
        "/api/search",
        json={"q": "AI"},
        headers={"X-Persona-Id": pid},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persona_id"] == pid
    assert "extras" in body
    assert body["extras"]["persona_name_kr"]


def test_search_general_reader_caps_top_k_at_5(client):
    """일반 독자는 top_k 최대 5 (입문성)."""
    response = client.post(
        "/api/search",
        json={"q": "AI", "top_k": 20},
        headers={"X-Persona-Id": "general_reader"},
    )
    body = response.json()
    assert len(body["hits"]) <= 5


def test_search_data_ai_floors_top_k_at_15(client):
    """데이터·AI는 분석 후보 풍부히 (top_k 최소 15)."""
    response = client.post(
        "/api/search",
        json={"q": "AI", "top_k": 5},  # 요청은 5
        headers={"X-Persona-Id": "data_ai"},
    )
    body = response.json()
    # mock fixture가 6개이므로 hits는 mock 한계만큼만 (6 ≤ 15)
    # adjust_top_k는 15 보장하지만 mock이 더 많지 않으면 그만큼.
    # 검증은 info endpoint로 정책 확인
    info_response = client.get("/api/search/info", headers={"X-Persona-Id": "data_ai"})
    assert info_response.json()["default_top_k"] == 15


def test_search_cohort_propagates_to_response(client):
    """editorial은 cohort=['real']이고 응답의 cohort_used에 반영."""
    response = client.post("/api/search", json={"q": "법안"},
                            headers={"X-Persona-Id": "editorial"})
    body = response.json()
    assert body["cohort_used"] == ["real"]


def test_search_paid_subscriber_cohort_includes_synthetic(client):
    """유료 구독자는 default_cohort에 synthetic 포함."""
    response = client.post("/api/search", json={"q": "법안"},
                            headers={"X-Persona-Id": "paid_subscriber"})
    cohort_used = response.json()["cohort_used"]
    assert "synthetic" in cohort_used or "*" in cohort_used


def test_search_general_reader_extras_has_guide_hint(client):
    response = client.post("/api/search", json={"q": "법안"},
                            headers={"X-Persona-Id": "general_reader"})
    extras = response.json()["extras"]
    assert "guide_hint" in extras


def test_search_paid_subscriber_extras_has_pdf_cta(client):
    response = client.post("/api/search", json={"q": "법안"},
                            headers={"X-Persona-Id": "paid_subscriber"})
    extras = response.json()["extras"]
    assert "premium_cta" in extras


def test_search_b2b_extras_has_api_hint(client):
    response = client.post("/api/search", json={"q": "법안"},
                            headers={"X-Persona-Id": "b2b"})
    extras = response.json()["extras"]
    assert "api_response_hint" in extras


# ─── 1-hop subgraph ─────────────────────────────────────────────────────────

def test_search_include_subgraph_returns_subgraph(client):
    """include_subgraph=true → top_hit_subgraph 포함."""
    response = client.post(
        "/api/search",
        json={"q": "AI 입법", "include_subgraph": True},
    )
    body = response.json()
    assert body["top_hit_subgraph"] is not None
    assert "root_id" in body["top_hit_subgraph"]
    assert "nodes" in body["top_hit_subgraph"]
    assert "edges" in body["top_hit_subgraph"]


def test_search_no_subgraph_when_disabled(client):
    response = client.post(
        "/api/search",
        json={"q": "AI", "include_subgraph": False},
    )
    body = response.json()
    assert body["top_hit_subgraph"] is None


def test_subgraph_root_node_present(client):
    """subgraph의 nodes에 root_id 노드가 포함."""
    response = client.post("/api/search", json={"q": "AI"})
    body = response.json()
    sg = body["top_hit_subgraph"]
    root_ids = [n["id"] for n in sg["nodes"] if n["id"] == sg["root_id"]]
    assert root_ids


# ─── 유효성 검증 ────────────────────────────────────────────────────────────

def test_search_empty_query_rejected(client):
    response = client.post("/api/search", json={"q": ""})
    assert response.status_code == 422


def test_search_long_query_rejected(client):
    response = client.post("/api/search", json={"q": "x" * 501})
    assert response.status_code == 422


def test_search_top_k_out_of_range_rejected(client):
    response = client.post("/api/search", json={"q": "AI", "top_k": 100})
    assert response.status_code == 422
    response2 = client.post("/api/search", json={"q": "AI", "top_k": 0})
    assert response2.status_code == 422


# ─── Hit 모양 ───────────────────────────────────────────────────────────────

def test_hit_has_required_fields(client):
    response = client.post("/api/search", json={"q": "AI"})
    body = response.json()
    assert body["hits"]
    hit = body["hits"][0]
    for f in ("id", "score", "source", "title", "snippet", "node_type", "metadata"):
        assert f in hit


def test_hit_source_in_cohort(client):
    """반환된 hit의 source가 cohort_used에 포함되어야 한다."""
    response = client.post("/api/search", json={"q": "AI"},
                            headers={"X-Persona-Id": "editorial"})
    body = response.json()
    cohort_used = body["cohort_used"]
    for hit in body["hits"]:
        if "*" not in cohort_used:
            assert hit["source"] in cohort_used


# ─── GET /api/search/info ───────────────────────────────────────────────────

def test_search_info_returns_metadata(client):
    response = client.get("/api/search/info")
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_code"] == "A"
    assert body["persona_id"] == "editorial"
    assert "cohort" in body
    assert "supported_node_types" in body


def test_search_info_per_persona(client):
    """info 응답이 페르소나별로 정확히 변함."""
    e_info = client.get("/api/search/info", headers={"X-Persona-Id": "editorial"}).json()
    g_info = client.get("/api/search/info", headers={"X-Persona-Id": "general_reader"}).json()
    p_info = client.get("/api/search/info", headers={"X-Persona-Id": "paid_subscriber"}).json()
    assert e_info["default_top_k"] == 10
    assert g_info["default_top_k"] == 5
    assert p_info["default_top_k"] == 10
