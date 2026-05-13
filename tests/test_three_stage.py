"""api.services.three_stage 3-stage 챗봇 검증.

테스트 범위:
- 3 stage 함수 모두 StageResult 반환
- stage 식별자 (chatbot/agent/agentic) 정확
- duration_ms 양수
- tools_called / agents_invoked / sources_used 모양
- run_all_stages 3 모드 모두 실행
- 6 페르소나 모두 처리
"""
from __future__ import annotations
import pytest

from api.services import three_stage


# ─── Stage 1 (Chatbot) ──────────────────────────────────────────────────────

def test_stage1_chatbot_returns_stage_result():
    r = three_stage.stage1_chatbot("AI 관련 법안")
    assert isinstance(r, three_stage.StageResult)
    assert r.stage == "chatbot"
    assert r.text


def test_stage1_chatbot_no_tools_no_agents():
    """Chatbot은 도구·에이전트 호출 없음."""
    r = three_stage.stage1_chatbot("질문")
    assert r.tools_called == []
    assert r.agents_invoked == []


def test_stage1_chatbot_has_sources():
    """RAG이므로 sources_used 비어있지 않음."""
    r = three_stage.stage1_chatbot("AI")
    assert len(r.sources_used) >= 1


def test_stage1_chatbot_duration_recorded():
    r = three_stage.stage1_chatbot("질문")
    assert r.duration_ms >= 0


def test_stage1_chatbot_extras_shows_limitation():
    """청중에 'RAG 한계'를 전달하는 extras."""
    r = three_stage.stage1_chatbot("질문")
    assert "limitation" in r.extras


# ─── Stage 2 (Agent / Tool Use) ─────────────────────────────────────────────

def test_stage2_agent_returns_stage_result():
    r = three_stage.stage2_agent("AI 법안 발의자 알려줘")
    assert r.stage == "agent"
    assert r.text


def test_stage2_agent_calls_four_tools():
    """Stage 2는 4개 도구 순차 호출."""
    r = three_stage.stage2_agent("질문")
    assert "search_bills" in r.tools_called
    assert "get_proposers" in r.tools_called
    assert "cosponsor_network" in r.tools_called
    assert "analyze_votes" in r.tools_called
    assert len(r.tools_called) == 4


def test_stage2_agent_no_subagents():
    """Stage 2는 서브 에이전트 없음 (도구만)."""
    r = three_stage.stage2_agent("질문")
    assert r.agents_invoked == []


def test_stage2_agent_extras_shows_workflow_limitation():
    r = three_stage.stage2_agent("질문")
    assert "Tool Use" in r.extras.get("approach", "")


# ─── Stage 3 (Agentic) ──────────────────────────────────────────────────────

def test_stage3_agentic_returns_stage_result():
    r = three_stage.stage3_agentic("AI 입법 네트워크 분석")
    assert r.stage == "agentic"
    assert r.text


def test_stage3_agentic_invokes_four_agents():
    """Stage 3는 Planner → Graph → Analyst → Editor 순서로 4 에이전트 실행."""
    r = three_stage.stage3_agentic("질문")
    assert r.agents_invoked == ["planner", "graph", "analyst", "editor"]


def test_stage3_agentic_extras_has_agent_outputs():
    """Editor 외 plan/graph/analyst의 중간 출력이 extras에 노출."""
    r = three_stage.stage3_agentic("질문")
    assert "plan_text" in r.extras
    assert "graph_text" in r.extras
    assert "analyst_text" in r.extras
    assert "Multi-Agent" in r.extras["approach"]


# ─── run_all_stages (비교) ──────────────────────────────────────────────────

def test_run_all_stages_returns_three_modes():
    """3 모드 모두 실행하여 dict 반환."""
    results = three_stage.run_all_stages("AI 입법 동향")
    assert set(results.keys()) == {"chatbot", "agent", "agentic"}


def test_run_all_stages_each_has_correct_stage():
    results = three_stage.run_all_stages("질문")
    assert results["chatbot"].stage == "chatbot"
    assert results["agent"].stage == "agent"
    assert results["agentic"].stage == "agentic"


def test_run_all_stages_complexity_progresses():
    """Stage 1 < 2 < 3 복잡도. 도구·에이전트 호출 개수로 측정."""
    results = three_stage.run_all_stages("질문")
    s1_calls = len(results["chatbot"].tools_called) + len(results["chatbot"].agents_invoked)
    s2_calls = len(results["agent"].tools_called) + len(results["agent"].agents_invoked)
    s3_calls = len(results["agentic"].tools_called) + len(results["agentic"].agents_invoked)
    assert s1_calls < s2_calls <= s3_calls


# ─── 6 페르소나 처리 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("pid", ["editorial", "data_ai", "ad_sales",
                                  "general_reader", "paid_subscriber", "b2b"])
def test_all_three_stages_handle_all_personas(pid):
    """모든 페르소나로 3 모드 호출 가능."""
    results = three_stage.run_all_stages("질문", persona_id=pid)
    assert len(results) == 3


# ─── 직렬화 ─────────────────────────────────────────────────────────────────

def test_stage_result_to_dict_serializable():
    """StageResult.to_dict()는 JSON 직렬화 가능."""
    import json
    r = three_stage.stage1_chatbot("질문")
    d = r.to_dict()
    assert json.dumps(d, ensure_ascii=False)  # 예외 없으면 OK
    assert "stage" in d
    assert "text" in d
    assert "sources_used" in d


def test_political_balance_score_propagated():
    """3 stage 모두 political_balance_score 첨부."""
    results = three_stage.run_all_stages("질문")
    for stage_name, r in results.items():
        assert 0.0 <= r.political_balance_score <= 1.0, f"{stage_name}: invalid score"
