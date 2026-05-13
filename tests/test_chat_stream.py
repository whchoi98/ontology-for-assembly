"""SSE streaming 검증 (Phase 5 Track 5-5).

POST /api/chat/stream의 SSE 이벤트 sequence를 raw bytes로 파싱·검증.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _parse_sse_stream(body: bytes) -> list[tuple[str, dict]]:
    """SSE bytes → [(event_name, data_dict), ...]."""
    text = body.decode("utf-8").replace("\r\n", "\n")
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            data = json.loads("".join(data_lines))
            events.append((event_name, data))
    return events


def _collect_events(client: TestClient, **request_kwargs) -> list[tuple[str, dict]]:
    """SSE 응답 전체 bytes 수집 + 파싱."""
    with client.stream("POST", "/api/chat/stream", **request_kwargs) as resp:
        assert resp.status_code == 200, resp.text
        full = b"".join(resp.iter_bytes())
    return _parse_sse_stream(full)


# ─── 기본 ──────────────────────────────────────────────────────────────────

def test_stream_returns_event_stream(client):
    """Content-Type: text/event-stream."""
    with client.stream(
        "POST", "/api/chat/stream",
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


def test_stream_emits_15_events(client):
    """3 phase + 4 agent log + 4 tool log + 3 result + 1 done = 15."""
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    assert len(events) == 15


def test_stream_event_types_in_order(client):
    """이벤트 순서: phase → log... → result → phase → log... → result → ... → done."""
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    types = [e[0] for e in events]
    # 첫 이벤트 phase, 마지막 done
    assert types[0] == "phase"
    assert types[-1] == "done"

    # 3 phase events
    assert types.count("phase") == 3
    # 3 result events (각 stage 끝)
    assert types.count("result") == 3
    # 1 done
    assert types.count("done") == 1
    # 나머지는 log
    assert types.count("log") == 8  # 4 tools + 4 agents


def test_stream_phase_events_cover_three_stages(client):
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    phase_stages = [d["stage"] for n, d in events if n == "phase"]
    assert phase_stages == ["chatbot", "agent", "agentic"]


def test_stream_result_has_political_balance_score(client):
    """result 이벤트마다 political_balance_score 포함."""
    events = _collect_events(
        client,
        json={"query": "AI 입법", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    for name, data in events:
        if name == "result":
            assert "political_balance_score" in data
            assert 0.0 <= data["political_balance_score"] <= 1.0


def test_stream_agent_logs_tool_calls(client):
    """Stage 2 (agent) log 이벤트가 4개 도구 호출 모두 포함."""
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    tools_seen = []
    for name, data in events:
        if name == "log" and data.get("stage") == "agent":
            tools_seen.append(data.get("tool_called"))
    assert set(tools_seen) == {"search_bills", "get_proposers", "cosponsor_network", "analyze_votes"}


def test_stream_agentic_logs_four_agents_in_order(client):
    """Stage 3 (agentic) log 이벤트가 Planner→Graph→Analyst→Editor 순서."""
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    agents_seen = []
    for name, data in events:
        if name == "log" and data.get("stage") == "agentic":
            agents_seen.append(data.get("agent_invoked"))
    assert agents_seen == ["planner", "graph", "analyst", "editor"]


def test_stream_done_carries_total_ms(client):
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "editorial"},
    )
    done = [d for n, d in events if n == "done"]
    assert len(done) == 1
    assert "total_ms" in done[0]
    assert done[0]["total_ms"] >= 0
    assert done[0]["persona_id"] == "editorial"


def test_stream_persona_propagates(client):
    events = _collect_events(
        client,
        json={"query": "AI", "mode": "compare"},
        headers={"X-Persona-Id": "general_reader"},
    )
    done = [d for n, d in events if n == "done"][0]
    assert done["persona_id"] == "general_reader"


def test_stream_invalid_query_rejected(client):
    """빈 query는 422."""
    response = client.post(
        "/api/chat/stream",
        json={"query": "", "mode": "compare"},
    )
    assert response.status_code == 422
