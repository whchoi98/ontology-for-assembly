"""시나리오 K 표결 이상치 라우터·서비스 검증 (Phase 4 Track 4-1)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import outlier_detect


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── outlier_detect 서비스 ──────────────────────────────────────────────────

def test_list_outliers_returns_pydantic_entries():
    items = outlier_detect.list_outliers()
    assert len(items) >= 1
    assert all(isinstance(o, outlier_detect.OutlierEntry) for o in items)


def test_list_sorted_by_deviation_score_desc():
    items = outlier_detect.list_outliers(limit=10)
    scores = [o.deviation_score for o in items]
    assert scores == sorted(scores, reverse=True)


def test_list_limit_applied():
    items = outlier_detect.list_outliers(limit=2)
    assert len(items) <= 2


def test_filter_by_outlier_type():
    party_line = outlier_detect.list_outliers(outlier_type="party_line_break")
    assert all(o.outlier_type == "party_line_break" for o in party_line)
    swing = outlier_detect.list_outliers(outlier_type="swing_vote")
    assert all(o.outlier_type == "swing_vote" for o in swing)


def test_get_outlier_existing():
    o = outlier_detect.get_outlier("ol_party_break_001")
    assert o is not None
    assert o.outlier_type == "party_line_break"


def test_get_outlier_nonexistent_returns_none():
    assert outlier_detect.get_outlier("nonexistent_id") is None


def test_outlier_types_cover_three_kinds():
    items = outlier_detect.list_outliers(limit=20)
    types = {o.outlier_type for o in items}
    assert "party_line_break" in types
    assert "swing_vote" in types
    assert "cross_party" in types


# ─── 정치 중립성 검증 ───────────────────────────────────────────────────────

def test_ai_label_no_party_attack():
    """ai_label에 정당 비방 어휘 미포함 (ADR-0004)."""
    forbidden = ["무능", "부패", "엉터리", "쓰레기", "악마", "기만"]
    for o in outlier_detect.list_outliers(limit=20):
        for word in forbidden:
            assert word not in o.ai_label, f"{o.outlier_id} ai_label에 '{word}'"


def test_description_no_party_attack():
    forbidden = ["무능", "부패", "엉터리"]
    for o in outlier_detect.list_outliers(limit=20):
        for word in forbidden:
            assert word not in o.description


# ─── 라우터 ─────────────────────────────────────────────────────────────────

def test_list_endpoint_default(client):
    response = client.get("/api/outlier")
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_code"] == "K"
    assert body["persona_id"] == "editorial"
    assert "outliers" in body
    assert "persona_note" in body
    assert len(body["outliers"]) >= 1


def test_list_endpoint_with_type_filter(client):
    response = client.get("/api/outlier?outlier_type=swing_vote")
    body = response.json()
    for o in body["outliers"]:
        assert o["outlier_type"] == "swing_vote"


def test_list_endpoint_limit_param(client):
    response = client.get("/api/outlier?limit=2")
    body = response.json()
    assert len(body["outliers"]) <= 2


def test_detail_endpoint(client):
    response = client.get("/api/outlier/ol_party_break_001")
    assert response.status_code == 200
    body = response.json()
    assert body["outlier"]["outlier_id"] == "ol_party_break_001"
    assert "extras" in body
    assert "follow_up_hint" in body["extras"]


def test_detail_endpoint_404(client):
    response = client.get("/api/outlier/unknown_id")
    assert response.status_code == 404


@pytest.mark.parametrize("pid", [
    "editorial", "data_ai", "ad_sales",
    "general_reader", "paid_subscriber", "b2b",
])
def test_persona_note_per_persona(client, pid):
    """6 페르소나 모두 고유 안내 메시지."""
    response = client.get("/api/outlier", headers={"X-Persona-Id": pid})
    body = response.json()
    assert body["persona_id"] == pid
    assert body["persona_note"]


def test_b2b_follow_up_hint_includes_api(client):
    response = client.get(
        "/api/outlier/ol_swing_001",
        headers={"X-Persona-Id": "b2b"},
    )
    hint = response.json()["extras"]["follow_up_hint"]
    assert "/api/outlier" in hint


def test_editorial_follow_up_hint_mentions_interview(client):
    response = client.get(
        "/api/outlier/ol_party_break_001",
        headers={"X-Persona-Id": "editorial"},
    )
    hint = response.json()["extras"]["follow_up_hint"]
    assert "취재" in hint or "인터뷰" in hint


# ─── 유효성 ─────────────────────────────────────────────────────────────────

def test_invalid_limit_rejected(client):
    response = client.get("/api/outlier?limit=200")
    assert response.status_code == 422


def test_invalid_outlier_type_rejected(client):
    response = client.get("/api/outlier?outlier_type=invalid_type")
    assert response.status_code == 422
