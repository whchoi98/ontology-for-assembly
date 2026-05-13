"""Bedrock Sonnet 4.6 invoke 단일 진입점.

모든 LLM 호출은 이 함수를 통과해야 한다. 직접 boto3 `invoke_model` 호출 금지.
이 함수가 자동으로 처리:
1. persona system prompt 합성 (NEUTRALITY_GUARD_SUFFIX 포함)
2. Bedrock Guardrails 입력 스크럽 (ADR-0004 Layer 1)
3. Bedrock Sonnet 4.6 invoke
4. 출력 정치 중립성 평가 + annotate (ADR-0004 Layer 3)
5. 알람 감지

`DEMO_PUBLIC_MODE=true`에서는 mock 응답으로 fallback. 테스트·로컬 개발에 사용.

References:
- ADR-0001 (Sonnet 4.6 고정, Haiku silent downgrade 금지)
- ADR-0004 (정치 중립성 다층 가드레일)
- spec §7 핵심 컴포넌트 노트
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from api.services import guardrails
from api.services.persona import system_prompt

__all__ = ["InvokeResult", "invoke"]


# 기본 모델 — ADR-0001 D11. Haiku 등으로 silent downgrade 금지.
DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"


@dataclass(frozen=True)
class InvokeResult:
    """LLM 응답 + 메타데이터.

    `to_sse_final()` 결과를 SSE final event payload에 그대로 사용 가능.
    """
    text: str
    model_id: str
    persona_id: str
    scenario_code: str
    guardrail_passed: bool
    political_balance_score: float
    alarm: bool
    alarm_reason: Optional[str]
    balance_components: dict
    blocked_topics: list[str] = field(default_factory=list)

    def to_sse_final(self) -> dict:
        """SSE `{"type": "final", "data": {...}}` payload에 머지 가능한 dict."""
        return {
            "text": self.text,
            "model_id": self.model_id,
            "persona_id": self.persona_id,
            "scenario_code": self.scenario_code,
            "political_balance_score": self.political_balance_score,
            "balance_components": self.balance_components,
            "guardrail_passed": self.guardrail_passed,
            "alarm": self.alarm,
            "alarm_reason": self.alarm_reason,
            "blocked_topics": list(self.blocked_topics),
        }


def invoke(
    user_message: str,
    persona_id: Optional[str] = "editorial",
    scenario_code: str = "A",
    model_id: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> InvokeResult:
    """단일 진입점 LLM 호출.

    Args:
        user_message: 사용자 입력 (라우터에서 받은 query).
        persona_id: 6 페르소나 중 하나. None이면 editorial.
        scenario_code: A–N 한 글자.
        model_id: 미지정 시 BEDROCK_CHAT_MODEL_ID env 또는 Sonnet 4.6.
        temperature: Anthropic 권장 0.0–1.0.
        max_tokens: 응답 토큰 상한.

    Returns:
        InvokeResult — 텍스트 + 정치 중립성 메타데이터.

    Behavior:
        - 입력이 정치 중립성 가드레일에 차단되면 fallback 텍스트 + alarm=True 반환.
        - 정상 응답도 political_balance_score < 0.8이면 alarm=True (응답은 전달).
        - DEMO_PUBLIC_MODE에서는 mock 응답으로 fallback.
    """
    import time
    pid = persona_id or "editorial"
    selected_model = model_id or os.environ.get("BEDROCK_CHAT_MODEL_ID", DEFAULT_MODEL_ID)
    t0 = time.monotonic()

    # 1. System prompt — persona tone + KPI + NEUTRALITY_GUARD_SUFFIX 자동 첨부
    sys_prompt = system_prompt(pid, scenario_code)

    # 2. 입력 가드 (ADR-0004 Layer 1)
    input_check = guardrails.check_prompt(user_message, pid)
    if not input_check.passed:
        result = _blocked_input_result(
            blocked_topics=list(input_check.blocked_topics),
            persona_id=pid,
            scenario_code=scenario_code,
            model_id=selected_model,
        )
        _record(result, int((time.monotonic() - t0) * 1000))
        return result

    # 3. Bedrock invoke (또는 demo mock)
    response_text = _bedrock_invoke(
        sys_prompt=sys_prompt,
        user_message=user_message,
        model_id=selected_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # 4. 출력 평가 + annotate (ADR-0004 Layer 3)
    annotation = guardrails.annotate_response(response_text, pid)

    result = InvokeResult(
        text=response_text,
        model_id=selected_model,
        persona_id=pid,
        scenario_code=scenario_code,
        guardrail_passed=annotation["guardrail_passed"],
        political_balance_score=annotation["political_balance_score"],
        alarm=annotation["alarm"],
        alarm_reason=annotation["alarm_reason"],
        balance_components=annotation["balance_components"],
        blocked_topics=[],
    )

    # 5. 운영 콘솔 trace 링버퍼 기록 (ADR-0004 Layer 3 메트릭)
    _record(result, int((time.monotonic() - t0) * 1000))
    return result


# ─── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _record(result: "InvokeResult", duration_ms: int) -> None:
    """LLM 호출 trace 1건을 ops_metrics 링버퍼에 기록."""
    # Lazy import - 순환 의존 회피 + 테스트에서 mock 가능.
    from api.services.ops_metrics import record_trace
    record_trace(
        persona_id=result.persona_id,
        scenario_code=result.scenario_code,
        model_id=result.model_id,
        political_balance_score=result.political_balance_score,
        alarm=result.alarm,
        alarm_reason=result.alarm_reason,
        blocked_topics=result.blocked_topics,
        duration_ms=duration_ms,
    )

def _blocked_input_result(
    blocked_topics: list[str],
    persona_id: str,
    scenario_code: str,
    model_id: str,
) -> InvokeResult:
    """입력 차단 시 안전 fallback InvokeResult."""
    return InvokeResult(
        text="(이 요청은 정치 중립성 가드레일에 의해 차단되었습니다. 다른 표현으로 질문해 주세요.)",
        model_id=model_id,
        persona_id=persona_id,
        scenario_code=scenario_code,
        guardrail_passed=False,
        political_balance_score=0.0,
        alarm=True,
        alarm_reason="input_blocked",
        balance_components={},
        blocked_topics=blocked_topics,
    )


def _bedrock_invoke(
    sys_prompt: str,
    user_message: str,
    model_id: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Bedrock invoke 분기.

    Demo mode (`DEMO_PUBLIC_MODE=true`): mock 응답.
    Production: boto3 `bedrock-runtime.invoke_model`.
    """
    if _demo_mode():
        return _mock_response(user_message, sys_prompt)

    # Production 경로
    from api.aws_clients import session as boto_session  # lazy import

    client = boto_session().client("bedrock-runtime")
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": sys_prompt,
        "messages": [{"role": "user", "content": user_message}],
    })
    response = client.invoke_model(modelId=model_id, body=body)
    payload = json.loads(response["body"].read())
    # Anthropic on Bedrock: content는 list of {type, text}
    return "".join(part.get("text", "") for part in payload.get("content", []))


def _mock_response(user_message: str, sys_prompt: str) -> str:
    """Demo mode mock - 페르소나별로 차별화된 final 응답.

    원칙 (사용자 결정 2026-05-13):
    - 같은 질문 → 일관된 답변: 3 stage의 final 텍스트 결론은 같음
    - 페르소나별 → 다른 답변: 어조·깊이·형식이 청중에 맞게 변환

    Stage 진화 메시지는 process metadata(tools_called, agents_invoked)로 전달.
    Final 텍스트는 stage 무관 페르소나 일관성 유지.

    예외: Multi-agent 내부 에이전트(Planner/Graph/Analyst) 출력은 internal process
    detail이므로 페르소나 무관 균일. Editor의 최종 출력부터 페르소나 적용.
    """
    # 1. Multi-agent 내부 에이전트 — 페르소나 무관 (internal process detail)
    if "[당신은 Planner 에이전트입니다]" in user_message:
        return _mock_planner_plan()
    if "[당신은 Graph 쿼리 에이전트입니다]" in user_message:
        return _mock_graph_summary()
    if "[당신은 분석가 에이전트입니다]" in user_message:
        return _mock_analyst_interpretation()

    # 2. Final 응답 (Stage 1·2·3 모두) — 페르소나 키 dispatch
    persona_id = _detect_persona_id(sys_prompt)
    return _PERSONA_MOCKS.get(persona_id, _mock_for_editorial)()


def _detect_persona_id(sys_prompt: str) -> str:
    """system_prompt에서 페르소나 ID 추출.

    persona.system_prompt()가 "사용자는 <name_kr> (<tier> tier)이며..." 형식으로
    합성하므로 그 부분에서 매칭.
    """
    if "사용자는 편집국" in sys_prompt:
        return "editorial"
    if "사용자는 데이터·AI" in sys_prompt:
        return "data_ai"
    if "사용자는 광고·세일즈" in sys_prompt:
        return "ad_sales"
    if "사용자는 일반 독자" in sys_prompt:
        return "general_reader"
    if "사용자는 유료 구독자" in sys_prompt:
        return "paid_subscriber"
    if "사용자는 기업" in sys_prompt or "정책 인텔리전스" in sys_prompt:
        return "b2b"
    return "editorial"  # fallback


# ─── Multi-agent 내부 (페르소나 무관) ───────────────────────────────────────

def _mock_planner_plan() -> str:
    return (
        "1. AI 관련 의안 검색 및 발의자 식별\n"
        "2. 발의자별 공동발의 네트워크 추출\n"
        "3. 표결 협력 패턴 분석 (정당 간 일치율)\n"
        "4. 토픽 분포 + 시계열 추세 확인\n"
        "5. 후속 취재 포인트 도출"
    )


def _mock_graph_summary() -> str:
    return (
        "Neptune 조회 결과 요약 (출처: 국회 OpenAPI 2026-05):\n"
        "- 의안 노드 10건 (상태: 발의 5 / 상임위 3 / 본회의 1 / 가결 1)\n"
        "- 발의자 노드 8명 (더불어민주당 5, 국민의힘 3)\n"
        "- 공동발의 엣지 23개, 평균 연결도 2.3\n"
        "- 표결 노드 8건 (찬반 분포 균형)\n"
        "핵심 패턴: ○○○ 의원이 공동발의 허브 역할."
    )


def _mock_analyst_interpretation() -> str:
    return (
        "Graph 결과 해석:\n"
        "- AI 입법은 양당이 공유하는 의제. 표결 일치율 62%는 협력적 양상.\n"
        "- 공동발의 허브(○○○ 의원)는 양당 의원과 모두 연결되어 정파 무관 협업.\n"
        "\n추가 가설 2개:\n"
        "1. 허브 의원의 지역구 산업 분포가 의안 카테고리(산업 4건)와 상관 가능성.\n"
        "2. 표결 일치율이 의안 단계(상임위 vs 본회의)에 따라 다를 가능성. "
        "→ Graph 에이전트에 재질의 필요: 단계별 일치율 분리 조회."
    )


# ─── 페르소나별 final 응답 ──────────────────────────────────────────────────

# 같은 데이터 결론을 6 가지 청중 언어로 번역:
#   - 발의 10건 (더불어민주당 5, 국민의힘 3, 기타 2)
#   - 핵심 의원 3명 (○○○, △△△, □□□)
#   - 양당 표결 일치율 62%
#   - 카테고리: 산업 4 / 법무 3 / 문화 3
# 어조·구조·진입점만 페르소나에 맞춰 변환.

def _mock_for_editorial() -> str:
    return (
        "[편집국 기자] AI 입법 동향 — 22대 국회 1분기 분석\n"
        "\n"
        "22대 국회 첫 분기 AI 관련 의안 10건 발의 — 더불어민주당 5건, 국민의힘 3건, "
        "기타 2건. 공동발의 핵심 의원 ○○○이 양당 사이의 허브 역할. "
        "표결 일치율 62%로 협력적 입법 양상 "
        "(출처: 국회 OpenAPI 2026-05).\n"
        "\n"
        "후속 취재 포인트:\n"
        "- ○○○ 의원 지역구 산업 분포 ↔ 발의 법안 카테고리 상관관계\n"
        "- 의안 단계별(상임위 vs 본회의) 표결 일치율 변화 가능성\n"
        "- 1분기 미디어 화제성과 발의 빈도 차이"
    )


def _mock_for_data_ai() -> str:
    return (
        "[데이터·AI 데스크] AI 입법 정량 분석 (22대 1분기, 2026-01 ~ 2026-04)\n"
        "\n"
        "- 발의 건수: n=10\n"
        "- 발의자 정당 분포: 더불어민주당 5 / 국민의힘 3 / 기타 2\n"
        "- 공동발의 평균 연결도: 2.3 ± 0.4 (CV=0.17)\n"
        "- 표결 일치율: 62% (95% CI: 54–70%, n=10)\n"
        "- 카테고리 엔트로피: 1.49 (균형 분포)\n"
        "- 카테고리: 산업 4 / 법무 3 / 문화 3\n"
        "\n"
        "추가 분석 가설:\n"
        "1. 허브 노드(○○○) 제거 시 네트워크 클러스터 분리 가능성\n"
        "2. 단계별 일치율 분산 — 본회의 표결 vs 상임위 통과 시점 비교\n"
        "(출처: 국회 OpenAPI 2026-05, sample_size=10)"
    )


def _mock_for_ad_sales() -> str:
    return (
        "[광고·세일즈] AI 입법 콘텐츠 광고 적합도 분석\n"
        "\n"
        "콘텐츠 토픽: AI 입법, 데이터·산업 정책 — 매우 적합\n"
        "- 추천 광고 카테고리: 데이터 솔루션, 보안, 컴플라이언스, 클라우드\n"
        "- 회피 토픽: 정치 민감 사안 없음 (안전 콘텐츠)\n"
        "\n"
        "AdMatchDecision 모드 비교:\n"
        "- keyword 매칭 score: 0.45 (낮은 정확도)\n"
        "- embedding 매칭 score: 0.71 (중)\n"
        "- Agent 판단 score: 0.87 (allow, 정책 정보성 콘텐츠 + 광고주 평판 양립)\n"
        "\n"
        "기준 데이터: 의안 10건 발의(더불어민주당 5 + 국민의힘 3 + 기타 2), 양당 일치율 62% "
        "(출처: 국회 OpenAPI + 합성 광고 인벤토리)."
    )


def _mock_for_general_reader() -> str:
    return (
        "[독자 안내] AI 관련 법, 어떻게 진행되고 있을까요?\n"
        "\n"
        "22대 국회 첫 분기에 10건의 AI 관련 법안이 발의되었어요. "
        "더불어민주당과 국민의힘 양쪽 의원들이 함께 발의한 경우가 많아서, "
        "협력적으로 다루고 있는 분야로 볼 수 있어요. "
        "표결에서도 양당이 함께 찬성한 비율이 62%로 높은 편이에요 "
        "(출처: 국회 OpenAPI 2026-05).\n"
        "\n"
        "관련해서 더 알고 싶다면:\n"
        "- '내 지역구 의원'이 어떤 활동을 했는지 확인해보세요\n"
        "- 'AI'를 관심 토픽에 추가하면 새 법안 발의 시 안내 받을 수 있어요"
    )


def _mock_for_paid_subscriber() -> str:
    return (
        "[심층 분석] AI 입법 동향 심층 리포트 — 22대 국회 1분기\n"
        "\n"
        "## 핵심 발견\n"
        "AI 관련 의안 10건 발의 — 더불어민주당 5건, 국민의힘 3건, 기타 2건. "
        "공동발의 핵심 의원 ○○○이 양당 의원과 모두 연결된 허브 역할. "
        "표결 일치율 62%로 정파를 초월한 협력적 의제로 정착 중.\n"
        "\n"
        "## 의안 단계별 진행률\n"
        "- 발의: 5건 (50%)\n"
        "- 상임위 심사: 3건 (30%)\n"
        "- 본회의 상정: 1건 (10%)\n"
        "- 가결: 1건 (10%)\n"
        "\n"
        "## 카테고리 분포\n"
        "- 산업 진흥·지원: 4건\n"
        "- 법무·개인정보: 3건\n"
        "- 디지털 문화: 3건\n"
        "\n"
        "(출처: 국회 OpenAPI 2026-05)\n"
        "\n"
        "[PDF 리포트로 받기] [○○○ 의원 알림 설정] [의원 비교 도구]"
    )


def _mock_for_b2b() -> str:
    return (
        "[정책 인텔리전스 API 응답]\n"
        "{\n"
        '  "headline": "22대 국회 AI 입법 동향 — 1분기 리뷰",\n'
        '  "summary": "AI 관련 의안 10건 발의 — 양당 협력 의제로 정착, 표결 일치율 62%",\n'
        '  "impact_score": 0.85,\n'
        '  "confidence": 0.92,\n'
        '  "key_actors": ["○○○", "△△△", "□□□"],\n'
        '  "party_distribution": {"더불어민주당": 5, "국민의힘": 3, "기타": 2},\n'
        '  "category_distribution": {"산업": 4, "법무": 3, "문화": 3},\n'
        '  "agreement_rate": 0.62,\n'
        '  "bill_stage": {"proposed": 5, "in_committee": 3, "in_plenary": 1, "passed": 1},\n'
        '  "sources": ["국회 OpenAPI 2026-05"]\n'
        "}\n"
        "\n"
        "관련 KOSIS 통계: https://kosis.kr/statHtml/statHtml.do?orgId=440\n"
        "관련 정부 백서: 2025 AI 산업 백서"
    )


# 페르소나 키 → mock 함수 dispatch
_PERSONA_MOCKS = {
    "editorial": _mock_for_editorial,
    "data_ai": _mock_for_data_ai,
    "ad_sales": _mock_for_ad_sales,
    "general_reader": _mock_for_general_reader,
    "paid_subscriber": _mock_for_paid_subscriber,
    "b2b": _mock_for_b2b,
}


def _demo_mode() -> bool:
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"
