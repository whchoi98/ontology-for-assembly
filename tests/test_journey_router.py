"""시나리오 M 의원 정치 여정 검증 (Phase 4 Track 4-2)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import journey_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────

def test_build_journey_hub_returns_rich_timeline():
    """MONA_001 (허브) - 8 이벤트 풍부한 timeline."""
    result = journey_builder.build_journey("MONA_001")
    assert result is not None
    assert result.person_id == "MONA_001"
    assert len(result.events) >= 8
    assert result.stats["proposed"] >= 1
    assert result.stats["co_proposed"] >= 1
    assert result.stats["voted"] >= 1


def test_build_journey_other_returns_simple_timeline():
    """일반 의원 (MONA_002)는 단순 3 이벤트."""
    result = journey_builder.build_journey("MONA_002")
    assert result is not None
    assert len(result.events) == 3


def test_build_journey_unknown_returns_none():
    assert journey_builder.build_journey("nonexistent_xyz") is None


def test_events_chronologically_consistent():
    """이벤트 날짜가 stats period 내."""
    result = journey_builder.build_journey("MONA_001")
    assert result is not None
    dates = [e.date for e in result.events]
    assert min(dates) >= result.stats["period_start"]
    assert max(dates) <= result.stats["period_end"]


def test_event_types_diverse():
    """허브 timeline에 5개 이벤트 유형 모두 등장 (PDF 시그니처)."""
    result = journey_builder.build_journey("MONA_001")
    assert result is not None
    types = {e.event_type for e in result.events}
    # proposed·co_proposed·voted·statement·committee_join 모두 등장
    assert "proposed" in types
    assert "voted" in types
    assert "statement" in types
    assert "committee_join" in types


def test_summary_includes_data_source():
    """요약문에 데이터 출처 명시 (ADR-0004)."""
    result = journey_builder.build_journey("MONA_001")
    assert result is not None
    assert "출처" in result.summary or "OpenAPI" in result.summary


# ─── 라우터 ─────────────────────────────────────────────────────────────────

def test_list_persons_endpoint(client):
    response = client.get("/api/journey/persons")
    assert response.status_code == 200
    body = response.json()
    assert "available_persons" in body
    assert len(body["available_persons"]) >= 1
    # 허브 의원이 highlighted 표시
    mona001 = next(p for p in body["available_persons"] if p["person_id"] == "MONA_001")
    assert mona001["highlighted"] is True


def test_get_journey_hub(client):
    response = client.get("/api/journey/MONA_001")
    assert response.status_code == 200
    body = response.json()
    assert body["person_id"] == "MONA_001"
    assert len(body["events"]) >= 8
    assert body["stats"]["proposed"] >= 1


def test_get_journey_404_for_unknown(client):
    response = client.get("/api/journey/unknown_id")
    assert response.status_code == 404


@pytest.mark.parametrize("pid", [
    "editorial", "data_ai", "ad_sales",
    "general_reader", "paid_subscriber", "b2b",
])
def test_persona_propagation(client, pid):
    response = client.get(
        "/api/journey/MONA_001",
        headers={"X-Persona-Id": pid},
    )
    body = response.json()
    assert body["persona_id"] == pid
    assert "extras" in body


def test_editorial_extras_includes_follow_up(client):
    response = client.get("/api/journey/MONA_001", headers={"X-Persona-Id": "editorial"})
    extras = response.json()["extras"]
    assert "follow_up_hint" in extras


def test_paid_subscriber_extras_has_pdf_cta(client):
    response = client.get("/api/journey/MONA_001", headers={"X-Persona-Id": "paid_subscriber"})
    extras = response.json()["extras"]
    assert "premium_cta" in extras


def test_b2b_extras_has_api_hint(client):
    response = client.get("/api/journey/MONA_001", headers={"X-Persona-Id": "b2b"})
    extras = response.json()["extras"]
    assert "api_response_hint" in extras


# ─── 정치 중립성 ────────────────────────────────────────────────────────────

def test_event_descriptions_no_party_attack():
    """이벤트 description에 정당 비방 어휘 없음."""
    forbidden = ["무능", "부패", "엉터리"]
    result = journey_builder.build_journey("MONA_001")
    assert result is not None
    for e in result.events:
        for word in forbidden:
            assert word not in e.description
            assert word not in e.title
