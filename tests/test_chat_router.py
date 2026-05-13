"""api.routers.chat FastAPI 라우터 검증.

FastAPI TestClient 사용. 실제 ASGI 서버 부팅 없이 라우터 동작 검증.

테스트 범위:
- POST /api/chat compare 모드 (3 모드 모두 응답)
- POST /api/chat 단일 모드 (chatbot/agent/agentic)
- X-Persona-Id 헤더 처리 (6 페르소나)
- 기본 페르소나 editorial fallback
- 유효성 검증 (mode enum, scenario_code 정규식)
- 헬스 체크 /healthz, /api/healthz
- GET /api/chat/modes 메타데이터
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 헬스 ─────────────────────────────────────────────────────────────────────

def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_healthz_ok(client):
    response = client.get("/api/healthz")
    assert response.status_code == 200


# ─── GET /api/chat/modes ────────────────────────────────────────────────────

def test_chat_modes_lists_four_modes(client):
    response = client.get("/api/chat/modes")
    assert response.status_code == 200
    modes = response.json()["modes"]
    mode_ids = {m["id"] for m in modes}
    assert mode_ids == {"chatbot", "agent", "agentic", "compare"}


# ─── POST /api/chat ───────────────────────────────────────────────────────────

def test_chat_default_compare_mode_returns_three_results(client):
    """mode 미지정 시 compare → 3 모드 응답."""
    response = client.post("/api/chat", json={"query": "AI 입법 동향"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "compare"
    assert set(body["results"].keys()) == {"chatbot", "agent", "agentic"}


def test_chat_chatbot_only_returns_one_result(client):
    response = client.post("/api/chat", json={"query": "질문", "mode": "chatbot"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "chatbot"
    assert list(body["results"].keys()) == ["chatbot"]


def test_chat_agent_only_returns_one_result(client):
    response = client.post("/api/chat", json={"query": "질문", "mode": "agent"})
    assert response.status_code == 200
    body = response.json()
    assert list(body["results"].keys()) == ["agent"]


def test_chat_agentic_only_returns_one_result(client):
    response = client.post("/api/chat", json={"query": "질문", "mode": "agentic"})
    assert response.status_code == 200
    body = response.json()
    assert list(body["results"].keys()) == ["agentic"]


# ─── X-Persona-Id 헤더 ───────────────────────────────────────────────────────

def test_chat_default_persona_editorial(client):
    """헤더 미지정 시 editorial fallback."""
    response = client.post("/api/chat", json={"query": "질문", "mode": "chatbot"})
    assert response.status_code == 200
    assert response.json()["persona_id"] == "editorial"


@pytest.mark.parametrize("pid", ["editorial", "data_ai", "ad_sales",
                                  "general_reader", "paid_subscriber", "b2b"])
def test_chat_persona_header_propagated(client, pid):
    """6 페르소나 모두 X-Persona-Id 헤더 전파."""
    response = client.post(
        "/api/chat",
        json={"query": "질문", "mode": "chatbot"},
        headers={"X-Persona-Id": pid},
    )
    assert response.status_code == 200
    assert response.json()["persona_id"] == pid


# ─── 유효성 검증 ─────────────────────────────────────────────────────────────

def test_chat_invalid_mode_rejected(client):
    """mode enum 외 값은 422."""
    response = client.post("/api/chat", json={"query": "질문", "mode": "invalid"})
    assert response.status_code == 422


def test_chat_empty_query_rejected(client):
    """query 빈 문자열은 422."""
    response = client.post("/api/chat", json={"query": ""})
    assert response.status_code == 422


def test_chat_invalid_scenario_code_rejected(client):
    """scenario_code 정규식 (A-N) 외는 422."""
    response = client.post(
        "/api/chat",
        json={"query": "질문", "scenario_code": "Z"},
    )
    assert response.status_code == 422


def test_chat_long_query_rejected(client):
    """2000자 초과 query는 422."""
    long_query = "a" * 2001
    response = client.post("/api/chat", json={"query": long_query})
    assert response.status_code == 422


# ─── 응답 모양 ──────────────────────────────────────────────────────────────

def test_chat_compare_result_structure(client):
    response = client.post("/api/chat", json={"query": "AI 분석"})
    body = response.json()
    chatbot = body["results"]["chatbot"]
    assert chatbot["stage"] == "chatbot"
    assert "text" in chatbot
    assert "sources_used" in chatbot
    assert "tools_called" in chatbot
    assert "agents_invoked" in chatbot
    assert "political_balance_score" in chatbot
    assert "alarm" in chatbot
    assert "duration_ms" in chatbot
    assert "extras" in chatbot


def test_chat_agentic_result_has_four_agents(client):
    response = client.post("/api/chat", json={"query": "분석", "mode": "agentic"})
    agentic = response.json()["results"]["agentic"]
    assert agentic["agents_invoked"] == ["planner", "graph", "analyst", "editor"]


def test_chat_agent_result_has_four_tools(client):
    response = client.post("/api/chat", json={"query": "분석", "mode": "agent"})
    agent = response.json()["results"]["agent"]
    assert "search_bills" in agent["tools_called"]
    assert len(agent["tools_called"]) == 4


def test_chat_political_balance_score_in_range(client):
    """모든 응답에 political_balance_score 첨부 + [0, 1] 범위."""
    response = client.post("/api/chat", json={"query": "분석"})
    body = response.json()
    for stage in body["results"].values():
        assert 0.0 <= stage["political_balance_score"] <= 1.0
