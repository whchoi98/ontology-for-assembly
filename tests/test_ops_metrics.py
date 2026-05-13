"""api.services.ops_metrics + api.routers.ops 검증 (Phase 5 Track 5-2)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import ops_metrics


@pytest.fixture(autouse=True)
def reset_buffer():
    """각 테스트 시작 전 ring buffer + 카운터 초기화."""
    ops_metrics.reset()
    yield
    ops_metrics.reset()


# ─── ops_metrics 서비스 ──────────────────────────────────────────────────────

def test_record_trace_appends_to_ring_buffer():
    entry = ops_metrics.record_trace(
        persona_id="editorial",
        scenario_code="A",
        model_id="global.anthropic.claude-sonnet-4-6",
        political_balance_score=0.95,
        alarm=False,
    )
    assert entry.persona_id == "editorial"
    traces = ops_metrics.get_recent_traces()
    assert len(traces) == 1
    assert traces[0].persona_id == "editorial"


def test_ring_buffer_caps_at_buffer_size():
    """BUFFER_SIZE 초과 시 가장 오래된 entry 제거."""
    for i in range(ops_metrics.BUFFER_SIZE + 30):
        ops_metrics.record_trace(
            persona_id=f"persona_{i}",
            scenario_code="A",
            model_id="m",
            political_balance_score=0.9,
            alarm=False,
        )
    traces = ops_metrics.get_recent_traces(limit=ops_metrics.BUFFER_SIZE + 50)
    assert len(traces) == ops_metrics.BUFFER_SIZE  # 캡 적용


def test_recent_traces_returns_most_recent_first():
    """최신 trace가 첫 번째."""
    for i in range(5):
        ops_metrics.record_trace(
            persona_id="editorial", scenario_code=chr(ord("A") + i),
            model_id="m", political_balance_score=0.9, alarm=False,
        )
    traces = ops_metrics.get_recent_traces(limit=5)
    # 마지막에 기록된 'E'가 첫 번째
    assert traces[0].scenario_code == "E"
    assert traces[-1].scenario_code == "A"


def test_counters_accumulate_correctly():
    for _ in range(3):
        ops_metrics.record_trace(
            persona_id="editorial", scenario_code="A", model_id="m",
            political_balance_score=0.9, alarm=False,
        )
    ops_metrics.record_trace(
        persona_id="editorial", scenario_code="A", model_id="m",
        political_balance_score=0.5, alarm=True, alarm_reason="low_balance_score",
    )
    counters = ops_metrics.get_guardrail_counters()
    assert counters.total_invocations == 4
    assert counters.total_alarms_low_balance == 1
    assert counters.total_blocked == 0


def test_counters_track_blocked_topics():
    ops_metrics.record_trace(
        persona_id="editorial", scenario_code="A", model_id="m",
        political_balance_score=0.0, alarm=True, alarm_reason="input_blocked",
        blocked_topics=["party_attack"],
    )
    counters = ops_metrics.get_guardrail_counters()
    assert counters.total_blocked == 1
    assert counters.blocked_by_topic["party_attack"] == 1


def test_avg_balance_score_running_average():
    scores = [0.9, 0.7, 0.8]
    for s in scores:
        ops_metrics.record_trace(
            persona_id="editorial", scenario_code="A", model_id="m",
            political_balance_score=s, alarm=False,
        )
    expected_avg = sum(scores) / len(scores)
    counters = ops_metrics.get_guardrail_counters()
    assert abs(counters.avg_balance_score - expected_avg) < 0.01


def test_reset_clears_state():
    ops_metrics.record_trace("editorial", "A", "m", 0.9, False)
    assert len(ops_metrics.get_recent_traces()) == 1
    ops_metrics.reset()
    assert len(ops_metrics.get_recent_traces()) == 0
    assert ops_metrics.get_guardrail_counters().total_invocations == 0


# ─── bedrock.invoke 통합 - 자동 trace 기록 ─────────────────────────────────

def test_bedrock_invoke_records_trace():
    """bedrock.invoke가 매 호출 시 trace를 자동 기록한다."""
    from api.services import bedrock
    bedrock.invoke("AI 입법", persona_id="editorial", scenario_code="A")
    traces = ops_metrics.get_recent_traces()
    assert len(traces) == 1
    assert traces[0].persona_id == "editorial"
    assert traces[0].scenario_code == "A"
    assert traces[0].political_balance_score > 0


def test_bedrock_invoke_blocked_input_also_recorded():
    """입력 차단도 trace에 남는다 (audit)."""
    from api.services import bedrock
    bedrock.invoke("국민의힘은 무능하다 부패", persona_id="editorial", scenario_code="B")
    traces = ops_metrics.get_recent_traces()
    assert len(traces) == 1
    assert traces[0].alarm is True
    # input_blocked 또는 low_balance_score 모두 alarm reason 가능
    assert traces[0].alarm_reason in ("input_blocked", "low_balance_score")


# ─── 운영 콘솔 라우터 ───────────────────────────────────────────────────────

@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_ops_ingest_panel(client):
    response = client.get("/api/ops/ingest")
    assert response.status_code == 200
    body = response.json()
    assert "output_dir" in body
    assert "file_counts" in body
    assert "source_distribution" in body


def test_ops_guardrail_panel(client):
    response = client.get("/api/ops/guardrail")
    assert response.status_code == 200
    body = response.json()
    assert "total_invocations" in body
    assert "avg_balance_score" in body
    assert body["threshold"] == 0.8  # ALARM_THRESHOLD


def test_ops_memory_panel(client):
    response = client.get("/api/ops/memory")
    assert response.status_code == 200
    body = response.json()
    assert "namespaces" in body
    assert set(body["namespaces"]) == {"staff", "subscriber", "guest"}


def test_ops_wow_quality_panel(client):
    """harness-eval 미실행 상태에서도 panel은 응답."""
    response = client.get("/api/ops/wow-quality")
    assert response.status_code == 200
    body = response.json()
    assert "total_cases" in body
    assert "pass_rate" in body


def test_ops_trace_panel_empty(client):
    response = client.get("/api/ops/trace")
    assert response.status_code == 200
    body = response.json()
    assert body["buffer_size"] == ops_metrics.BUFFER_SIZE
    assert isinstance(body["entries"], list)


def test_ops_trace_panel_after_invocation(client):
    """bedrock.invoke 후 trace 패널에 entry 등장."""
    from api.services import bedrock
    bedrock.invoke("AI", persona_id="data_ai", scenario_code="E")
    response = client.get("/api/ops/trace?limit=5")
    body = response.json()
    assert len(body["entries"]) >= 1
    assert body["entries"][0]["persona_id"] == "data_ai"


def test_ops_trace_limit_param(client):
    """limit 파라미터 적용."""
    from api.services import bedrock
    for i in range(5):
        bedrock.invoke(f"Q{i}", persona_id="editorial", scenario_code="A")
    response = client.get("/api/ops/trace?limit=3")
    body = response.json()
    assert len(body["entries"]) <= 3


def test_ops_trace_limit_out_of_range_rejected(client):
    response = client.get("/api/ops/trace?limit=200")
    assert response.status_code == 422


def test_ops_guardrail_counters_reflect_invocations(client):
    from api.services import bedrock
    for _ in range(3):
        bedrock.invoke("AI", persona_id="editorial", scenario_code="A")
    response = client.get("/api/ops/guardrail")
    body = response.json()
    assert body["total_invocations"] >= 3
