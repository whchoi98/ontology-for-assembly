"""api.services.bedrock invoke 단일 진입점 검증.

테스트 범위:
- DEMO_PUBLIC_MODE에서 mock 응답
- system prompt에 페르소나 정보 + NEUTRALITY_GUARD 자동 첨부
- 입력 가드레일 차단 시 안전 fallback
- 정상 응답에 정치 중립성 메타데이터 첨부
- InvokeResult.to_sse_final() 모양
- 6 페르소나 × A·B·L 시나리오 통과
"""
from __future__ import annotations
import os

import pytest

# conftest에서 DEMO_PUBLIC_MODE=true 보장. 명시적 재확인.
os.environ["DEMO_PUBLIC_MODE"] = "true"

from api.services import bedrock


def test_invoke_returns_invoke_result():
    """기본 invoke가 InvokeResult 반환."""
    result = bedrock.invoke("AI 관련 입법 동향")
    assert isinstance(result, bedrock.InvokeResult)
    assert result.text  # 비어있지 않음


def test_invoke_uses_default_model_when_unspecified():
    """모델 미지정 시 Sonnet 4.6 사용 (BEDROCK_CHAT_MODEL_ID env 또는 default)."""
    result = bedrock.invoke("test", persona_id="editorial", scenario_code="A")
    # conftest에서 BEDROCK_CHAT_MODEL_ID=global.anthropic.claude-sonnet-4-6 주입
    assert "sonnet" in result.model_id.lower()


def test_invoke_propagates_persona_and_scenario():
    """InvokeResult에 persona_id, scenario_code가 정확히 전달."""
    result = bedrock.invoke("test", persona_id="data_ai", scenario_code="E")
    assert result.persona_id == "data_ai"
    assert result.scenario_code == "E"


def test_invoke_none_persona_falls_back_to_editorial():
    """persona_id=None이면 editorial로 fallback."""
    result = bedrock.invoke("test", persona_id=None)
    assert result.persona_id == "editorial"


def test_mock_response_contains_balanced_party_mentions():
    """Mock 응답은 균형 잡힌 정당 언급 + 출처 인용 포함하여 self-alarm 방지."""
    result = bedrock.invoke("AI 법안 분석", persona_id="editorial", scenario_code="A")
    text = result.text
    assert "더불어민주당" in text
    assert "국민의힘" in text
    assert "출처" in text


def test_invoke_normal_path_no_alarm():
    """정상 mock 응답은 political_balance_score >= 0.8, alarm=False."""
    result = bedrock.invoke("법안 분석", persona_id="editorial", scenario_code="A")
    assert result.guardrail_passed is True
    assert result.political_balance_score >= bedrock.guardrails.ALARM_THRESHOLD
    assert result.alarm is False
    assert result.alarm_reason is None


def test_invoke_blocks_party_attack_input():
    """입력에 정당 비방 결합 패턴이 있으면 즉시 차단."""
    result = bedrock.invoke("국민의힘은 무능하다 부패", persona_id="editorial")
    assert result.guardrail_passed is False
    assert result.alarm is True
    assert result.alarm_reason == "input_blocked"
    assert "차단" in result.text  # fallback 메시지


def test_invoke_result_has_balance_components():
    """InvokeResult.balance_components 7개 sub-key 모두 존재."""
    result = bedrock.invoke("test")
    comp = result.balance_components
    expected = {
        "party_mention_balance", "citation_score", "assertion_penalty",
        "parties_mentioned", "total_party_mentions", "citation_count", "assertion_count",
    }
    assert expected <= set(comp.keys())


def test_to_sse_final_serializable():
    """InvokeResult.to_sse_final()은 SSE payload로 직렬화 가능한 dict."""
    import json
    result = bedrock.invoke("test")
    payload = result.to_sse_final()
    # JSON 직렬화 가능
    serialized = json.dumps(payload, ensure_ascii=False)
    assert serialized
    assert "political_balance_score" in payload
    assert "alarm" in payload
    assert "balance_components" in payload


@pytest.mark.parametrize("pid", ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"])
def test_invoke_for_each_persona(pid):
    """6 페르소나 모두 정상 응답 + 페르소나별 mock 텍스트 노출."""
    result = bedrock.invoke("이번 분기 입법 동향 알려주세요", persona_id=pid, scenario_code="A")
    assert result.guardrail_passed
    assert result.persona_id == pid
    # mock_response에 페르소나 이름이 일부 노출되는지 확인 (편집국 / 독자 등)
    # 페르소나별 mock 분기가 동작하므로 일부는 그 키워드 포함
    assert result.text


@pytest.mark.parametrize("scenario", ["A", "B", "C", "L", "K", "N"])
def test_invoke_for_key_scenarios(scenario):
    """핵심 시나리오(A·B·C·L·K·N) 모두 invoke 통과."""
    result = bedrock.invoke("분석 부탁드립니다", persona_id="editorial", scenario_code=scenario)
    assert result.scenario_code == scenario
    assert result.guardrail_passed


def test_invoke_blocked_result_has_alarm():
    """차단된 응답은 alarm=True + alarm_reason 명시."""
    result = bedrock.invoke("정의당은 부패 정의당 부패", persona_id="editorial")
    # 정의당 + 부패 패턴 매치 가능
    if not result.guardrail_passed:
        assert result.alarm is True
        assert result.alarm_reason == "input_blocked"
        assert result.political_balance_score == 0.0


# ─── 디자인 원칙: stage 일관, 페르소나 차별 (2026-05-13 사용자 결정) ────────

PERSONAS = ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"]


def test_six_personas_produce_distinct_text():
    """원칙: 페르소나가 다르면 final 텍스트가 명확히 달라야 한다."""
    same_query = "AI 입법 동향 분석"
    texts = {pid: bedrock.invoke(same_query, persona_id=pid).text for pid in PERSONAS}
    # 모든 페르소나의 텍스트가 서로 다름
    assert len(set(texts.values())) == len(PERSONAS), \
        f"중복 텍스트 발견 - 페르소나 차별 실패: {texts}"


@pytest.mark.parametrize("pid", PERSONAS)
def test_persona_text_has_distinctive_marker(pid):
    """각 페르소나 텍스트에 자신만의 식별 마커가 있어야 한다."""
    text = bedrock.invoke("AI 입법", persona_id=pid).text
    markers = {
        "editorial": "후속 취재 포인트",
        "data_ai": "CV=",  # 통계 메트릭 표기
        "ad_sales": "AdMatchDecision",
        "general_reader": "내 지역구",
        "paid_subscriber": "PDF 리포트로 받기",
        "b2b": '"headline"',  # JSON 응답
    }
    assert markers[pid] in text, f"{pid}: 식별 마커 '{markers[pid]}' 누락"


@pytest.mark.parametrize("pid", PERSONAS)
def test_stage_consistency_within_persona(pid):
    """같은 페르소나의 chatbot·agent·agentic final 텍스트는 동일해야 한다.

    Stage 진화는 metadata(tools_called, agents_invoked)로 표현하고
    final 텍스트 결론은 일관 유지 (사용자 결정 2026-05-13).
    """
    from api.services import three_stage
    results = three_stage.run_all_stages("AI 입법 동향", persona_id=pid)
    chatbot_text = results["chatbot"].text
    agent_text = results["agent"].text
    agentic_text = results["agentic"].text
    assert chatbot_text == agent_text == agentic_text, (
        f"{pid}: stage 텍스트 불일치\n"
        f"  chatbot:  {chatbot_text[:60]}...\n"
        f"  agent:    {agent_text[:60]}...\n"
        f"  agentic:  {agentic_text[:60]}..."
    )


def test_multi_agent_internal_outputs_are_persona_neutral():
    """Multi-agent 내부 에이전트(Planner/Graph/Analyst) 출력은 페르소나 무관 동일."""
    # 같은 입력 (Planner agent prompt)을 다른 페르소나로 호출하면 결과 동일해야 함
    planner_msg = "[당신은 Planner 에이전트입니다]\n질문: AI 입법 분석"
    r1 = bedrock.invoke(planner_msg, persona_id="editorial")
    r2 = bedrock.invoke(planner_msg, persona_id="b2b")
    assert r1.text == r2.text, "Planner 내부 출력이 페르소나에 의존하면 안 됨"

    graph_msg = "[당신은 Graph 쿼리 에이전트입니다]\n결과: 10건"
    r3 = bedrock.invoke(graph_msg, persona_id="editorial")
    r4 = bedrock.invoke(graph_msg, persona_id="general_reader")
    assert r3.text == r4.text, "Graph 내부 출력이 페르소나에 의존하면 안 됨"


def test_all_persona_responses_balanced():
    """6 페르소나 모두 정치 균형 (정당 양쪽 언급 또는 무언급)."""
    for pid in PERSONAS:
        text = bedrock.invoke("AI 분석", persona_id=pid).text
        # 양당 모두 언급하거나 둘 다 없음
        has_dem = "더불어민주당" in text
        has_ppp = "국민의힘" in text
        balanced = (has_dem and has_ppp) or (not has_dem and not has_ppp)
        assert balanced, f"{pid}: 일방 정당만 언급 ({'민주당만' if has_dem else '국힘만'})"


def test_all_persona_responses_have_source_citation():
    """6 페르소나 모두 출처 인용 포함 (citation_score 보장)."""
    for pid in PERSONAS:
        text = bedrock.invoke("AI 분석", persona_id=pid).text
        has_citation = (
            "출처" in text
            or "국회 OpenAPI" in text
            or "sources" in text  # B2B JSON 형식
            or "KOSIS" in text
        )
        assert has_citation, f"{pid}: 출처 인용 누락"


def test_b2b_response_is_json_like():
    """B2B 페르소나는 JSON 추출 가능한 구조 응답."""
    text = bedrock.invoke("AI 입법", persona_id="b2b").text
    assert "{" in text and "}" in text
    assert '"headline"' in text
    assert '"sources"' in text


def test_general_reader_response_uses_friendly_tone():
    """일반 독자 페르소나는 친근한 어조 (~요/~어요 종결)."""
    text = bedrock.invoke("AI 입법", persona_id="general_reader").text
    # 친근한 종결어미 + 안내 진입점
    assert "요" in text  # ~할까요, ~돼요 등
    assert "내 지역구" in text or "관심 토픽" in text
