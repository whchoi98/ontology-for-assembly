"""api.services.multi_agent 4-에이전트 파이프라인 검증."""
from __future__ import annotations
import pytest

from api.services import multi_agent


def test_four_agents_registered():
    """AGENT_PROMPTS에 4 에이전트 등록."""
    assert set(multi_agent.AGENT_PROMPTS.keys()) == {"planner", "graph", "analyst", "editor"}


def test_run_agentic_pipeline_returns_dict():
    result = multi_agent.run_agentic_pipeline("AI 법안 분석")
    assert isinstance(result, dict)


def test_pipeline_invokes_four_agents_in_order():
    result = multi_agent.run_agentic_pipeline("질문")
    assert result["agents_invoked"] == ["planner", "graph", "analyst", "editor"]


def test_pipeline_text_is_editor_output():
    """최종 text는 Editor 에이전트의 출력 (기사 초안)."""
    result = multi_agent.run_agentic_pipeline("질문")
    assert result["text"]
    assert len(result["text"]) > 0


def test_pipeline_intermediate_outputs_preserved():
    """plan/graph/analyst 텍스트가 별도 키로 보존됨."""
    result = multi_agent.run_agentic_pipeline("질문")
    assert "plan_text" in result
    assert "graph_text" in result
    assert "analyst_text" in result


def test_pipeline_tools_called_include_search_and_neptune():
    """파이프라인이 OpenSearch + Neptune 도구를 호출했어야 한다."""
    result = multi_agent.run_agentic_pipeline("AI 법안")
    assert "semantic_search" in result["tools_called"]
    assert any("neptune" in t for t in result["tools_called"])


def test_pipeline_sources_have_node_types():
    """sources_used에 다양한 node_type 노출."""
    result = multi_agent.run_agentic_pipeline("질문")
    assert len(result["sources_used"]) >= 1
    for src in result["sources_used"]:
        assert "source" in src
        assert "node_type" in src


def test_pipeline_score_in_valid_range():
    result = multi_agent.run_agentic_pipeline("질문")
    assert 0.0 <= result["political_balance_score"] <= 1.0


@pytest.mark.parametrize("pid", ["editorial", "general_reader", "paid_subscriber", "b2b"])
def test_pipeline_handles_each_persona(pid):
    result = multi_agent.run_agentic_pipeline("질문", persona_id=pid)
    assert result["text"]
    assert len(result["agents_invoked"]) == 4


def test_agent_prompts_have_role_keyword():
    """모든 AGENT_PROMPTS에 에이전트 이름 또는 역할이 명시."""
    for name, prompt in multi_agent.AGENT_PROMPTS.items():
        # 한국어 역할 키워드
        role_keywords = {
            "planner": "Planner",
            "graph": "Graph",
            "analyst": "분석가",
            "editor": "편집장",
        }
        assert role_keywords[name] in prompt, f"{name}: 역할 키워드 누락"
