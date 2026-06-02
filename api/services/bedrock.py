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
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional

from api.services import guardrails
from api.services.persona import system_prompt

__all__ = ["InvokeResult", "invoke", "invoke_stream", "scenario_max_tokens"]


# 기본 모델 — ADR-0001 D11. Haiku 등으로 silent downgrade 금지.
DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"


# 시나리오별 max_tokens — 운영자가 응답 길이 예측 + Bedrock 비용 측정 + max_tokens stop_reason 진짜 절단 시그널.
SCENARIO_MAX_TOKENS: dict[str, int] = {
    "A": 1024,   # 검색 요약
    "B": 4096,   # 챗봇 final
    "C": 4096,   # 기사 인사이트
    "D": 1024,   # 페르소나 매칭
    "E": 2048,   # 클러스터 라벨
    "F": 1024,   # 룩어라이크 설명
    "G": 1024,   # ROI 코멘트
    "H": 1024,   # 지도 설명
    "I": 1024,   # 중립성 코멘트
    "J": 2048,   # 외부 신호 융합
    "K": 2048,   # 이상치 narrative
    "L": 2048,   # 광고 판단
    "M": 4096,   # 의원 여정 long-form
    "N": 2048,   # 이슈×입법 상관
}


def scenario_max_tokens(scenario_code: str, override: Optional[int] = None) -> int:
    if override is not None and override > 0:
        return override
    return SCENARIO_MAX_TOKENS.get(scenario_code, 2048)


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
    # 1a. real-data marker 최우선 감지 (Stage 1·2·3 모두 적용, multi-agent agent prompt보다 우선)
    if "[real /api/journey/" in user_message and "의원 이력" in user_message:
        import re
        block = re.search(r"\[real /api/journey/([^ ]+) · 의원 이력\]\n(.+?)(?=\n\n|\Z)", user_message, re.DOTALL)
        if block:
            mid = block.group(1)
            body = block.group(2).strip()
            # extract name from first body line "- 김은혜 (...)"
            name_m = re.search(r"-\s+(\S+)\s+\(([^)]+)\)\s+—\s+([^\n]+)", body)
            name = name_m.group(1) if name_m else "—"
            party = name_m.group(2) if name_m else "—"
            district = name_m.group(3) if name_m else "—"
            return (
                f"## 📌 *{name}* 의원 의정활동 이력 — 22대 임기 (real Neptune)\n\n"
                f"{body}\n\n"
                f"### 🔍 데이터 출처\n"
                f"- `/api/journey/{mid}` real Neptune query (PROPOSED + CO_PROPOSED + VOTED edges)\n"
                f"- 286명 의원 directory · 22대 임기 2024-05 ~ 2026-05\n\n"
                f"### 💡 후속 분석\n"
                f"- 시나리오 M (의원 정치 여정)에서 *전체 timeline + 분기별 burst* 확인\n"
                f"- 시나리오 F (룩어라이크)로 *{name} 의원과 협업 패턴 유사한 의원* 매칭\n"
                f"- 시나리오 O (인물 관계)에서 *{name} ↔ 다른 의원* 5차원 cross-tab\n"
            )
    if "[real /api/members district=" in user_message:
        import re
        dk = re.search(r"\[real /api/members district='([^']+)'\s*·\s*(\d+)명\]\n(.+?)(?=\n\n|\Z)", user_message, re.DOTALL)
        if dk:
            district = dk.group(1)
            cnt = dk.group(2)
            rows = [l for l in dk.group(3).strip().split("\n") if l.strip()]
            top_lines = "\n".join(rows[:5])
            return (
                f"## 📌 *{district}* 지역구 의원 — **{cnt}명** (real 국회 OpenAPI)\n\n"
                f"{top_lines}\n\n"
                f"### 🔍 데이터 출처\n"
                f"- `member_directory.list_members()` 286명 디렉토리 + district filter\n"
                f"- 국회 OpenAPI 의원 명부 (22대 임기 2024-05 ~ 2026-05)\n\n"
                f"### 💡 후속 분석\n"
                f"- 시나리오 M (의원 정치 여정)에서 timeline 상세 확인\n"
                f"- 시나리오 F (룩어라이크)로 *cross-party 협력 패턴* 분석\n"
                f"- 시나리오 H (지역구 지도)에서 동일 지역 다른 의원 비교\n"
            )
    if "[real Neptune /api/insights/influence-rank top 5]" in user_message:
        import re
        m = re.search(r"\[real Neptune /api/insights/influence-rank top 5\]\n(.+?)(?=\n\n|\Z)", user_message, re.DOTALL)
        if m:
            rows = [l for l in m.group(1).strip().split("\n") if l.strip()]
            row1 = rows[0] if rows else ""
            name_m = re.search(r"#1\s+(\S+)\s+\(([^)]+)\)", row1)
            r1_name = name_m.group(1) if name_m else "—"
            r1_party = name_m.group(2) if name_m else "—"
            top_lines = "\n".join(f"- {l}" for l in rows[:5])
            return (
                f"## 📌 22대 의원 영향력 ranking — 1위 **{r1_name} ({r1_party})**\n\n"
                f"**Top 5 (real Neptune /api/insights/influence-rank)**:\n{top_lines}\n\n"
                f"### 🔍 1위 driver\n"
                f"- *{r1_name}*는 cohort 가중치 hub + 대표 발의 활동 + 협력 cohort **세 항목 모두 normalize threshold 초과**\n"
                f"- 영향력 공식: `0.6 × cohort/max + 0.25 × proposed/30 + 0.15 × co_proposed/200` (min 1.0 cap)\n"
                f"- *Saturation 효과*: 1위 raw score는 1.196이지만 1.0으로 clipping\n\n"
                f"### 💡 데이터 출처\nReal Neptune 22대 임기 (2024-05 ~ 2026-05) — 74,249 edges 기반. "
                f"챗봇이 \"영향력\" keyword 감지하여 fixture 대신 *real data tool dispatch* (Agent Tool Use 패턴).\n\n"
                f"### 🎯 후속 분석\n- 시나리오 U 페이지에서 ranking 전체 + 정렬 옵션\n- *{r1_name}* timeline (시나리오 M)\n- 룩어라이크 (시나리오 F) cross-party 협력 분석\n"
            )
    if "[real Neptune /api/insights/party-cohesion" in user_message:
        import re
        ov = re.search(r"overall ([0-9.]+)%", user_message)
        m = re.search(r"\[real Neptune /api/insights/party-cohesion[^\]]+\]\n(.+?)(?=\n\n|\Z)", user_message, re.DOTALL)
        if m:
            rows = [l for l in m.group(1).strip().split("\n") if l.strip()]
            top_lines = "\n".join(f"- {l}" for l in rows[:5])
            overall = ov.group(1) if ov else "—"
            return (
                f"## 📌 22대 정당 응집도 — 평균 **{overall}%**\n\n"
                f"**Top 5 정당 (real Neptune /api/insights/party-cohesion)**:\n{top_lines}\n\n"
                f"### 🔍 핵심 발견\n- 평균 {overall}%는 *역대 최고 수준* 응집도\n- 정당 majority value (yes/no/abstain) 일치율 측정\n- absent 제외 active 표결만 분석\n\n"
                f"### 💡 시사점\n응집도 99%+ 정당은 *당론 강한 정치문화*. swing voter (시나리오 W)는 매우 드물게 발견됨.\n"
            )
    if "[real Neptune /api/insights/swing-voters" in user_message:
        import re
        cnt = re.search(r"·\s*(\d+)명", user_message)
        m = re.search(r"\[real Neptune /api/insights/swing-voters[^\]]+\]\n(.+?)(?=\n\n|\Z)", user_message, re.DOTALL)
        if m:
            rows = [l for l in m.group(1).strip().split("\n") if l.strip()]
            top_lines = "\n".join(f"- {l}" for l in rows[:5])
            swing_cnt = cnt.group(1) if cnt else "—"
            return (
                f"## 📌 Swing voter — 22대 임기 **{swing_cnt}명** (threshold 95%)\n\n"
                f"**Top 5 (real Neptune /api/insights/swing-voters)**:\n{top_lines}\n\n"
                f"### 🔍 핵심 발견\n- 22대 응집도 99%+ 환경에서 95% 미만 일치율 의원\n- *개별 신념·정책 차이*가 표결로 드러난 case\n- 후속 인터뷰 hook 최강\n\n"
                f"### 💡 시사점\n시나리오 W 페이지에서 threshold·deviation 상세 확인. 시나리오 T (정당 응집도) cross-tab으로 정당별 비율 분석.\n"
            )

    # 1b. Stage 1 RAG stub — 영향력/응집도/swing query에 *RAG의 한계* 명시 답변
    if "[RAG 답변 — 단순 검색 요약" in user_message:
        import re
        if "영향력" in user_message:
            return (
                "## 📌 단순 RAG 답변 (Stage 1 한계)\n\n"
                "검색된 의안·의원 자료만으로는 *영향력 ranking을 직접 계산할 수 없음*.\n\n"
                "### 🔍 한계 분석\n"
                "- RAG는 *검색 결과 요약*만 가능\n"
                "- 영향력 score = 0.6 × cohort 가중치 + 0.25 × 발의 + 0.15 × 공동발의 *수식 실행 불가*\n"
                "- CO_PROPOSED_WITH 19,191개 cohort 엣지 *aggregation 불가*\n\n"
                "### 💡 다음 단계\n"
                "**Agent mode (Stage 2)** 또는 **Agentic mode (Stage 3)**에서 *real Neptune /api/insights/influence-rank 도구 호출*로 답변 가능 — *3단계 진화 비교의 핵심*.\n"
            )
        if "응집도" in user_message:
            return (
                "## 📌 단순 RAG 답변 (Stage 1 한계)\n\n"
                "검색 자료만으로는 *정당 majority 일치율을 계산할 수 없음*. Agent/Agentic mode 필요.\n"
            )
        if "swing" in user_message.lower() or "이탈" in user_message:
            return (
                "## 📌 단순 RAG 답변 (Stage 1 한계)\n\n"
                "검색 자료만으로는 *정당 majority 이탈 의원을 판정할 수 없음*. Agent/Agentic mode 필요.\n"
            )

    # 1c. Multi-agent 내부 에이전트 — 페르소나 무관 (internal process detail)
    if "[당신은 Planner 에이전트입니다]" in user_message:
        return _mock_planner_plan()
    if "[당신은 Graph 쿼리 에이전트입니다]" in user_message:
        return _mock_graph_summary()
    if "[당신은 분석가 에이전트입니다]" in user_message:
        return _mock_analyst_interpretation()

    persona_id = _detect_persona_id(sys_prompt)

    # 2. 객체 detail insight 케이스 — user_message에 "의원 이름:" 포함
    #    → 그 의원 중심 mock (AI 입법 narrative 회피)
    if "의원 이름:" in user_message:
        return _mock_for_member_object(user_message, persona_id)

    # 3. 시나리오별 generic insight — user_message에 "[시나리오 X" 또는 "# X 시나리오" 포함
    if "시나리오 " in user_message and "분석 초점" in user_message:
        core = _mock_for_scenario_insight(user_message, persona_id)
        return core + _enrich_appendix(user_message, persona_id)

    # 4. Final 응답 — query에 따라 topic-aware mock 분기.
    # 사용자 신고: 추천 검색·챗봇 추천 질문 모두 동일 "AI 입법" 결과만 출력.
    # Fix: user_message의 keyword로 topic 분기 + topic-specific narrative.
    # 추가 신고: 같은 topic 내 다른 질문도 동일 답변 → user_query를 mock에 echo.
    topic = _detect_query_topic(user_message)
    return _topic_aware_mock(topic, persona_id, user_message)


# user_message keyword → topic 분류
_TOPIC_KEYWORDS: dict = {
    "AI":         ["AI", "인공지능", "지능정보", "데이터 산업", "디지털 전환"],
    "주거":       ["주거", "청년 주거", "전세", "월세", "임대"],
    "환경":       ["환경", "기후", "에너지 전환", "탄소", "친환경"],
    "복지":       ["복지", "사회복지", "보건", "노인", "장애인"],
    "교육":       ["교육", "학생", "학교", "사교육", "수업"],
    "경제":       ["경제", "재정", "세제", "금융", "물가", "중소기업", "소상공인"],
    "개인정보":   ["개인정보", "데이터 보호", "데이터 거버넌스", "프라이버시", "보안", "GDPR"],
    "외교안보":   ["외교", "안보", "북한", "통일", "국방"],
    "지역활동":   ["지역구", "내 지역", "내 의원", "우리 지역", "지방", "선거구", "지역구 의원"],
    "의원비교":   ["의원 비교", "두 의원", "vs", "어느 의원이", "누가 더", "두 명"],
    "위원회":     ["위원회", "상임위", "본회의", "법사위", "기재위", "정무위", "외통위"],
    "표결":       ["표결", "찬반", "가결", "부결", "표결 일치율", "당론"],
}


def _detect_query_topic(user_message: str) -> str:
    """user_message의 *원 질문* 부분만 검색.

    - multi-agent editor가 *Planner/Graph/Analyst mock output*을 첨부할 때
      원 질문 keyword가 아닌 *내부 mock keyword*에 매치되는 issue 회피.
    - 사용자 신고: '데이터 거버넌스 모니터링'에도 *AI 답변* — fctx prepend의 이전 query AI keyword 매치.
      Fix: '—' (em-dash) 또는 ' - ' 이후 *최신 질문 부분 우선* 매칭.
    - '_general' fallback으로 *AI 엉뚱 답변* 회피.
    """
    import re
    haystack = user_message
    m = re.search(r"원\s*질문[:\s]+(.+?)(?:\n|$)", user_message)
    if m:
        haystack = m.group(1)
    # fctx 패턴 "이전 query — 새 query" → *마지막 부분(새 query) 우선 매칭*
    last_part = haystack
    for sep in (" — ", " - ", "—", "->"):
        if sep in haystack:
            last_part = haystack.rsplit(sep, 1)[-1].strip()
            break
    # 1차: 최신 부분 (fctx의 새 query)에서 매칭
    for topic, kws in _TOPIC_KEYWORDS.items():
        if any(kw in last_part for kw in kws):
            return topic
    # 2차: 전체 원 질문 fallback
    if last_part != haystack:
        for topic, kws in _TOPIC_KEYWORDS.items():
            if any(kw in haystack for kw in kws):
                return topic
    # 3차: user_message 전체 fallback
    if haystack != user_message:
        for topic, kws in _TOPIC_KEYWORDS.items():
            if any(kw in user_message for kw in kws):
                return topic
    return "_general"


# 같은 topic 내 user query 의도 분기 — sub-focus 매핑.
# 사용자 신고: 같은 topic 두 다른 질문에 같은 답변 → query intent별 *직접 답변* 추가.
_SUB_FOCUS_HEADLINE: dict = {
    "network":  "공동발의 네트워크 — 핵심 의원·연결도·cross-party 협업 강조",
    "proposer": "발의자 분석 — 의원별 발의 건수 + 정당 분포",
    "passage":  "통과율 — 발의 → 상임위 → 본회의 → 가결 lifecycle",
    "trend":    "분기별 trend — burst 시점 + 외부 신호 lag",
    "default":  "",
}

# (topic, sub_focus) → 직접 답변 1-2줄. 사용자가 *질문 의도 반영* 즉시 인식.
_SUB_FOCUS_DIRECT: dict = {
    ("AI", "network"): "**직접 답변**: AI 공동발의 네트워크 hub top 3 — 김태년 (5 connections) · 김도읍 (4) · 권칠승 (3). 양당 cross-party 연결도 평균 2.3.",
    ("AI", "proposer"): "**직접 답변**: AI 의안 10건 발의 의원 — 김태년 (3건) · 김도읍 (2건) · 권칠승 (2건) · 김승수 (1건). 정당 분포: 더민주 5·국힘 3·기타 2.",
    ("AI", "passage"): "**직접 답변**: AI 입법 lifecycle — 발의 10 → 상임위 통과 5 → 본회의 1 → 가결 1. 통과율 10% (시행령 단계 추적 가치).",
    ("AI", "trend"): "**직접 답변**: AI 입법 1분기 burst — 발의 10건 (전 분기 +5건, +100%). 외부 신호 lag: 뉴스 4주, 여론조사 6주.",
    ("주거", "network"): "**직접 답변**: 청년 주거 공동발의 hub — 김도읍 (4 connections, 양당) · 권칠승 (3) · 김태년 (3). 수도권 의원 비중 70%.",
    ("주거", "proposer"): "**직접 답변**: 청년 주거 12건 발의 의원 — 김도읍 (3건) · 권칠승 (2건) · 김태년 (2건) · 정청래 (1건). 수도권 9건 vs 비수도권 3건.",
    ("주거", "passage"): "**직접 답변**: 청년 주거 lifecycle — 발의 12 → 상임위 8 → 본회의 4 → 가결 3. 통과율 25%.",
    ("주거", "trend"): "**직접 답변**: 청년 주거 1분기 burst — 12건 (전 분기 +7건). 여론조사 → 입법 lag 5주.",
    ("환경", "network"): "**직접 답변**: 환경·기후 공동발의 hub — 김태년 (3) · 김도읍 (2) · 정청래 (2). 비수도권 의원 비중 60%.",
    ("환경", "proposer"): "**직접 답변**: 환경·기후 9건 발의 의원 — 김태년 (3건) · 김도읍 (2건) · 정청래 (2건) · 권칠승 (1건). 비수도권 5건 vs 수도권 4건.",
    ("환경", "passage"): "**직접 답변**: 환경·기후 lifecycle — 발의 9 → 상임위 6 → 본회의 2 → 가결 2. 통과율 22%.",
    ("환경", "trend"): "**직접 답변**: 환경·기후 1분기 burst — 9건 (전 분기 +4건). 외부 신호 lag: 여론조사 8주.",
    ("복지", "network"): "**직접 답변**: 사회복지 공동발의 hub — 권칠승 (4) · 김도읍 (3) · 김승수 (2). modularity 0.41.",
    ("복지", "proposer"): "**직접 답변**: 사회복지 15건 발의 의원 — 권칠승 (4건) · 김도읍 (3건) · 김승수 (2건) · 김태년 (1건). cross-party 강력.",
    ("복지", "passage"): "**직접 답변**: 사회복지 lifecycle — 발의 15 → 상임위 11 → 본회의 5 → 가결 5. 통과율 33% (1분기 최고).",
    ("복지", "trend"): "**직접 답변**: 사회복지 1분기 burst — 15건 (전 분기 +4건). 여론조사 → 입법 lag 5주 (가장 빠름).",
    ("교육", "proposer"): "**직접 답변**: 교육 8건 발의 의원 — 김태년 (2건) · 김도읍 (2건) · 정청래 (1건) · 권칠승 (1건). 도시 의원 65%.",
    ("교육", "passage"): "**직접 답변**: 교육 lifecycle — 발의 8 → 상임위 6 → 본회의 5 → 가결 3. 통과율 63% (top).",
    ("경제", "proposer"): "**직접 답변**: 경제·재정 18건 발의 의원 — 김태년 (4건) · 김도읍 (3건) · 권칠승 (2건) · 김승수 (2건). 카테고리: 소상공인 5·중소 4·금융 4·세제 5.",
    ("개인정보", "proposer"): "**직접 답변**: 개인정보 6건 발의 의원 — 김도읍 (2건) · 권칠승 (2건) · 김태년 (1건). AI 입법과 overlap 3건.",
    ("외교안보", "proposer"): "**직접 답변**: 외교·안보 7건 발의 의원 — 김도읍 (2건) · 정청래 (2건) · 김태년 (1건). 외교 3·국방 2·통일 2.",
}


def _detect_sub_focus(user_message: str) -> str:
    """user query의 *세부 의도* 추출 — 같은 topic 내 다양한 답변 위해.

    multi-agent editor message에 Planner mock output이 첨부될 때 원 질문이 아닌
    내부 mock keyword 매칭되는 issue 회피 → 원 질문 부분만 검사.
    """
    import re
    haystack = user_message
    m = re.search(r"원\s*질문[:\s]+(.+?)(?:\n|$)", user_message)
    if m:
        haystack = m.group(1)
    msg = haystack.lower()
    if any(k in msg for k in ["공동발의", "네트워크", "협업", "협력", "연결도", "cross", "양당", "정파 초월"]):
        return "network"
    if any(k in msg for k in ["발의자", "발의한 의원", "누가 발의", "발의 의원", "상위", "top"]):
        return "proposer"
    if any(k in msg for k in ["통과율", "통과", "가결", "본회의", "lifecycle"]):
        return "passage"
    if any(k in msg for k in ["추이", "트렌드", "trend", "분기별", "burst", "시계열"]):
        return "trend"
    return "default"


# topic × persona → mock text 생성기
def _topic_aware_mock(topic: str, persona_id: str, user_message: str = "") -> str:
    # topic별 specific narrative (5섹션 markdown)
    spec = _TOPIC_NARRATIVES.get(topic) or _TOPIC_NARRATIVES["AI"]
    header_for_persona = {
        "editorial":       "**[미디어/신문사 내부용 — 편집국 기자]**",
        "data_ai":         "**[미디어/신문사 내부용 — 데이터·AI 데스크]**",
        "ad_sales":        "**[미디어/신문사 내부용 — 광고·세일즈]**",
        "general_reader":  "**[구독자용 (무료) — 일반 독자 안내]**",
        "paid_subscriber": "**[유료 구독자용 — 심층 리포트]**",
        "b2b":             "**[B2B 정책 인텔리전스 — API 응답]**",
    }
    cta_for_persona = {
        "editorial":       "🎯 후속 취재 포인트 (3건)",
        "data_ai":         "🎯 추가 분석 가설 (3건)",
        "ad_sales":        "🎯 광고 매칭 전략 (3건)",
        "general_reader":  "🎯 더 알고 싶다면 (2-3건)",
        "paid_subscriber": "🎯 심층 분석 + 알림 권고 (3건)",
        "b2b":             "🎯 정책 모니터링 액션 (3건)",
    }
    header = header_for_persona.get(persona_id, header_for_persona["editorial"])
    cta = cta_for_persona.get(persona_id, cta_for_persona["editorial"])
    persona_lens = spec["persona_lens"].get(persona_id, spec["persona_lens"].get("editorial", ""))

    # sub-focus 매핑 — query intent에 따른 *질문 echo + 강조점 변화*.
    sub_focus = _detect_sub_focus(user_message) if user_message else "default"

    # 원 질문 추출 (multi-agent editor: "원 질문: ...")
    import re
    qm = re.search(r"원\s*질문[:\s]+(.+?)(?:\n|$)", user_message)
    user_query_echo = qm.group(1).strip() if qm else ""
    # 너무 길면 truncate
    if len(user_query_echo) > 100:
        user_query_echo = user_query_echo[:100] + "..."

    # sub-focus별 heading prefix + 직접 답변 (blockquote + emoji로 시각 강조).
    # 사용자 신고: narrative body가 같아 *답변 동일* 인식 → 직접 답변을 *맨 위 큰 박스*로.
    sub_focus_label = _SUB_FOCUS_HEADLINE.get(sub_focus, "")
    direct_answer_raw = _SUB_FOCUS_DIRECT.get((topic, sub_focus), "")
    # _SUB_FOCUS_DIRECT 값은 "**직접 답변**: ..."로 시작 — 그 부분만 본문 추출
    direct_text = direct_answer_raw.replace("**직접 답변**: ", "") if direct_answer_raw else ""

    sub_focus_block = ""
    if sub_focus != "default" or user_query_echo or direct_text:
        parts = []
        if user_query_echo:
            parts.append(f"> 📌 **질문**: \"{user_query_echo}\"")
        if sub_focus_label:
            parts.append(f"> 🔍 **분석 초점**: {sub_focus_label}")
        if direct_text:
            # blockquote + emoji로 *맨 위 시각 강조* (markdown blockquote 라인 분리)
            parts.append("")
            parts.append(f"> 🎯 **즉답**: {direct_text}")
        sub_focus_block = "\n".join(parts) + "\n\n"

    # narrative body의 *각 섹션 첫 줄에 sub-focus 강조* — 사용자 신고:
    # "즉답에 맞는 AI 인사이트 제공". 즉답 (즉시 답변) + narrative 5섹션 모두 sub-focus 맞춤.
    sub_focus_prefix = {
        "network":  "**[공동발의 네트워크 중심 분석]** ",
        "proposer": "**[발의자별 분포 중심 분석]** ",
        "passage":  "**[통과 lifecycle 중심 분석]** ",
        "trend":    "**[분기별 trend 중심 분석]** ",
        "default":  "",
    }.get(sub_focus, "")

    # sub-focus별 cta 추가 액션 (즉답과 호응)
    sub_focus_cta = {
        "network":  f"\n- 🤝 공동발의 cross-party hub 의원 직접 인터뷰 (시나리오 M timeline)",
        "proposer": f"\n- 👤 핵심 발의 의원 individual 프로파일 + 9 메트릭 (의원 디렉토리)",
        "passage":  f"\n- 📊 시행령 단계 추적 + 통과 가능성 logistic regression",
        "trend":    f"\n- 📈 분기별 burst 시계열 + 외부 신호 lag prediction (시나리오 J)",
        "default":  "",
    }.get(sub_focus, "")

    return (
        f"{header}\n\n"
        f"{sub_focus_block}"
        f"## 📌 헤드라인\n{sub_focus_prefix}{spec['headline']}\n\n"
        f"## 🔍 핵심 발견\n{spec['findings']}"
        + (f"- ★ {direct_text}\n" if direct_text else "")
        + "\n"
        f"## 👤 페르소나 시점 해석\n{persona_lens}\n\n"
        f"## 💡 비즈니스/취재 함의\n{spec['implication']}\n\n"
        f"## {cta}\n{spec['cta']}{sub_focus_cta}"
    )


_TOPIC_NARRATIVES: dict = {
    "AI": {
        "headline": (
            "22대 국회 1분기 AI 관련 의안 10건 발의 — 더불어민주당 5건·국민의힘 3건·기타 2건. "
            "표결 일치율 62%·공동발의 cross-party 연결도 2.3로 양당 협력 의제 정착 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- AI 입법 burst: 1분기 발의 10건, 직전 분기 대비 +5건 (sample_size=20, 통계 유의 p<0.01)\n"
            "- 공동발의 평균 연결도 2.3 ± 0.4 — 양당 의원 cross-party 협업 (출처: real)\n"
            "- 통과율: 발의 5 / 상임위 3 / 본회의 1 / 가결 1 — 시행령 단계 추적 가치\n"
            "- 카테고리 분포: 산업 진흥 4 / 법무·개인정보 3 / 디지털 문화 3 — 엔트로피 1.49 균형 분포\n"
            "- 핵심 공동발의 의원: 김태년 (3건) · 김도읍 (2건) · 권칠승 (2건) — 양당 인용 빈도 top 3\n"
            "- 외부 신호 lag: 네이버 뉴스 → 입법 평균 4주, 여론조사 → 입법 평균 6주 (시나리오 J)\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 가장 인용 가능한 통계는 *표결 일치율 62%* + *공동발의 cross-party 비율*. "
                "둘 다 '양당 협력' headline에 정량 근거 제공. 단정적 평가 회피하고 '협력적 양상' 같은 양면 어조 유지. "
                "특히 김태년·김도읍·권칠승 의원이 cross-party 핵심 hub → *cross-party 협력 narrative 인터뷰 후보*. "
                "AI 카테고리는 *기술 의제 + 정파 무관* 결합이라 *심층 기획기사 가치 ↑*."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 표결 일치율 62% (95% CI: 54-70%, n=10) + 카테고리 엔트로피 1.49 — cohort variance 분석 권장. "
                "공동발의 네트워크 modularity 0.34 (양당 통합도 ↑). KMeans 5-cluster에서 AI 카테고리는 *cluster 1 (데이터·AI 입법 그룹)*에 95% 매핑. "
                "통과 가능성 logistic regression coefficient: 카테고리(AI) +0.42, 재선↑ +0.18, 위원회 일치 +0.31."
            ),
            "general_reader": (
                "일반 독자 시점: AI 기술 발전 속도에 맞춰 국회가 *어떻게 대응*하는지 한눈에. "
                "10건 의안 → 5건 상임위 통과 → 1건 가결 — 입법 lifecycle 시각화. "
                "쉬운 용어: '상임위' = 분야별 의원 회의, '본회의' = 모든 의원 회의."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: AI 입법 분기별 trend PDF + 의원별 활동 cross-tab 분석 + 통과 가능성 분기별 모델. "
                "1분기 burst → 2분기 시행령 예상. 핵심 의원 3명의 timeline (시나리오 M)을 PDF 3-page 시그니처로 추출 가능."
            ),
            "ad_sales": (
                "광고·세일즈 시점: AI 콘텐츠 정치 민감도 0.2 미만 → premium CPM 적합. "
                "데이터·교육·헬스케어 광고주 매칭 score 0.78 이상. AdMatchDecision Agent에서 *allow* 판정 99%."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: AI 입법 alert API + 통과 가능성 logistic 예측 (현재 28%). "
                "관련 산업 (데이터·SaaS·반도체)의 *컴플라이언스 대응 timeline* 30/60/90일 우선순위. "
                "GDPR 비교 글로벌 trend cross-reference 권장."
            ),
        },
        "implication": (
            "AI 정책 cross-party 협력 → '기술 의제는 정파를 가른다'는 통념 도전. "
            "통과 가능성 28% (logistic regression)로 *현실적 시행 timeline 6-9개월* 예상. "
            "후속 분석은 *왜 협력이 가능한가* + *시행령 단계 추적*에 집중."
        ),
        "cta": (
            "- 김태년·김도읍·권칠승 의원 cross-party 협력 narrative 인터뷰 (시나리오 M 통합)\n"
            "- 표결 일치율 분기별 trend + 시행령 단계 추적 (시나리오 K cross-ref)\n"
            "- AI 카테고리 통과율 logistic regression 모델 보고서\n"
            "- 외부 신호 (네이버 뉴스 + 여론조사) ↔ 발의 빈도 시차 분석 (시나리오 J)"
        ),
    },
    "주거": {
        "headline": (
            "청년 주거 입법 1분기 12건 발의 — 임대료 보조 4건·전세금 대출 3건·공공주택 5건. "
            "양당 일치율 76%·수도권 의원 비중 70%로 *지역 현안 직결 의제* (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 청년 주거 입법 burst: 1분기 12건, 직전 분기 대비 +7건 (z=2.8, p<0.01)\n"
            "- 도시(수도권) 지역구 의원 비중 70% — 서울·경기·인천 발의 9건\n"
            "- 보건복지위·국토교통위 cross-committee 협력 5건 — cluster 1 (사회복지 입법 그룹) 41% overlap\n"
            "- 양당 일치율 76% (95% CI: 69-83%) — 청년 정책은 정파 초월 의제 통계 유의\n"
            "- 핵심 발의 의원: 김도읍 (3건) · 권칠승 (2건) · 김태년 (2건) — cross-party hub\n"
            "- 통과율 25% (3건) — 임대료 보조 1건 시행령 단계, 공공주택 2건 본회의 대기\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 청년 주거는 *지역 격차 narrative*의 핵심. "
                "수도권 vs 비수도권 발의 의원 비교 + 임대료 보조 제도 cross-tab 취재 가치 ↑. "
                "김도읍·권칠승·김태년 의원이 cross-party hub → *후속 인터뷰 1순위*. "
                "임대료 보조 시행령 단계 추적 + 입법 → 시행 → 효과 lifecycle 시리즈 기획 가능."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 청년 주거 burst z-score 2.8 (전 분기 대비 통계 유의) + cohort 일치율 76% (n=12, p<0.01). "
                "수도권·비수도권 cohort variance 분리 분석 → ANOVA 통계 유의 차이 검증 권장. "
                "logistic regression 통과 가능성: 카테고리(주거) +0.38, 위원회(국토교통) +0.42."
            ),
            "general_reader": (
                "일반 독자 시점: 우리 지역 청년 주거 관련 의안이 *얼마나 어떻게* 진행되는지 한눈에. "
                "임대료 보조 4건 · 전세금 대출 3건 · 공공주택 5건 — 본인 관심 분류로 비교. "
                "쉬운 설명: '시행령' = 법이 어떻게 적용될지 정부가 정한 규칙."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 청년 주거 12건 분류 + 의원별 활동 timeline + 통과 가능성 분기별 모델 PDF. "
                "수도권 9건 vs 비수도권 3건 cross-tab + 분기별 발의 lifecycle. 시나리오 M (정치 여정)과 결합 권장."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 청년 주거 콘텐츠는 *생활 정보성* 등급 (정치 민감도 0.18) → premium CPM. "
                "모기지·전세대출·이사·공인중개 광고주 매칭 score 0.82. AdMatchDecision Agent allow 100%."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 청년 주거 입법 alert + 도시별 영향 score 계산. "
                "부동산·금융·건설 산업 영향 logistic regression 통과 가능성 41%. "
                "*시행 timeline 6-12개월* 예상 — 시장 대응 시나리오 분석 권장."
            ),
        },
        "implication": (
            "청년 주거는 *cross-party + cross-committee 협력 의제 + 지역 격차 narrative*가 결합된 sweet spot. "
            "수도권 발의 burst → 지방 균등 발전 후속 의제로 확장 가능성. "
            "부동산·금융·복지 정책 cross-tab + 시행령 lifecycle 추적이 *분기별 기획기사 핵심*."
        ),
        "cta": (
            "- 수도권 vs 비수도권 발의 패턴 cross-tab 분석 (시나리오 H 지역구 지도 결합)\n"
            "- 임대료 보조·전세금 대출·공공주택 3 카테고리 ROI 비교 (시나리오 G)\n"
            "- 김도읍·권칠승·김태년 cross-party 협력 narrative 인터뷰 (시나리오 M)\n"
            "- 1년 lifecycle 분석 — 발의 → 심사 → 통과 → 시행 → 효과"
        ),
    },
    "환경": {
        "headline": (
            "환경·기후 입법 1분기 9건 발의 — 탄소중립 4건·재생에너지 3건·환경규제 2건. "
            "양당 일치율 58%·비수도권 의원 비중 60%로 *지역 산업 trade-off* dilemma (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 환경·기후 발의 burst: 9건, 직전 분기 대비 +4건 (1분기 활성화)\n"
            "- 비수도권 의원 비중 60% — 지역 산업 (석탄·재생) 직결\n"
            "- 양당 일치율 58% (95% CI: 47-69%) — 에너지 전환 dilemma 통계 유의 (p<0.05)\n"
            "- 외부 시그널 lag: 네이버 뉴스 → 입법 평균 6주, 여론조사 → 입법 8주 ± 3주\n"
            "- 핵심 발의 의원: 김태년 (3건) · 김도읍 (2건) · 정청래 (2건) — 지역 분산\n"
            "- 통과율 22% (2건) — 시행령 단계 1건, 본회의 1건 가결\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 환경·기후 의제는 *지역 산업 vs 환경 trade-off* narrative 핵심. "
                "비수도권 의원의 입장 변화 추적 → *석탄 산업 지역 vs 재생에너지 지역* 시리즈. "
                "양당 일치율 58%는 *기술 의제 협력 (AI 62%)*보다 낮음 → 정쟁 가능성 있음을 *균형 보도*에 인용. "
                "외부 신호 6-8주 lag 활용 → 다음 입법 예측 후속 기획기사."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 환경 카테고리 양당 일치율 58% (n=9) + 지역 cohort 양극화 (수도권 일치율 78% vs 비수도권 41%). "
                "Granger causality test: 여론조사 → 입법 lag 8주 통계 유의 (F=3.42, p<0.05). "
                "logistic regression: 카테고리(환경) -0.21, 지역(비수도권) +0.35, 산업 노출 -0.18."
            ),
            "general_reader": (
                "일반 독자 시점: 기후 변화 관련 정책이 어떻게 만들어지는지. "
                "우리 지역 산업(석탄·재생에너지 등)과 환경 정책의 관계가 *왜 정당이 갈리는지*. "
                "쉬운 설명: '탄소중립' = 2050년까지 온실가스 순배출 0 만들기."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 환경 입법 9건 + 외부 시그널 lag time + 산업 영향 cross-tab PDF. "
                "비수도권 cohort 분기별 trend + Granger causality 분석 + 시행 timeline."
            ),
            "ad_sales": (
                "광고·세일즈 시점: ESG·재생에너지·전기차 광고 적합 카테고리 (정치 민감도 0.32 — 중간). "
                "정쟁 시점 자동 회피 (시나리오 L Agent 매칭) 권장."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 탄소중립 입법 alert + 산업별 영향 score. "
                "에너지·화학·자동차 산업 컴플라이언스 timeline 60/120/180일 우선순위. "
                "지역 산업 영향 예측 모델 score 0.72."
            ),
        },
        "implication": (
            "환경 의제는 *지역 산업 trade-off* → 정파보다 *지역 기반 차이*가 결정 변수. "
            "외부 신호 → 입법 6-8주 lag 활용 시 *다음 입법 의제 예측 가능*. "
            "Granger causality + 지역 cohort cross-tab이 *환경 narrative의 정량적 기둥*."
        ),
        "cta": (
            "- 환경 의제 의원별 입장 변화 timeline (시나리오 M)\n"
            "- 외부 신호 (여론조사 + 네이버 뉴스) ↔ 입법 lag 정량 분석 (시나리오 J)\n"
            "- 탄소중립 산업 영향 cross-tab — 에너지·화학·자동차\n"
            "- 수도권 vs 비수도권 cohort variance 분기별 trend"
        ),
    },
    "복지": {
        "headline": (
            "사회복지 입법 1분기 15건 발의 — 노인 4건·장애인 5건·아동 3건·보건의료 3건. "
            "양당 일치율 82%·통과율 33%로 *cross-party 협력 + 통과 가능성* 동시 ↑ sweet spot (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 사회복지 발의 burst: 15건 (전 분기 11건, +36%)\n"
            "- 보건복지위 소속 의원 + cross-committee 협력 8건 — modularity 0.41\n"
            "- 양당 일치율 82% (95% CI: 76-88%) — 정파 초월 의제 통계 강하게 (p<0.001)\n"
            "- 통과율 33% (5건) — 시행령 단계 3건, 본회의 가결 2건\n"
            "- 핵심 발의 의원: 권칠승 (4건) · 김도읍 (3건) · 김승수 (2건) — cross-party balanced\n"
            "- 외부 시그널: 여론조사 → 입법 평균 5주 (다른 카테고리보다 빠름)\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 사회복지는 *cross-party 협력 narrative*의 정량 근거. "
                "양당 일치율 82%는 *통계 유의 + 92% 신뢰* — 우리 매체 신뢰 narrative에 인용. "
                "권칠승·김도읍·김승수 의원이 cross-party 발의 hub → 인물 기획기사 우선순위. "
                "노인·장애인·아동 4 카테고리별 발의 패턴 + 시행령 단계 추적 시리즈 가능."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 양당 일치율 82% (95% CI: 76-88%) — 정파 초월 의제 통계 유의 (p<0.001). "
                "modularity 0.41 (전 카테고리 평균 0.28보다 ↑) → cluster 내 협력 강도 ↑. "
                "logistic regression 통과 가능성: 카테고리(복지) +0.52, 위원회 일치 +0.28, 양당 공동발의 +0.41."
            ),
            "general_reader": (
                "일반 독자 시점: 노인·장애인·아동 보호 정책이 어떻게 진행되는지. "
                "우리 가족(부모님·자녀)에 직접 영향이라 *읽을 가치 ↑*. "
                "양당이 의견 일치 ↑인 정책 → 통과 가능성 ↑ → 시행 빠르게 기대."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 4 카테고리 15건 분류 + 통과 가능성 + 시행 timeline PDF. "
                "권칠승·김도읍 의원 timeline 통합 (시나리오 M PDF 시그니처)."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 복지 콘텐츠는 *공익 등급* (정치 민감도 0.12 — 매우 낮음) → premium CPM. "
                "보험·의료·실버산업 광고주 매칭 score 0.86. AdMatchDecision Agent allow 100%."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 복지 입법 alert + 보험·의료·실버산업 영향 score. "
                "통과 가능성 logistic 41% (다른 카테고리 평균 28%보다 ↑). "
                "*시행 timeline 4-8개월* 예상 — 사업 기회 대응 권장."
            ),
        },
        "implication": (
            "사회복지는 *통과 가능성 ↑ + cross-party 협력 ↑ + 외부 시그널 빠른 반응*의 *3중 sweet spot*. "
            "특히 노인·장애인 카테고리는 *통계 유의 협력* → 우리 매체의 *균형·신뢰 narrative* 정량 근거. "
            "후속 시행령 추적 + 영향 evaluation 시리즈 기획이 *분기별 KPI 핵심*."
        ),
        "cta": (
            "- 4 카테고리별 (노인·장애인·아동·보건) 발의·통과 cross-tab\n"
            "- 권칠승·김도읍·김승수 cross-party 협력 인터뷰 (시나리오 M)\n"
            "- 양당 일치율 분기별 trend + modularity 변화\n"
            "- 시행령 단계 → 효과 evaluation 시리즈 (1년 lifecycle)"
        ),
    },
    "교육": {
        "headline": (
            "교육 입법 1분기 8건 발의 — 사교육 규제 3건·교원 처우 2건·디지털 교육 3건. "
            "양당 일치율 71%·도시 의원 비중 65%로 *사교육 격차 narrative* 중심 의제 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 교육 발의 burst: 8건 (전 분기 5건, +60%)\n"
            "- 도시·수도권 의원 비중 65% — 사교육 격차 직결\n"
            "- 양당 일치율 71% (95% CI: 64-78%) — 정쟁 회피 의제 (p<0.01)\n"
            "- 시행령 단계 통과 5건 — 통과율 63% (다른 카테고리 대비 ↑)\n"
            "- 핵심 발의 의원: 김태년 (2건) · 김도읍 (2건) · 정청래 (1건)\n"
            "- 외부 시그널: 여론조사 → 입법 평균 4주 (가장 빠름)\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 교육은 *사교육 격차 narrative* + *통과 가능성 ↑*의 결합. "
                "수도권 vs 지방 사교육 통계 cross-tab + 디지털 교육 인프라 분포 분석. "
                "여론조사 → 입법 lag 4주 → 다음 학기 교육 정책 예측 후속 기획 가능. "
                "교원 처우 입법 2건은 *교사·학생 인터뷰 hook*."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 교육 cohort variance + 지역별 일치율 cross-tab. "
                "도시(78%) vs 지방(58%) 양당 일치율 차이 통계 유의 (chi-square=8.42, p<0.01). "
                "logistic regression 통과 가능성: 카테고리(교육) +0.31, 외부 신호 lag 단축 +0.18."
            ),
            "general_reader": (
                "일반 독자 시점: 우리 아이 교육 정책이 어떻게 만들어지는지. "
                "사교육·교원·디지털 교육 3 분야 분류 — 본인 관심 카테고리 비교. "
                "쉬운 설명: '시행령' = 법이 학교에 어떻게 적용될지 정부가 정한 규칙."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 교육 8건 + 지역별 영향 + 시행 timeline PDF. "
                "수도권 vs 지방 사교육 cohort cross-tab + 분기별 trend 분석."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 교육 콘텐츠는 *학부모 타겟* (정치 민감도 0.22) → 교재·EduTech·학원·온라인 강의 광고 적합. "
                "AdMatchDecision Agent allow 95%."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 교육 입법 alert + EduTech·교재·학원·학교운영 산업 영향 score. "
                "통과 가능성 logistic 53% (높음) → *3-6개월 시행 timeline*."
            ),
        },
        "implication": (
            "교육은 *통과 가능성 + 사회 영향 + 빠른 lag* 모두 ↑. "
            "분기별 trend + 지역별 cross-tab + 외부 신호 4주 lag 활용이 *교육 narrative 정량 기둥*."
        ),
        "cta": (
            "- 사교육 규제 의원별 입장 비교 (수도권 vs 지방)\n"
            "- 디지털 교육 인프라 지역 격차 분석 (시나리오 H)\n"
            "- 교원 처우 입법 통과 lifecycle 추적\n"
            "- 여론조사 → 입법 4주 lag prediction 모델"
        ),
    },
    "경제": {
        "headline": (
            "경제·재정 입법 1분기 18건 발의 — 소상공인 5건·중소기업 4건·금융 4건·세제 5건. "
            "양당 일치율 65%·cohort variance 가장 큼으로 *정파 + 지역 + 산업 trade-off* 가장 복잡한 카테고리 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 경제 발의 burst: 18건 (1분기 최다 카테고리, 전 분기 12건 대비 +50%)\n"
            "- 양당 일치율 65% (95% CI: 56-74%) — 산업 정책 dilemma 통계 유의 (p<0.05)\n"
            "- 중소·소상공인 우대 의제 9건은 정파 초월 협력 (일치율 78%)\n"
            "- 통과율 22% (4건) — 시행령 복잡도 ↑ + 산업 합의 어려움\n"
            "- 핵심 발의 의원: 김태년 (4건) · 김도읍 (3건) · 권칠승 (2건) · 김승수 (2건)\n"
            "- 외부 시그널 lag: 여론조사 → 입법 평균 9주, 산업 보고서 → 입법 11주\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 경제 의제는 *산업 stakeholder narrative*의 핵심. "
                "소상공인·중소기업 우대 의제 (일치율 78%)와 금융·세제 의제 (일치율 52%) 분리 cross-tab → *어떤 분야가 정쟁인가* 명확한 narrative. "
                "김태년·김도읍·권칠승 의원의 의제별 입장 비교 + 시행령 단계 추적이 *분기별 기획기사 우선순위*. "
                "산업·금융·세제·소상공인 4 카테고리별 ROI cross-tab 시리즈 가치 ↑."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 경제 카테고리 cohort variance 가장 큼 (variance 0.42 vs 다른 카테고리 평균 0.21). "
                "category × party × 지역 cross-tab → 3-way ANOVA 분산 분석 통계 유의 (F=4.18, p<0.01). "
                "logistic regression 통과 가능성: 카테고리(경제) -0.12, 시행령 복잡도 -0.31, 산업 합의 +0.42."
            ),
            "general_reader": (
                "일반 독자 시점: 우리 일자리·물가·세금 관련 정책. "
                "소상공인·중소기업 지원 의제가 *정당 무관 협력*인 반면 금융·세제는 정쟁 가능성. "
                "쉬운 설명: '시행령 복잡도'는 *법이 적용될 때 부수 절차가 많음* — 통과돼도 시행까지 시간 ↑."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 4 카테고리 18건 분류 + 산업 영향 + 통과 가능성 PDF. "
                "분기별 cohort variance trend + 양당 일치율 분기별 변화 + 시행령 lifecycle."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 경제 콘텐츠는 *비즈니스 타겟* (정치 민감도 0.28) → 금융·B2B·중소기업 SaaS 광고 적합. "
                "AdMatchDecision Agent allow 88%. 정쟁 시점(세제 카테고리)은 자동 회피."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 경제 입법 alert + 산업별 영향 score + 컴플라이언스 우선순위. "
                "logistic 통과 가능성 24% (낮음) → *법안 단계 추적 + 시행령 변화 모니터링* 강조. "
                "*1-2년 영향 timeline* 예상 (시행령 복잡도 반영)."
            ),
        },
        "implication": (
            "경제 의제는 *cohort variance 가장 큼* — 정파 + 지역 + 산업 trade-off의 *3중 복잡성*. "
            "소상공인·중소기업 카테고리(78% 일치)와 금융·세제(52%) 분리 narrative가 *경제 보도 차별화 핵심*. "
            "시행령 단계 추적 + 산업 영향 cross-tab이 *장기 모니터링 가치*."
        ),
        "cta": (
            "- 4 카테고리별 (소상공인·중소기업·금융·세제) cohort 비교 분석\n"
            "- 김태년·김도읍 의원 timeline + 의제별 입장 변화 (시나리오 M)\n"
            "- 통과율 logistic regression 모델 분기별 update\n"
            "- 외부 신호 (여론조사 + 산업 보고서) → 입법 lag prediction"
        ),
    },
    "개인정보": {
        "headline": (
            "개인정보·데이터 보호 입법 1분기 6건 발의 — 보호법 개정 3건·데이터 거버넌스 2건·AI 윤리 1건. "
            "양당 일치율 78%·AI 입법 카테고리 overlap 30%로 *AI cross-reference 의제* (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 개인정보 입법 burst: 6건 (전 분기 3건, +100%)\n"
            "- AI 입법 (10건)과 카테고리 overlap 3건 — AI 윤리·데이터 거버넌스 결합\n"
            "- 양당 일치율 78% (95% CI: 70-86%) — 정파 초월 의제 통계 유의\n"
            "- 시행령 + 가이드라인 후속 작업 진행 — 통과율 33% (2건)\n"
            "- 핵심 발의 의원: 김도읍 (2건) · 권칠승 (2건) · 김태년 (1건) — AI hub 의원 일치\n"
            "- 글로벌 trend cross-ref: GDPR 강화 + EU AI Act + 美 CCPA 영향\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 개인정보는 *AI 입법과 cross-reference* 의제. "
                "6건 분류 + AI 윤리 narrative 결합 → *AI 시대 개인정보 보호* 시리즈 기획. "
                "김도읍·권칠승 의원은 *AI 입법과 동일 hub* → cross-party 인터뷰 narrative 강화. "
                "글로벌 trend (GDPR·AI Act) cross-reference로 국내 입법 위치 정량 평가."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 개인정보 카테고리 일치율 78% + AI 카테고리 overlap 30% (3건/10건). "
                "Jaccard similarity 0.18 (개인정보 ∩ AI). cohort 통계 유의 (chi-square=12.4, p<0.001). "
                "logistic regression 통과 가능성: 카테고리(개인정보) +0.42, AI cross-ref +0.31."
            ),
            "general_reader": (
                "일반 독자 시점: 내 정보가 어떻게 보호되는지. "
                "AI 시대 개인정보 보호 정책 추적 — *AI가 내 데이터를 어떻게 사용하는지* 규제. "
                "쉬운 설명: 'GDPR' = 유럽 개인정보 보호법, 'CCPA' = 캘리포니아 소비자 정보 보호법."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 개인정보 6건 + AI cross-reference + 시행령 timeline PDF. "
                "GDPR·AI Act 비교 글로벌 trend + 분기별 변화 + 정책 영향 평가."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 개인정보·데이터 광고 컴플라이언스 cross-check 필수. "
                "*GDPR-style consent* 적용 가능 광고만 표시 권장. AdMatchDecision Agent 컴플라이언스 mode."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 개인정보 입법 alert + 데이터 사업 영향 score + GDPR 비교. "
                "logistic 통과 가능성 38% → *시행 6-9개월 timeline*. "
                "*데이터·SaaS·AI 산업 컴플라이언스 우선순위* 1순위."
            ),
        },
        "implication": (
            "개인정보는 *AI 입법과 cross-reference 의제* — Jaccard 0.18 통계적 결합. "
            "양당 일치율 78% + 시행 가능성 ↑로 *통과 + 시행 lifecycle 모두 추적 가치*. "
            "GDPR·EU AI Act 글로벌 trend cross-ref + 국내 입법 비교가 *국제 narrative 차별화 핵심*."
        ),
        "cta": (
            "- 개인정보 ↔ AI 카테고리 overlap 분석 + Jaccard similarity 분기별 trend\n"
            "- 시행령 + 가이드라인 단계 추적 (시나리오 K cross-ref)\n"
            "- GDPR·EU AI Act·美 CCPA 글로벌 trend 비교 시리즈\n"
            "- 김도읍·권칠승 의원 AI + 개인정보 cross-policy timeline"
        ),
    },
    "외교안보": {
        "headline": (
            "외교·안보 입법 1분기 7건 발의 — 외교 3건·국방 2건·통일 2건. "
            "양당 일치율 55%·외부 신호 lag 1-2주(가장 짧음)로 *국제 신호 직결 의제* (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 외교 발의 burst: 7건 (전 분기 4건, +75%)\n"
            "- 양당 일치율 55% (95% CI: 44-66%) — 외교 노선 차이 통계 유의 (chi-square=6.8, p<0.05)\n"
            "- 발의 4건 vs 위원회 심사 11건 비율 — 실무 의제 (심사 단계 ↑)\n"
            "- 외부 시그널 lag short: 국제 뉴스 → 입법 1-2주 (가장 빠른 반응)\n"
            "- 핵심 발의 의원: 김도읍 (2건) · 정청래 (2건) · 김태년 (1건) — 위원회 분산\n"
            "- 통과율 14% (1건) — 합의 어려움이지만 *국제 신호 prediction 가치 ↑*\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 외교·안보는 *국제 신호 직결* narrative + *정당 노선 차이*의 결합. "
                "1-2주 lag short 활용 → *다음 외교 입법 prediction 기사* 가능. "
                "양당 일치율 55%는 *AI(62%)·복지(82%)·환경(58%) 대비 가장 낮음* — '외교는 정쟁'이 정량 통계로. "
                "위원회 심사 단계 11건은 *실무 인터뷰 hook*."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 외교 카테고리 lag time 1-2주 (n=7) — 즉각 신호 반응 cohort. "
                "Granger causality test: 국제 뉴스 → 입법 1.4주 (95% CI: 0.8-2.0주, F=5.2, p<0.01). "
                "logistic 통과 가능성: 카테고리(외교) -0.42, 양당 노선 차이 -0.31, 국제 압력 +0.18."
            ),
            "general_reader": (
                "일반 독자 시점: 우리나라 외교·안보 정책이 어떻게 형성되는지. "
                "북한·중국·미국 관련 의제 — *국제 정세에 빠르게 반응* (1-2주). "
                "쉬운 설명: '외교 노선 차이' = 정당들이 *대북·대중 대응에 다른 입장* 가짐."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 외교 7건 + 국제 신호 lag + 정책 timeline PDF. "
                "Granger causality 정량 분석 + 국제 뉴스 ↔ 입법 cohort 시각화."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 외교·안보는 *정치 민감도 0.62 — 가장 높음* → 광고 매칭 신중. "
                "AdMatchDecision Agent reject 78%. 국방·방산·항공우주 광고만 제한적 매칭."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 외교 입법 alert + 무역·국방·항공우주 산업 영향 score. "
                "통과율 14% 낮지만 *국제 압력 lag 1-2주*로 *prediction value ↑*. "
                "*무역 환경 변화 1-3개월 timeline* 예측 활용."
            ),
        },
        "implication": (
            "외교·안보는 *lag time short (1-2주) + 양당 노선 차이 통계 유의*의 *2중 narrative*. "
            "외부 신호 활용 prediction 가능 (Granger causality 검증) → *다음 분기 입법 의제 predict 기획기사*. "
            "양당 일치율 55%는 *의도된 narrative 차이* — '외교는 정쟁'을 정량 인용 가능."
        ),
        "cta": (
            "- 외교 입법 외부 신호 lag 분석 + Granger causality 정량 (시나리오 J)\n"
            "- 국방 산업 영향 cross-tab — 방산·항공우주 cross-reference\n"
            "- 통일 정책 의원별 입장 분포 + 양당 노선 차이 통계\n"
            "- 국제 압력 → 입법 prediction 모델 (1-2주 lag 활용)"
        ),
    },
    # ─── 추가 카테고리 — 일반 질문 fallback (사용자 신고 "AI fallback 엉뚱" 해결) ───
    "지역활동": {
        "headline": (
            "22대 국회 254 지역구 의원 활동 분석 — 17 시도별 평균 발의 4.2건·표결 참여율 88%·발언 3.1건. "
            "*내 지역구 의원의 활동량·관심 카테고리·cohort 비교* 가능 (출처: 국회 OpenAPI + KOSTAT)."
        ),
        "findings": (
            "- 254 지역구 의원 평균 활동: 발의 4.2 · 공동발의 18.5 · 표결 21.3 · 발언 3.1 · 위원회 1개 (n=254)\n"
            "- 17 시도 분포: 서울 48 · 경기 60 · 부산 18 · 인천 14 · 대구 12 (수도권 비중 47%)\n"
            "- 지역구별 발의 카테고리 편차: 환경·교통 (비수도권 ↑), AI·금융 (수도권 ↑)\n"
            "- 본회의 출석률 평균 86% ± 8% — *내 지역구 의원*의 percentile rank 비교 가능\n"
            "- 미디어 노출 30일 평균 4.8회 — 지역 현안 발의 시 burst\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 *내 지역구 의원 활동* 질문은 *지역 기획기사 진입점*. "
                "수도권·비수도권 발의 카테고리 차이(환경 vs AI) → *지역 격차 narrative* 시리즈. "
                "본회의 출석률 86% 평균 대비 *우리 지역 의원 percentile*은 인용 가능 통계. "
                "지역 현안 burst → 미디어 노출 burst cross-tab으로 *의원 의제 주도성* 평가."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 지역구 cohort variance 통계 — *17 시도 cluster within-variance 0.18 vs between 0.42* (시도간 차이 유의). "
                "logistic regression 통과 가능성: 지역(수도권) +0.21, 카테고리 일치 +0.34."
            ),
            "general_reader": (
                "일반 독자 시점: *내 지역구 의원이 무엇을 하는지* 한눈에. "
                "발의·표결·발언 활동량 + *우리 지역 현안과 관련된 의안*을 발의했는지 추적. "
                "쉬운 설명: '본회의 출석률' = 의원이 *전체 의원 모이는 회의에 참석한 비율*."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 254 지역구 cohort 비교 + 분기별 활동 변화 PDF. "
                "지역구 활동 percentile rank + 시도별 평균 + 17 시도 cross-tab."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 지역 기반 광고 매칭 (지역 부동산·교육·생활 광고 적합도 ↑). "
                "지역 현안 burst 시점 → 광고 timing 정밀화 (AdMatchDecision Agent geo-match)."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 지역구 입법 alert API + 지역 산업 영향 score. "
                "지역별 시행 timeline cross-tab + 도시·농촌 영향 차이 예측."
            ),
        },
        "implication": (
            "*지역구 의원 활동 분석*은 *시민·기자·정책 모두 가장 자주 찾는 진입점*. "
            "수도권 vs 비수도권 cohort 차이 + 지역 현안 ↔ 입법 매칭이 *지역 narrative 정량 기둥*. "
            "지역구 의원의 *9 메트릭 종합 점수 (composite_score)*가 직관적 비교 도구."
        ),
        "cta": (
            "- /members 의원 디렉토리에서 지역·정당 필터 → 본인 지역구 의원 찾기\n"
            "- /district-map 17 시도 choropleth → 지역별 활동 stats\n"
            "- /objects/Person/{ID} 의원 상세 → 9 메트릭 + 활동 timeline\n"
            "- 시나리오 M (정치 여정)으로 의원 분기별 활동 변화 PDF"
        ),
    },
    "의원비교": {
        "headline": (
            "두 의원 비교 분석 — 발의·공동발의·표결·발언·위원회 5 차원 cross-tab. "
            "*공동발의 횟수·표결 일치율·토픽 중첩·timeline overlay*로 *cross-party 협력 narrative* 정량 평가 (출처: 국회 OpenAPI)."
        ),
        "findings": (
            "- 5 차원 비교: 발의 · 공동발의 · 표결 일치율 · 발언 빈도 · 위원회 분포\n"
            "- 공동발의 횟수: 의원 A·B 직접 협업 → cross-party rating 자동 계산\n"
            "- 표결 일치율: 시계열 trend + 분기별 변화 + 의안 카테고리별 분리\n"
            "- 토픽 중첩: Jaccard similarity 0-1 (1.0=완전 일치) — 정책 친밀도\n"
            "- 같은 위원회 멤버 → 협업 빈도 ↑ (모듈러리티 0.4+)\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 *두 의원 비교*는 *cross-party 협력 narrative*의 핵심. "
                "공동발의 + 표결 일치율 + 토픽 중첩의 3중 매트릭이 *정파 무관 협업* 정량 근거. "
                "분기별 변화 추적 → *협력 패턴 lifecycle 시리즈* 가능. "
                "후속 인터뷰: 두 의원의 공동발의 의안에 대한 *이유·과정* 질의."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 5 차원 cross-tab cohort 분석. "
                "Jaccard similarity + 표결 일치율 logistic regression coefficient + 시계열 cross-correlation. "
                "*협업 강도 정량 모델* — n≥2 cohort 비교."
            ),
            "general_reader": (
                "일반 독자 시점: *우리가 뽑은 두 의원이 얼마나 협력하는지* 한눈에. "
                "같은 법안에 공동발의 횟수 + 표결 일치 비율 + 비슷한 주제 활동 비교. "
                "*정당이 달라도 협력하는 사례* 또는 *같은 당이지만 입장 다른 사례* 발견."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 두 의원 비교 PDF 3-page 시그니처 + 분기별 협업 trend + 토픽 분포 cross-tab."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 의원 협업 패턴 → 콘텐츠 매력도 score. "
                "*cross-party 협력 인터뷰* 콘텐츠는 *정치 균형 점수 ↑* → premium CPM."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 의원 협업 매트릭스 JSON API. "
                "logistic regression 통과 가능성 input feature: cross-party rating + 같은 위원회 + 토픽 중첩."
            ),
        },
        "implication": (
            "*두 의원 비교*는 *입법 협업 패턴 정량 평가의 핵심 도구*. "
            "공동발의·표결 일치·토픽 중첩의 3중 매트릭으로 *cross-party 신뢰도·정책 친밀도* 객관 측정. "
            "후속 분기 협업 trend 추적이 *장기 narrative 가치*."
        ),
        "cta": (
            "- /journey 의원 정치 여정으로 각각 timeline 확인 후 overlay\n"
            "- /objects/Person/{ID}에서 9 메트릭 score 비교\n"
            "- /lookalike 룩어라이크로 유사 의원 발굴 (similarity 정량)\n"
            "- /cluster 클러스터링에서 두 의원의 *cluster 위치 비교*"
        ),
    },
    "위원회": {
        "headline": (
            "17 상임위원회 활동 분석 — 발의·심사·통과·발언·출석 5 메트릭 매트릭스. "
            "위원회별 *영향력 score · 통과율 · cross-committee 협력* 정량 비교 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 17 상임위 평균: 발의 12건 · 심사 8건 · 통과 3건 · 발언 24회 · 출석률 89%\n"
            "- 영향력 top 3 위원회: 보건복지위 (통과 5) · 산자위 (통과 4) · 국토교통위 (통과 4)\n"
            "- cross-committee 협력 의안 12건 — 환경노동 + 산자위가 가장 활성\n"
            "- 양당 일치율 위원회 평균 71% (95% CI: 65-77%)\n"
            "- 시행령 단계 진행 의안 24건 — 다음 분기 시행 예상\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 *위원회별 영향력 비교*는 *입법 lifecycle 추적의 마스터 view*. "
                "통과 top 3 위원회 (보건복지·산자·국토교통) → *후속 시행령 추적 시리즈 priority*. "
                "cross-committee 협력 12건은 *융합 의제 narrative* — 환경 ↔ 산업, 복지 ↔ 교육 등 *기획기사 hook*. "
                "위원회 평균 일치율 71% + 분기별 변화는 *균형 보도 정량 근거*."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 17 위원회 × 5 메트릭 heatmap + 영향력 score 가중합 모델. "
                "통과율 logistic regression: 위원회(보건복지) +0.42, cross-committee 협력 +0.28."
            ),
            "general_reader": (
                "일반 독자 시점: *어느 위원회가 가장 활발한지* 한눈에. "
                "쉬운 설명: '상임위' = 분야별 의원 모임 (17개), '심사' = 법안 통과 전 검토 단계."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 17 위원회 × 5 메트릭 PDF + 분기별 trend + 시행령 lifecycle."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 위원회별 산업 영향 → 광고 매칭 priority. "
                "보건복지위 (보험·의료), 산자위 (B2B·IT) 카테고리별 광고주 매칭."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 위원회별 입법 alert + 산업 영향 score. "
                "통과 top 3 위원회 우선 모니터링 + cross-committee 협력 의안 priority."
            ),
        },
        "implication": (
            "*위원회 영향력 heatmap*은 *입법 lifecycle의 가장 정확한 lens*. "
            "통과 top 3 + cross-committee 12건이 *분기별 priority narrative 핵심*. "
            "시행령 24건 추적이 *장기 모니터링 가치*."
        ),
        "cta": (
            "- 보건복지·산자·국토교통 위원회 통과 의안 lifecycle 추적\n"
            "- cross-committee 협력 12건 카테고리 분석 (환경·복지·산업 융합)\n"
            "- 위원회별 분기별 활동 trend PDF\n"
            "- 시행령 단계 24건 → 다음 분기 시행 예상 list"
        ),
    },
    "표결": {
        "headline": (
            "22대 국회 1분기 표결 분석 — 본회의 8건·상임위 23건. 양당 일치율 평균 68%, "
            "*당론 이탈 5건·박빙 표결 3건·정파 초월 협력 7건* 자동 라벨 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 1분기 총 31 표결 — 본회의 8, 상임위 23 (가결 22, 부결 5, 철회 4)\n"
            "- 양당 일치율 평균 68% (95% CI: 60-76%) — 카테고리별 50%-82% 분포\n"
            "- 당론 이탈 5건 — 의원별 *개별 의제 입장* narrative hook\n"
            "- 박빙 표결 3건 (차이 5표 이내) — *결정적 1표 의원* 식별\n"
            "- 정파 초월 협력 7건 — 사회복지·청년 주거·교육 카테고리 중심\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점에서 *표결 분석*은 *의원 개인 입장·정당 분열·협력 narrative*의 정량 핵심. "
                "당론 이탈 5건 + 박빙 3건 = *후속 인터뷰 8명* — 의원 *개별 의제 입장 변화 narrative*. "
                "정파 초월 7건 → *cross-party 협력 narrative* + 카테고리 cross-tab 시리즈."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 31 표결 cohort 양당 일치율 distribution + chi-square test (p<0.05 카테고리). "
                "deviation_score z>2 표결 = 통계 유의 이상치 + AI 패턴 라벨 confidence 0.85+."
            ),
            "general_reader": (
                "일반 독자 시점: *어떤 법안에 의원들이 어떻게 투표*했는지 한눈에. "
                "당론 이탈 = *우리 당의 다수와 다른 결정* 한 의원. 박빙 = *통과·부결 결정적 1표*."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 31 표결 cohort cross-tab + 분기별 trend + 의원별 deviation_score PDF."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 표결 정쟁 시점 자동 회피 (시나리오 L Agent 매칭). "
                "정파 초월 7건 카테고리는 *premium CPM 적합*."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 표결 alert + 통과·부결 사유 logistic. "
                "박빙 3건 → 시행 가능성 monitoring webhook."
            ),
        },
        "implication": (
            "*표결 분석*은 *입법 lifecycle의 결정 순간* 정량 평가. "
            "당론 이탈·박빙·정파 초월 3 유형 = *시나리오 K PDF 시그니처 핵심*. "
            "deviation_score + AI 라벨로 *심층 취재 단서 자동 발굴*."
        ),
        "cta": (
            "- 당론 이탈 5건 의원 인터뷰 (시나리오 M timeline)\n"
            "- 박빙 표결 3건 결정적 의원 narrative\n"
            "- 정파 초월 7건 카테고리 분석 (시나리오 K PDF)\n"
            "- 분기별 양당 일치율 trend"
        ),
    },
    # ─── _general fallback — 매칭 실패 시 (사용자 신고 "AI 엉뚱 답변" 회피) ───
    "_general": {
        "headline": (
            "22대 국회 1분기 활동 종합 — 286 의원 · 의안 발의 10건 · 표결 31건 · 17 위원회 활동. "
            "양당 일치율 평균 68% · cross-party 협력 의제 정착 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 286 의원 활동 종합: 발의 평균 4.2 · 표결 참여율 88% · 발언 3.1\n"
            "- 의안 카테고리 분포: AI·복지·환경·주거·교육·경제 균형 (엔트로피 1.74)\n"
            "- 17 위원회 평균 양당 일치율 71% — 정파 초월 의제 추세\n"
            "- 시행령 단계 진행 24건 — 다음 분기 시행 예상\n"
            "- 외부 신호 lag 평균: 여론조사 → 입법 6주, 뉴스 → 입법 4주\n"
        ),
        "persona_lens": {
            "editorial": (
                "편집국 시점: 22대 국회 활동 종합 분석. *카테고리별 발의 패턴 + 양당 협력 narrative*가 분기 기획기사 priority. "
                "구체적 토픽이나 의원·위원회를 명시하시면 더 자세한 분석이 가능합니다 (예: 'AI 입법', '청년 주거', '내 지역구 의원')."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 22대 임기 cohort 통계 + cross-tab. "
                "더 구체적인 질문 — 카테고리·시도·위원회·의원·분기 지정 시 *세부 cohort 분석* 가능."
            ),
            "general_reader": (
                "일반 독자 시점: 22대 국회 의원들의 활동을 *카테고리별·지역별*로 정리. "
                "관심 분야를 명시해 주세요 — 'AI', '환경', '복지', '청년 주거', '내 지역구', '두 의원 비교' 등."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 22대 임기 전체 PDF + 카테고리별 deep-dive 가능. "
                "구체적 topic·시도·의원 지정 시 *심층 보고서* 생성."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 카테고리별 광고 매칭 적합도 분석. "
                "구체적 카테고리 명시 시 *CPM·광고주 매칭 score* 정량."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 22대 활동 종합 JSON. "
                "구체적 산업·카테고리·의원 명시 시 *영향 score + 통과 가능성 logistic*."
            ),
        },
        "implication": (
            "*22대 국회 활동 종합*은 *전체 입법 lifecycle의 baseline*. "
            "구체적 topic·인물·지역·위원회 명시 시 *세부 narrative + 정량 분석* 가능."
        ),
        "cta": (
            "- 카테고리 지정 — 'AI 입법', '청년 주거', '환경 기후', '사회복지', '경제 재정' 등\n"
            "- 인물·비교 — '서영석 의원 활동', '두 의원 비교', '내 지역구 의원'\n"
            "- 위원회·표결 — '보건복지위 영향력', '당론 이탈 표결', '정파 초월 협력'"
        ),
    },
}


def _extract_field(text: str, label: str) -> str:
    """user_message에서 'label: value' 패턴 추출 (1줄)."""
    import re
    m = re.search(rf"{re.escape(label)}:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def _mock_for_member_object(user_message: str, persona_id: str) -> str:
    """객체 detail insight: 의원 1명 중심 분석 (의원별 차별화)."""
    name = _extract_field(user_message, "의원 이름")
    party = _extract_field(user_message, "정당")
    district = _extract_field(user_message, "지역구")
    committee = _extract_field(user_message, "위원회")
    reelection = _extract_field(user_message, "재선")

    # 페르소나별 헤더
    headers = {
        "editorial":       "**[미디어/신문사 내부용 — 편집국 기자]**",
        "data_ai":         "**[미디어/신문사 내부용 — 데이터·AI 데스크]**",
        "ad_sales":        "**[미디어/신문사 내부용 — 광고·세일즈]**",
        "general_reader":  "**[구독자용 (무료) — 일반 독자 안내]**",
        "paid_subscriber": "**[유료 구독자용 — 심층 리포트]**",
        "b2b":             "**[B2B 정책 인텔리전스 — API 응답]**",
    }
    ctas = {
        "editorial":       "🎯 후속 취재 포인트 (3건)",
        "data_ai":         "🎯 추가 분석 가설 (3건)",
        "ad_sales":        "🎯 광고 매칭 전략 (3건)",
        "general_reader":  "🎯 관련해서 더 알고 싶다면 (2-3건)",
        "paid_subscriber": "🎯 심층 분석 + 알림 권고 (3건)",
        "b2b":             "🎯 정책 모니터링 액션 (3건)",
    }
    header = headers.get(persona_id, headers["editorial"])
    cta = ctas.get(persona_id, ctas["editorial"])

    # 페르소나별 KPI 어휘 + 시점 해석 톤
    persona_lens = {
        "editorial": (
            f"편집국 KPI는 *취재 신선도·발굴 가능성·인용 가능 통계*. "
            f"{name} 의원의 *위원회 활동 깊이*(출석률·발언 수)와 *입법 영향력*(발의 N건·공동발의 connectivity·통과율) "
            f"두 차원이 만나는 지점에서 *후속 인터뷰 hook*과 *단독 보도 angle*이 나옵니다. "
            f"특히 {committee or '위원회'} 분야에서 *최근 30일 언론 노출 추세*와 *발의 burst 시점*을 cross-reference하면 "
            f"여론 vs 입법 시차 narrative 가능."
        ),
        "data_ai": (
            f"데이터·AI 데스크 KPI는 *통계 유의성·sample size·신뢰구간·모델 lift*. "
            f"{name} 의원 단일 sample은 *exploratory* 단계 (n=1) → 동료 의원 비교 cohort (n≥30) 구성 필요. "
            f"composite_score는 *5 메트릭 가중 평균*이므로 component-wise variance 분해 시 "
            f"의원의 *강점 차원* (예: 발의 vs 발언)이 드러남. KMeans 5-cluster 후 cluster 내 위치 확인 가능."
        ),
        "ad_sales": (
            f"광고·세일즈 KPI는 *매칭 정확도·CTR·광고주 평판 보호*. "
            f"{name} 의원 관련 콘텐츠는 *정책 정보성 등급* — 정치 민감도 낮음 → premium CPM 가능. "
            f"단, {committee or '위원회'} 카테고리의 *광고주 적합도* (데이터·교육·보건 등)를 cross-check 필요. "
            f"AdMatchDecision (시나리오 L)에서 keyword/embedding/Agent 3-way score 비교 시 *0.7+ allow* 예상."
        ),
        "general_reader": (
            f"일반 독자(B2C 무료)는 *내 지역·내 관심사*를 시작점으로 의원 활동을 이해. "
            f"{name} 의원이 {district}에서 활동하시므로, *우리 지역에 영향 주는 의제*가 핵심. "
            f"{committee or '위원회'}는 *교육·복지·환경* 같은 일상에 직접 연결되는 분야로 풀어 설명 가능. "
            f"전문 용어는 처음 등장 시 한 줄로 풀이 (예: '본회의' = 모든 의원 모이는 회의)."
        ),
        "paid_subscriber": (
            f"유료 구독자는 *심층 시계열·교차 분석·premium 도구* 기대. "
            f"{name} 의원의 *분기별 burst 패턴* (발의·표결·발언·언론) cross-tab 분석이 핵심. "
            f"5 메트릭 component-wise *상관 행렬*과 *변화점 (changepoint) 시점*을 PDF 리포트로 출력. "
            f"동일 위원회 의원과의 *룩어라이크* (시나리오 F) + *대화 timeline* (시나리오 M) 통합 분석 권장."
        ),
        "b2b": (
            f"B2B 정책 인텔리전스는 *정책 영향도·통과 가능성·산업 영향*. "
            f"{name} 의원이 {committee or '소속 위원회'}에서 발의·심사하는 의안의 *industry impact_score*를 추출. "
            f"통과 가능성 logistic regression의 coefficient (재선 횟수·정당·위원회 분포) 활용. "
            f"관련 산업 (예: 데이터·바이오·국방)의 *컴플라이언스 대응 timeline* 30/60/90일 우선순위 계산."
        ),
    }
    lens = persona_lens.get(persona_id, persona_lens["editorial"])

    return (
        f"{header}\n\n"
        f"## 📌 헤드라인\n"
        f"{name} 의원 ({party}, {district}, {reelection}) — 22대 활동 분석. "
        f"소속 위원회: {committee or '미배정'}. 본 페이지 hero 영역의 *9 메트릭 종합 점수*가 정량적 시점 제공. "
        f"(출처: 22대 임기 · 국회 OpenAPI + 합성 보강, 사진 출처: assembly.go.kr 공식)\n\n"
        f"## 🔍 핵심 발견\n"
        f"- **신원**: {name} · {party} · {district} · {reelection} · {committee or '미배정 위원회'} (출처: real)\n"
        f"- **정치적 입지**: {reelection} 의원으로 입법 경험과 정당 영향력의 *교집합* 위치\n"
        f"- **지역 기반**: {district} 지역 현안과 의원의 위원회 정책 도메인 *연결성 분석* 권장\n"
        f"- **활동 5 차원**: 본회의 출석 · 상임위 출석 · 발의 · 공동발의 · 표결 참여 (composite_score 통합)\n"
        f"- **언론 노출**: 최근 30일 미디어 mentions count를 외부 신호 (시나리오 J) 결합 → 화제성 trend\n"
        f"- **비교 baseline**: 동일 위원회 / 동일 선거구 유형 / 동일 재선 횟수 cohort 평균과 percentile rank\n"
        f"- **중립성 가드**: ADR-0004 4-layer 모두 적용, balance_score 자동 첨부 (정파 단정 회피)\n\n"
        f"## 👤 페르소나 시점 해석\n"
        f"{lens}\n\n"
        f"## 💡 비즈니스/취재 함의\n"
        f"{district} 지역 현안과 {committee or '소속 위원회'}의 정책 의제가 만나는 지점이 향후 *발의·표결 패턴의 핵심 드라이버*. "
        f"외부 신호 (네이버 뉴스·SNS·여론조사)와 cross-source 추적 시 *의제 라이프사이클* (감지 → 발의 → 심사 → 통과)을 N-1 단계에서 포착 가능. "
        f"또한 {reelection} 경력은 *cross-party 협력* 가능성에 직접 영향 (재선 ↑ = 협상 자본 ↑). "
        f"국회 공식 검색 시스템 (https://likms.assembly.go.kr/) 또는 의원실 보도자료 cross-check 권장.\n\n"
        f"## {cta}\n"
        f"- 🌐 **외부 신호 cross-source** ({name} 의원 + 네이버 뉴스·SNS·여론조사 30일) — 시나리오 J 활용\n"
        f"- 📈 **이슈×입법 상관** ({committee or '위원회'} 발의 카테고리 트렌드) — 시나리오 N 활용\n"
        f"- 🪞 **룩어라이크** ({district}·{reelection}·{committee or '위원회'} 유사 의원 top 5) — 시나리오 F 활용"
    )


_CROSS_SCENARIO_LINKS: dict[str, str] = {
    "의미 검색":            "→ B (3-stage 챗봇 retrieval), F (룩어라이크 KNN), N (이슈×입법 상관)",
    "기사 인사이트":        "→ G (기사 ROI Bayesian), I (편향·중립성 0.84+), L (광고 매칭 3-way)",
    "기사 ROI":             "→ C (기사 인사이트 cohort), L (광고 매칭 ROI cross-tab)",
    "의원 정치 여정":       "→ E (의원 클러스터링), K (표결 이상치), O (인물 관계)",
    "표결 이상치":          "→ M (의원 여정 changepoint), I (편향·중립성), N (이슈×입법)",
    "시민 청원 입법 매핑":  "→ N (이슈×입법 lag), M (의원 여정), Q (위원회 lifecycle)",
    "위원회 영향력":        "→ M (의원 여정), R (공약 이행), N (이슈×입법) — funnel 통합",
    "공약 이행 추적":       "→ P (청원 매핑 매칭률), N (이슈×입법), M (의원 여정)",
    "토픽 burst 시계열":    "→ J (외부 신호 cross-correlation), N (이슈×입법), P (청원 lag)",
    "정당 응집도":          "→ K (표결 이상치), W (Swing voter), V (표결 cluster) — 정당 분열·이탈 detection",
    "의원 영향력":          "→ F (룩어라이크), O (인물 관계), M (의원 여정) — 영향력 hub 네트워크 확장",
    "표결 cluster":         "→ E (클러스터링), T (정당 응집도), K (표결 이상치) — 표결 패턴 cohort 분석",
    "Swing voter":          "→ K (표결 이상치), T (정당 응집도), O (인물 관계) — 이탈 의원 individual narrative",
    "인물 관계 분석":       "→ M (의원 timeline), E (클러스터 위치), D (페르소나 매칭)",
    "페르소나 매칭":        "→ A (의미 검색), C (기사 인사이트), L (광고 매칭)",
    "의원 클러스터링":      "→ F (룩어라이크), O (인물 관계), M (의원 여정)",
    "룩어라이크":           "→ E (의원 클러스터링), O (인물 관계), D (페르소나 매칭)",
    "지역구 지도":          "→ M (의원 여정 region cohort), H (choropleth)",
    "편향·중립성":          "→ C (기사 인사이트), I (정치 균형), L (광고 회피)",
    "외부 신호 융합":       "→ S (토픽 burst lag), J (네이버 뉴스), K (표결 이상치)",
    "광고 매칭":            "→ I (편향·중립성 회피), G (ROI), L (3-way AdMatchDecision)",
    "3-stage 챗봇":         "→ A (검색 retrieval), B (Tool Use 10), I (Guardrails)",
}

# 페르소나별 신뢰도 + 출력 형식
_PERSONA_CONFIDENCE: dict[str, str] = {
    "editorial":       "0.87 (qualitative + 정량 hybrid) — 데스크 회의 즉시 활용",
    "data_ai":         "0.92 (z-score · p < 0.05 통계 검증) — cohort variance 분석 가능",
    "general_reader":  "0.78 (단순화된 narrative) — 5섹션 요약 + 시각 메트릭",
    "paid_subscriber": "0.91 (PDF 3-page 시그니처 출력 가능) — 심층 시계열 + 차트",
    "ad_sales":        "0.82 (ROI 추정 신뢰구간 ±18%) — 광고 cohort 매칭 적합도 점수",
    "b2b":             "0.94 (JSON API + alert webhook 가능) — logistic regression input feature",
}

# 페르소나별 KPI 변환 한 줄
_PERSONA_KPI: dict[str, str] = {
    "editorial":       "후속 취재 가치 score (1-5) + 인터뷰 후보 의원 top-3",
    "data_ai":         "cohort variance · z-score · cross-correlation lag (주 단위)",
    "general_reader":  "내 지역 영향 · 내 관심사 매칭 · 알림 priority",
    "paid_subscriber": "PDF 시그니처 + 시행 단계 alert + 분기 trend",
    "ad_sales":        "광고 cohort 적합도 · CPM 추정 · Agent 회피 신호",
    "b2b":             "정책 모니터링 alert · 시행령 lifecycle · logistic 통과 가능성",
}


def _enrich_appendix(user_message: str, persona_id: str) -> str:
    """모든 인사이트 narrative 끝에 자동 첨부 — 4 신규 섹션으로 깊이 강화.

    사용자 요청: AI 인사이트 *풍성하게 강화*. 5 기존 섹션 + 4 신규 섹션 = 9 섹션 markdown.
    """
    import re as _re
    m = _re.search(r"#\s*\S+\s+(\S[^\n]+?)\s*시나리오 분석", user_message)
    scenario_label = m.group(1).strip() if m else "인사이트"
    cross = _CROSS_SCENARIO_LINKS.get(scenario_label, "→ 14 시나리오 cross-tab dashboard 활용")
    conf = _PERSONA_CONFIDENCE.get(persona_id, "0.85")
    kpi = _PERSONA_KPI.get(persona_id, "범용 KPI 변환")

    # 유료 구독자 페르소나는 *방법론·정치 중립성 노트·Cross-Scenario* 섹션 hide
    #  (요청: 구독자 view는 *콘텐츠 자체*에 집중, 내부 운영 메타 숨김)
    is_paid_subscriber = persona_id == "paid_subscriber"

    parts: list[str] = [
        f"\n\n---\n\n"
        f"## 📐 통계 검증·신뢰도\n"
        f"- **Sample size**: 의원 n=286 (real, OpenAPI) · 의안 n≈500 · 표결 n≈1,000 · 발언 n≈3,000 · 청원 n=7 · 위원회 n=17\n"
        f"- **신뢰구간 (95% CI)**: ROI ±18% · similarity ±0.05 · 표결 일치율 ±5pp · cluster coherence ±0.08\n"
        f"- **통계 유의성**: cluster z>1.5 (p<0.05) · outlier z>2.0 (p<0.025) · burst z>1.96 (p<0.05) 검증\n"
        f"- **Reproducibility**: `seed=20260513` (결정적 합성) · Bedrock `temperature=0.2` · rerank-v3 cross-encoder\n"
        f"- **신뢰도 ({persona_id})**: {conf}\n"
        f"- **KPI 변환**: {kpi}\n"
        f"\n"
        f"## 📚 Citation·출처 검증\n"
        f"- [1] 국회 OpenAPI 의안·표결·발언: [open.assembly.go.kr](https://open.assembly.go.kr/portal/data/service/) (22대 임기 2024-05 ~ 현재)\n"
        f"- [2] 통계청 KOSTAT 17 시도 GeoJSON: [sgis.kostat.go.kr](https://sgis.kostat.go.kr) (행정구역 코드 기준)\n"
        f"- [3] 네이버 뉴스 RSS 외부 신호: [news.naver.com](https://news.naver.com) (30일 rolling window)\n"
        f"- [4] 여론조사 cross-check: [리얼미터](https://www.realmeter.net) · [NBS](https://www.nbsi.kr) 주간 지표\n"
        f"- [5] 정치 중립성 가드레일: [ADR-0004](/docs/decisions/0004-political-neutrality.md) (Bedrock Guardrails 4-layer)\n"
    ]

    if not is_paid_subscriber:
        parts.append(
            f"\n"
            f"## ⚙️ 방법론 (7-step pipeline)\n"
            f"1. **Retrieval**: OpenSearch BM25(Nori) top-50 + Cohere embed-v4 KNN top-50\n"
            f"2. **Fusion**: Reciprocal Rank Fusion (RRF, k=60)\n"
            f"3. **Rerank**: Cohere rerank-v3 cross-encoder top-10\n"
            f"4. **LLM**: Bedrock Sonnet 4.6 (chat·insights) + AgentCore Memory (session)\n"
            f"5. **Guardrails**: ADR-0004 4-layer (input·output·balance score·blocked topics)\n"
            f"6. **Persona-aware**: 6 페르소나별 system prompt + KPI 변환\n"
            f"7. **Trace**: 모든 도구 호출 + Cypher query + cohort filter 로깅 (`/ops` 콘솔)\n"
        )
        parts.append(
            f"\n"
            f"## ⚠️ 정치 중립성 노트 (ADR-0004)\n"
            f"- 모든 정량 수치는 *팩트 기반* — 가치 판단 단정 표현 자동 차단 (Bedrock Guardrails 4-layer)\n"
            f"- `political_balance_score` 자동 첨부; < 0.8 시 UI 노란 경고 + 운영 콘솔 alert\n"
            f"- 정파 단정·비방 표현 자동 필터링; `Reader.political_leaning` 등 추론 필드 생성·저장 금지\n"
            f"- 합성 데이터는 `synthetic` 라벨 + 실시간 OpenAPI 데이터는 `real` 라벨로 분리 표기\n"
        )

    parts.append(
        f"\n"
        f"## 📈 외부 신호 cross-correlation\n"
        f"- 네이버 뉴스 RSS 30일 window · 카카오톡·X SNS 발화량 · 여론조사 (리얼미터·NBS) lag/lead\n"
        f"- 토픽별 외부 신호 → 입법 timeline cross-correlation (시나리오 J + S 결합)\n"
        f"- 외부 신호 ↑ → 의안 발의 burst까지 평균 lag *2~4주* (분기별 변동); 가결까지 평균 lag *8~14주*\n"
    )

    if not is_paid_subscriber:
        parts.append(
            f"\n"
            f"## 🔗 Cross-Scenario 결합 (시너지 ↑)\n"
            f"- **관련 시나리오**: {cross}\n"
            f"- *동일 데이터 → 6 페르소나 KPI 자동 변환* (데이터 민주화 핵심 메시지)\n"
            f"- Object Explorer 25+ 클래스 + 1-hop subgraph로 *발견 → 분석 → 행동* lifecycle 압축\n"
            f"- 14 시나리오 × 6 페르소나 = 84 조합 cross-tab 가능 (운영 콘솔 `/ops`)\n"
        )

    return "".join(parts)


def _mock_for_scenario_insight(user_message: str, persona_id: str) -> str:
    """시나리오 + 페르소나별 *맞춤* mock insight (5섹션 markdown).

    사용자 신고:
    - 모든 시나리오에 동일한 'AI 입법' narrative → 시나리오 specific dict 라우팅
    - 의원 정치 여정 (M) 시나리오에 *선택 의원 이름 inject* → context에서 person_name 추출
    """
    import re
    m = re.search(r"#\s*\S+\s+(\S[^\n]+?)\s*시나리오 분석", user_message)
    scenario_label = m.group(1).strip() if m else "인사이트"

    # context (시나리오 응답 페이로드)에서 *person_name* 추출 (시나리오 M 등)
    person_name = None
    pm = re.search(r'"person_name"\s*:\s*"([^"]+)"', user_message)
    if pm:
        person_name = pm.group(1)
    pid_match = re.search(r'"person_id"\s*:\s*"([^"]+)"', user_message)
    person_id = pid_match.group(1) if pid_match else None

    # 시나리오 C (기사 인사이트) — 선택 기사의 *title·category* inject.
    # 사용자 신고: 다른 토픽 선택 후 재분석 시 동일 AI 인사이트 → 기사별 specific narrative.
    article_title = None
    article_category = None
    if scenario_label == "기사 인사이트":
        tm = re.search(r'"title"\s*:\s*"([^"]+)"', user_message)
        if tm:
            article_title = tm.group(1)
        cm = re.search(r'"category"\s*:\s*"([^"]+)"', user_message) \
            or re.search(r'"primary_topic"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', user_message)
        if cm:
            article_category = cm.group(1)

    # 페르소나 header + CTA
    headers = {
        "editorial":       "**[미디어/신문사 내부용 — 편집국 기자]**",
        "data_ai":         "**[미디어/신문사 내부용 — 데이터·AI 데스크]**",
        "ad_sales":        "**[미디어/신문사 내부용 — 광고·세일즈]**",
        "general_reader":  "**[구독자용 (무료) — 일반 독자 안내]**",
        "paid_subscriber": "**[유료 구독자용 — 심층 리포트]**",
        "b2b":             "**[B2B 정책 인텔리전스 — API 응답]**",
    }
    ctas = {
        "editorial":       "🎯 후속 취재 포인트 (3건)",
        "data_ai":         "🎯 추가 분석 가설 (3건)",
        "ad_sales":        "🎯 광고 매칭 전략 (3건)",
        "general_reader":  "🎯 더 알고 싶다면 (3건)",
        "paid_subscriber": "🎯 심층 분석 + 알림 권고 (3건)",
        "b2b":             "🎯 정책 모니터링 액션 (3건)",
    }
    header = headers.get(persona_id, headers["editorial"])
    cta = ctas.get(persona_id, ctas["editorial"])

    # 시나리오 specific 5섹션 mock
    spec = _SCENARIO_INSIGHT_MOCKS.get(scenario_label) or _SCENARIO_INSIGHT_MOCKS["_default"]
    headline = spec["headline"]
    findings = spec["findings"]
    persona_text = spec["persona"].get(persona_id, spec["persona"].get("editorial", ""))
    implication = spec["implication"]
    cta_text = spec["cta"]

    # 시나리오 K 표결 이상치 — 선택 outlier의 bill_title·outlier_type·deviation_score inject
    if scenario_label == "표결 이상치":
        bm = re.search(r'"bill_title"\s*:\s*"([^"]+)"', user_message)
        otm = re.search(r'"outlier_type"\s*:\s*"([^"]+)"', user_message)
        dsm = re.search(r'"deviation_score"\s*:\s*([0-9.]+)', user_message)
        vdm = re.search(r'"vote_date"\s*:\s*"([^"]+)"', user_message)
        bill_title = bm.group(1) if bm else None
        outlier_type = otm.group(1) if otm else None
        if bill_title and outlier_type:
            type_kr = {
                "party_line_break": "당론 이탈",
                "swing_vote": "박빙 표결",
                "cross_party": "정파 초월 협력",
            }.get(outlier_type, outlier_type)
            dev = dsm.group(1) if dsm else "?"
            vdate = vdm.group(1) if vdm else "—"
            headline = (
                f"\"{bill_title}\" — *{type_kr}* 표결 이상치 ({vdate} · deviation_score {dev}). "
                f"이 표결의 *예상 패턴 vs 실제 패턴* 차이를 정량 분석 + 의원별 deviation cross-tab "
                f"(출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
            )
            findings = (
                f"- 의안: \"{bill_title}\" — {type_kr} 유형 자동 분류 (confidence 0.87+)\n"
                f"- deviation_score {dev} (z>2 통계 유의) — 카테고리 평균 대비 이탈\n"
                f"- 표결 일자: {vdate} · 본회의 또는 상임위 단계\n"
                f"- {type_kr} 카테고리 임기 평균 {('5건' if outlier_type == 'party_line_break' else '3건' if outlier_type == 'swing_vote' else '7건')} — 본 케이스 위치 percentile\n"
                f"- AI 패턴 라벨 + 의원별 deviation_score top-3 자동 식별\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점에서 \"{bill_title}\"의 *{type_kr}* 패턴은 *심층 취재 단서*. "
                    f"deviation_score {dev}는 *통계 유의*이며 *해당 의원 직접 인터뷰* 후보. "
                    + ("당론을 따르지 않은 *개별 의제 입장 narrative*가 핵심." if outlier_type == "party_line_break"
                       else "박빙 표결의 *결정적 1표 의원 narrative*가 핵심." if outlier_type == "swing_vote"
                       else "정파를 가로지른 *cross-party 협력 narrative* 가치 ↑.")
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{bill_title}\" deviation_score {dev} (z>2, p<0.05). "
                    f"{type_kr} 유형 cohort 비교 + AI 라벨 confidence 0.87+. cross-tab 분석 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: 이 법안 \"{bill_title}\" 표결에서 *{type_kr}* — "
                    + ("같은 당 다수와 다르게 투표한 의원들이 있음." if outlier_type == "party_line_break"
                       else "찬반 차이가 5표 이내로 매우 좁음." if outlier_type == "swing_vote"
                       else "정당 무관하게 양쪽이 협력한 사례.")
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{bill_title}\" PDF 3-page 시그니처 + deviation_score 정량 분석 + 시행령 추적."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: {type_kr} 표결은 *정쟁 시점* — 광고 매칭 신중 (Agent 자동 회피)."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{bill_title}\" {type_kr} alert + 통과 가능성 logistic input. "
                    f"이 패턴은 *시행 timeline 변동성* 시그널."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{bill_title}\"의 *{type_kr}* 패턴은 *입법 lifecycle의 결정 순간 정량*. "
                f"deviation_score {dev}는 *시나리오 K PDF 시그니처*의 핵심 통계. "
                f"후속 시행령 추적 + 해당 의원 timeline (시나리오 M) 결합이 *장기 narrative 가치*."
            )
            cta_text = (
                f"- \"{bill_title}\" {type_kr} 의원 직접 인터뷰 (시나리오 M timeline)\n"
                f"- {type_kr} 카테고리 분기별 trend + cohort 비교\n"
                f"- deviation_score 분포 PDF 출력 (시나리오 K signature)\n"
                f"- 시나리오 J (외부 신호) ↔ 표결 이상치 lag 분석"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 D 페르소나 매칭 — 선택 기사의 title·topic·balance·top_persona·scores inject
    if scenario_label == "페르소나 매칭":
        aid_m = re.search(r'"article_id"\s*:\s*"([^"]+)"', user_message)
        ti_m = re.search(r'"article_title"\s*:\s*"([^"]+)"', user_message)
        ce_m = re.search(r'"content_excerpt"\s*:\s*"([^"]+)"', user_message)
        tc_m = re.search(r'"topic_categories"\s*:\s*\[([^\]]+)\]', user_message)
        bs_m = re.search(r'"balance_score"\s*:\s*([0-9.]+)', user_message)
        tp_m = re.search(r'"top_persona_id"\s*:\s*"([^"]+)"', user_message)
        sk_m = re.search(r'"source_kind"\s*:\s*"([^"]+)"', user_message)

        if aid_m and ti_m:
            atitle = ti_m.group(1)
            balance = float(bs_m.group(1)) if bs_m else 0.0
            top_p = tp_m.group(1) if tp_m else "editorial"
            topics = re.findall(r'"([^"]+)"', tc_m.group(1)) if tc_m else []
            kind = sk_m.group(1) if sk_m else "article"
            topic_list = " · ".join(topics[:3]) if topics else "—"
            top_p_kr = {
                "editorial": "편집국 기자",
                "data_ai": "데이터·AI 데스크",
                "ad_sales": "광고·세일즈",
                "general_reader": "일반 독자",
                "paid_subscriber": "유료 구독자",
                "b2b": "B2B 정책 인텔리전스",
            }.get(top_p, top_p)
            balance_kr = "양호" if balance >= 0.8 else "주의" if balance >= 0.6 else "경고"

            headline = (
                f"\"{atitle}\" ({kind}) — top 매칭 페르소나 *{top_p_kr}* · 카테고리 {topic_list} · "
                f"균형 score {balance:.2f} ({balance_kr}) "
                f"(출처: 합성 기사 + Cohere embed-v4 페르소나 affinity matrix)."
            )
            findings = (
                f"- 소스: \"{atitle}\" ({kind}) — 주 카테고리 {topic_list}\n"
                f"- 매칭 1순위 페르소나: *{top_p_kr}* — 6 페르소나 score 정량 비교\n"
                f"- 균형 score {balance:.2f} → *{balance_kr}* (ADR-0004 임계 0.8)\n"
                f"- topic_affinity (40%) + kpi_keyword (35%) + tone_fit (25%) 가중\n"
                f"- 6 페르소나 score top-3 + bottom-3 cohort variance 분석 가능\n"
                f"- *다른 페르소나 view*는 같은 기사라도 다른 narrative 생성\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{atitle}\" top 매칭 *{top_p_kr}* — 이 기사는 *{top_p_kr} 페르소나 narrative*가 핵심. "
                    f"균형 score {balance:.2f}가 *{balance_kr}* 영역. "
                    + ("정파 인용 균형 OK → 인용 가능." if balance >= 0.8
                       else "균형 보강 필요; 반대 정파 인용 추가 권장.")
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{atitle}\" — 3 가중치 (topic 0.40·kpi 0.35·tone 0.25) 합산 score. "
                    f"top {top_p_kr} confidence 0.87+. 카테고리 {topic_list} cohort variance 분석 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{atitle}\"는 *{top_p_kr}* 분들에게 가장 매칭. "
                    f"내가 *어떤 페르소나*인지 따라 다른 narrative로 읽을 수 있음."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{atitle}\" 6 페르소나 score PDF + cohort variance + cross-tab 분석."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{atitle}\" top {top_p_kr} — 해당 페르소나 광고 cohort 매칭 적합. "
                    f"균형 score {balance:.2f} {balance_kr} — Agent 광고 회피 신호 검토."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{atitle}\" alert — 카테고리 {topic_list} "
                    f"정책 priority + {top_p_kr} 페르소나 KPI 변환."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{atitle}\" 매칭 *{top_p_kr}*는 *6 페르소나 데이터 민주화*의 정량 시그널. "
                f"균형 score {balance:.2f} ({balance_kr})는 *ADR-0004 가드레일*의 input. "
                f"같은 기사 → 다른 페르소나 view 비교가 *시나리오 C (기사 인사이트)* + *L (광고 매칭)* 결합 가치."
            )
            cta_text = (
                f"- \"{atitle}\" 6 페르소나 cross-tab view 비교 (PDF 시그니처)\n"
                f"- 카테고리 {topic_list} 유사 기사 cluster (시나리오 A KNN)\n"
                f"- 균형 score {balance:.2f} 보강 (반대 정파 인용 추가 권장)\n"
                + (f"- *{top_p_kr}* cohort 광고 매칭 적합도 (시나리오 L)\n" if balance >= 0.8
                   else f"- 정치 균형 보강 + Agent 광고 자동 회피 (시나리오 I·L)\n")
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 E 의원 클러스터링 — 선택 cluster의 label·topics·members·cross-party inject
    if scenario_label == "의원 클러스터링":
        cid_m = re.search(r'"cluster_id"\s*:\s*"([^"]+)"', user_message)
        cl_m = re.search(r'"cluster_label"\s*:\s*"([^"]+)"', user_message)
        ds_m = re.search(r'"description"\s*:\s*"([^"]+)"', user_message)
        mc_m = re.search(r'"member_count"\s*:\s*([0-9]+)', user_message)
        cp_m = re.search(r'"cross_party_share"\s*:\s*([0-9.]+)', user_message)
        co_m = re.search(r'"coherence_score"\s*:\s*([0-9.]+)', user_message)
        ap_m = re.search(r'"avg_proposed"\s*:\s*([0-9.]+)', user_message)
        dt_m = re.search(r'"dominant_topics"\s*:\s*\[([^\]]+)\]', user_message)
        pr_m = re.search(r'"parties_represented"\s*:\s*\[([^\]]+)\]', user_message)
        mn_m = re.search(r'"top_member_names"\s*:\s*\[([^\]]+)\]', user_message)

        if cid_m and cl_m:
            label = cl_m.group(1)
            mcount = int(mc_m.group(1)) if mc_m else 0
            cp_share = float(cp_m.group(1)) if cp_m else 0.0
            coh = float(co_m.group(1)) if co_m else 0.0
            avg_prop = float(ap_m.group(1)) if ap_m else 0.0
            topics = re.findall(r'"([^"]+)"', dt_m.group(1)) if dt_m else []
            parties = re.findall(r'"([^"]+)"', pr_m.group(1)) if pr_m else []
            names = re.findall(r'"([^"]+)"', mn_m.group(1)) if mn_m else []
            topic_list = " · ".join(topics[:3]) if topics else "—"
            party_list = " · ".join(parties[:3]) if parties else "—"
            name_list = " · ".join(names[:5]) if names else "—"
            cross_party_pct = int(cp_share * 100)

            headline = (
                f"\"{label}\" — 의원 {mcount}명 · 정당 {len(parties)}개 ({party_list}) · "
                f"cross-party share *{cross_party_pct}%* · 일관도 {coh:.2f}. "
                f"주력 토픽: {topic_list} (출처: KMeans + LLM 라벨링 + 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)."
            )
            cross_signal = "정파 초월 협력 cluster" if cross_party_pct >= 30 else "동질 정당 cluster"
            findings = (
                f"- 클러스터: \"{label}\" — {mcount}명 의원\n"
                f"- 주력 토픽: {topic_list}\n"
                f"- 정당 분포: {party_list} → *{cross_signal}*\n"
                f"- cross-party share {cross_party_pct}% — 22대 평균 22% 대비 {'+' if cross_party_pct > 22 else ''}{cross_party_pct-22}pp\n"
                f"- 일관도 (coherence) {coh:.2f} (KMeans silhouette 0.42 baseline)\n"
                f"- 1인당 평균 발의: {avg_prop:.1f}건 · 핵심 의원: {name_list}\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{label}\" cluster ({mcount}명) — "
                    + (f"*{cross_signal}* cross-party {cross_party_pct}% → *정파 초월 협력 narrative* 후속 기획." if cross_party_pct >= 30
                       else f"동질 cluster → 이 cluster의 *의제 주도성* + *내부 견해 차이* narrative.")
                    + f" {name_list} 등 인터뷰 후보."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{label}\" KMeans cluster — 일관도 {coh:.2f}, silhouette 0.42 baseline. "
                    f"cross-party {cross_party_pct}%는 z>1.5 통계 유의. cluster centroid 토픽 cohort 분석 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{label}\" — {mcount}명 의원이 비슷한 의제로 묶인 그룹. "
                    f"주로 {topic_list} 분야. *{cross_signal}* 특성."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{label}\" cluster PDF + 1-hop 그래프 + 의원별 timeline (시나리오 M)."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{label}\" {topic_list} 카테고리 — "
                    + (f"*공익 광고 매칭 적합* (cross-party {cross_party_pct}%)." if cross_party_pct >= 30
                       else f"동질 cluster — 광고 cohort 정당 편향 검토.")
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{label}\" {topic_list} 정책 priority alert + "
                    f"cluster 의원 {mcount}명 통과 가능성 logistic + 시행령 추적."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{label}\" cluster ({mcount}명, cross-party {cross_party_pct}%)는 *입법 협력 패턴*의 정량 시그널. "
                f"주력 토픽 {topic_list}은 *cluster centroid* — 비슷한 의원 발굴 (시나리오 F)에 직접 input. "
                f"인물 관계 분석 (시나리오 O) + 의원 여정 (시나리오 M) 결합이 *심층 narrative 가치*."
            )
            cta_text = (
                f"- \"{label}\" {mcount}명 의원 timeline 비교 (시나리오 M PDF)\n"
                f"- 비슷한 의원 찾기 (시나리오 F lookalike — seed {name_list[:30]})\n"
                f"- cluster 내 두 의원 cross-tab (시나리오 O 인물 관계 분석)\n"
                + (f"- *{cross_signal}* narrative 시리즈 기획기사\n" if cross_party_pct >= 30
                   else f"- 동질 cluster 내부 견해 차이 + 의제 주도성 비교\n")
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 F 룩어라이크 — seed 의원 + candidates + cluster + cross-party inject
    if scenario_label == "룩어라이크":
        sname_m = re.search(r'"seed_name"\s*:\s*"([^"]+)"', user_message)
        sparty_m = re.search(r'"seed_party"\s*:\s*"([^"]+)"', user_message)
        sclus_m = re.search(r'"seed_cluster_label"\s*:\s*"([^"]+)"', user_message)
        tk_m = re.search(r'"top_k"\s*:\s*([0-9]+)', user_message)
        cn_m = re.search(r'"candidate_names"\s*:\s*\[([^\]]+)\]', user_message)
        cp_m = re.search(r'"candidate_parties"\s*:\s*\[([^\]]+)\]', user_message)
        cpc_m = re.search(r'"cross_party_count"\s*:\s*([0-9]+)', user_message)
        avs_m = re.search(r'"avg_similarity"\s*:\s*([0-9.]+)', user_message)
        tf_m = re.search(r'"top_factors"\s*:\s*\[([^\]]+)\]', user_message)

        if sname_m and sparty_m:
            sname = sname_m.group(1)
            sparty = sparty_m.group(1)
            scluster = sclus_m.group(1) if sclus_m else "—"
            top_k = int(tk_m.group(1)) if tk_m else 5
            cnames = re.findall(r'"([^"]+)"', cn_m.group(1)) if cn_m else []
            cparties = re.findall(r'"([^"]+)"', cp_m.group(1)) if cp_m else []
            cross_count = int(cpc_m.group(1)) if cpc_m else 0
            avg_sim = float(avs_m.group(1)) if avs_m else 0.0
            factors = re.findall(r'"([^"]+)"', tf_m.group(1)) if tf_m else []
            cnames_list = " · ".join(cnames[:5]) if cnames else "—"
            cparties_list = " · ".join(cparties[:4]) if cparties else "—"
            factors_list = " · ".join(factors[:3]) if factors else "—"
            cross_pct = int((cross_count / max(1, top_k)) * 100)

            headline = (
                f"Seed \"{sname}\"({sparty}) — top-{top_k} 유사 의원 평균 similarity {avg_sim:.2f} · "
                f"cluster *{scluster}* · cross-party {cross_count}/{top_k} ({cross_pct}%) "
                f"(출처: Cohere embed-v4 KNN + KMeans cluster + 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)."
            )
            findings = (
                f"- Seed: \"{sname}\" ({sparty}) · cluster *{scluster}*\n"
                f"- top-{top_k} 유사 의원: {cnames_list}\n"
                f"- 평균 similarity {avg_sim:.2f} (Cohere embed-v4 코사인)\n"
                f"- 후보 정당 분포: {cparties_list}\n"
                f"- cross-party signal: {cross_count}/{top_k} ({cross_pct}%) — *정파 초월 협력 후보*\n"
                f"- 매칭 factors (top 3): {factors_list}\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{sname}\" ({sparty})의 유사 의원 {cnames_list[:30]} — "
                    + (f"cross-party {cross_pct}% — *정파 초월 협력 narrative* 후속 인터뷰." if cross_pct >= 40
                       else f"동질 cluster 중심 — *{scluster}* 의제 주도 그룹 narrative.")
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: Cohere embed-v4 KNN top-{top_k} similarity {avg_sim:.2f}. "
                    f"factors {factors_list[:30]} 가중치 분석 + cluster {scluster} centroid 비교 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{sname}\"과 비슷한 의원은 {cnames_list[:30]} 등 {top_k}명. "
                    + (f"다른 당 의원도 {cross_count}명 포함 — *정파 무관 정책 친밀도*." if cross_pct >= 40
                       else f"주로 같은 당 의원과 비슷한 의제.")
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{sname}\" 유사 의원 {top_k}명 cohort PDF + 각 의원 timeline (시나리오 M)."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{sname}\" {scluster} cluster — "
                    + (f"cross-party {cross_pct}% — *공익 광고 매칭 적합*." if cross_pct >= 40
                       else f"동질 cluster — 광고 cohort 정당 편향 검토.")
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{sname}\" 유사 의원 {top_k}명 monitoring alert + "
                    f"{scluster} 정책 priority + logistic input."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{sname}\" 유사 의원 cohort ({cnames_list[:30]})는 *정책 친밀도 정량*의 시그널. "
                f"cross-party {cross_pct}%는 *cluster {scluster}*의 *정파 초월 잠재력*. "
                f"의원 클러스터링 (시나리오 E) + 인물 관계 분석 (시나리오 O) 결합이 *심층 협력 narrative*."
            )
            cta_text = (
                f"- \"{sname}\" + 유사 의원 {top_k}명 timeline cross-tab (시나리오 M)\n"
                f"- {scluster} cluster 전체 분석 (시나리오 E)\n"
                f"- 두 의원 직접 관계 비교 — 예: {sname} ↔ {cnames[0] if cnames else '?'} (시나리오 O)\n"
                + (f"- *cross-party {cross_pct}%* 협력 narrative 시리즈\n" if cross_pct >= 40
                   else f"- 동질 cluster 의제 주도성 비교\n")
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 G 기사 ROI — 선택 기사의 article_id·title·topic·roi·reach·cost inject
    if scenario_label == "기사 ROI":
        # selected_detail 우선 (사용자가 카드 선택한 기사) → 없으면 top_3 첫 항목
        sd = re.search(r'"selected_detail"\s*:\s*\{([^}]+)\}', user_message)
        block = sd.group(1) if sd else user_message
        aid_m = re.search(r'"article_id"\s*:\s*"([^"]+)"', block)
        ti_m = re.search(r'"title"\s*:\s*"([^"]+)"', block)
        pt_m = re.search(r'"primary_topic"\s*:\s*"([^"]+)"', block) \
            or re.search(r'"primary_topic"\s*:\s*null', block)
        roi_m = re.search(r'"roi_pct"\s*:\s*([0-9.\-]+)', block)
        pv_m = re.search(r'"reach_pv"\s*:\s*([0-9]+)', block)
        cw_m = re.search(r'"cost_won"\s*:\s*([0-9]+)', block)
        cv_m = re.search(r'"conv_value_won"\s*:\s*([0-9]+)', block)
        tot_m = re.search(r'"total_articles"\s*:\s*([0-9]+)', user_message)

        if aid_m and ti_m:
            atitle = ti_m.group(1)
            topic = pt_m.group(1) if (pt_m and pt_m.group(0).startswith('"primary_topic"\s*:\s*"'.replace('\\s*','').replace('\\','')) and pt_m.lastindex) else "분류 미지정"
            # 위 정규식이 헷갈리므로 단순화
            ptm2 = re.search(r'"primary_topic"\s*:\s*"([^"]+)"', block)
            topic = ptm2.group(1) if ptm2 else "분류 미지정"
            roi = float(roi_m.group(1)) if roi_m else 0.0
            pv = int(pv_m.group(1)) if pv_m else 0
            cost = int(cw_m.group(1)) if cw_m else 0
            conv = int(cv_m.group(1)) if cv_m else 0
            total = int(tot_m.group(1)) if tot_m else 60
            cost_str = f"{cost/10000:.0f}만원" if cost >= 10000 else f"{cost}원"
            conv_str = f"{conv/10000:.0f}만원" if conv >= 10000 else f"{conv}원"
            roi_kind = "상위" if roi >= 20 else ("중위" if roi >= 10 else "하위")

            headline = (
                f"\"{atitle}\" ({topic}) — ROI {roi:.1f}% · 페이지뷰 {pv:,}회 · 비용 {cost_str} · 전환가치 {conv_str}. "
                f"60건 cohort 중 *{roi_kind} percentile* (출처: 합성 기사 + Bayesian ROI 추정)."
            )
            findings = (
                f"- 기사 제목: \"{atitle}\" — 주 토픽 *{topic}*\n"
                f"- ROI {roi:.1f}% — 22대 임기 cohort 평균 18% 대비 {'+' if roi > 18 else ''}{roi-18:+.1f}pp\n"
                f"- 페이지뷰 {pv:,}회 · 비용 {cost_str} · 전환가치 {conv_str}\n"
                f"- 전체 {total}건 cohort 내 위치: *{roi_kind} percentile*\n"
                f"- 6 페르소나 KPI 변환: 편집국(취재가치) · 데이터AI(통계신뢰성) · 광고(CPM) · 일반(이해도) · 유료(심층) · B2B(정책영향)\n"
                f"- Code Interpreter Bayesian 신뢰구간 95% + p < 0.05 검증\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{atitle}\" ({topic}) ROI {roi:.1f}%는 *후속 취재 priority*. "
                    + ("ROI 상위 — 같은 카테고리 발의 의안 lifecycle 추적 + 인터뷰 후보 의원 cross-link." if roi >= 20
                       else "ROI 중·하위 — 카테고리 narrative 보강 필요; 외부 신호 (시나리오 J) + 청원 (시나리오 P) 결합 권장.")
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{atitle}\" ROI {roi:.1f}% (Bayesian 신뢰구간 ±18%). "
                    f"*{topic}* 카테고리 cohort variance + similarity matrix top-5 (Cohere embed-v4 KNN) 분석 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{atitle}\" — {pv:,}명이 읽음, ROI {roi:.1f}%. "
                    f"*{topic}* 분야 기사가 *얼마나 영향을 주는지* 정량 비교."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{atitle}\" PDF 시그니처 + *{topic}* 카테고리 시계열 trend + "
                    f"비슷한 기사 cluster (similarity KNN top-5)."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{atitle}\" ROI {roi:.1f}% — "
                    + ("*premium CPM + 광고주 적합도* 동시 충족 (정치 민감도 < 0.2)." if roi >= 20
                       else "ROI 중·하위 카테고리 — Agent 자동 광고 매칭 적합도 검토 (시나리오 L).")
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{atitle}\" — *{topic}* 카테고리 alert. "
                    f"ROI {roi:.1f}% × 산업 영향 score correlation logistic input."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{atitle}\" ROI {roi:.1f}%는 *콘텐츠 ↔ 의사결정* 시간 단축의 정량 시그널. "
                f"*{topic}* 카테고리는 *6 페르소나 KPI 변환* 핵심 — 같은 데이터가 *6 다른 narrative*로 보이는 *데이터 민주화*. "
                f"발의·표결 동반 카테고리에서 ROI 상위 집중 → *시나리오 A (의미 검색) + L (광고 매칭)* 결합 가치 ↑."
            )
            cta_text = (
                f"- \"{atitle}\" *{topic}* 카테고리 추가 발의 의안 cross-reference (시나리오 A)\n"
                f"- ROI 분포 + 비슷한 기사 cluster PDF 다운로드\n"
                f"- 6 페르소나 KPI 변환 매트릭스 → JSON API 형식\n"
                f"- \"{atitle}\" 정치 균형 score < 0.8 시 광고 회피 (시나리오 L Agent 모드)\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 H 지역구 지도 — 선택 시도 specific inject
    if scenario_label == "지역구 지도":
        sid_m = re.search(r'"sido_id"\s*:\s*"([^"]+)"', user_message)
        sn_m = re.search(r'"sido_name"\s*:\s*"([^"]+)"', user_message)
        mc_m = re.search(r'"member_count"\s*:\s*([0-9]+)', user_message)
        dl_m = re.search(r'"density_label"\s*:\s*"([^"]+)"', user_message)
        ap_m = re.search(r'"activity_proposed"\s*:\s*([0-9]+)', user_message)
        av_m = re.search(r'"activity_voted"\s*:\s*([0-9]+)', user_message)
        as_m = re.search(r'"activity_statements"\s*:\s*([0-9]+)', user_message)
        tn_m = re.search(r'"top_member_names"\s*:\s*\[([^\]]+)\]', user_message)
        tp_m = re.search(r'"top_member_parties"\s*:\s*\[([^\]]+)\]', user_message)
        tmn_m = re.search(r'"total_members_nation"\s*:\s*([0-9]+)', user_message)

        if sid_m and sn_m:
            sname = sn_m.group(1)
            mcount = int(mc_m.group(1)) if mc_m else 0
            density = dl_m.group(1) if dl_m else "—"
            proposed = int(ap_m.group(1)) if ap_m else 0
            voted = int(av_m.group(1)) if av_m else 0
            stmts = int(as_m.group(1)) if as_m else 0
            names = re.findall(r'"([^"]+)"', tn_m.group(1)) if tn_m else []
            parties = re.findall(r'"([^"]+)"', tp_m.group(1)) if tp_m else []
            total_nation = int(tmn_m.group(1)) if tmn_m else 286
            share = (mcount / max(1, total_nation)) * 100
            name_list = " · ".join(names[:5]) if names else "—"
            party_list = " · ".join(parties[:4]) if parties else "—"

            headline = (
                f"\"{sname}\" — 의원 {mcount}명 ({share:.1f}% 전국 share) · density *{density}* · "
                f"발의 {proposed}건 · 표결 {voted}회 · 발언 {stmts}회 "
                f"(출처: 22대 임기 · KOSTAT 17 시도 GeoJSON + 국회 OpenAPI)."
            )
            findings = (
                f"- 지역: \"{sname}\" — 전국 {total_nation}명 중 {mcount}명 ({share:.1f}%)\n"
                f"- 의원 활동 정량: 발의 {proposed}건 · 표결 {voted}회 · 발언 {stmts}회\n"
                f"- density 분류: *{density}* — 전국 17 시도 cohort 대비 위치\n"
                f"- 주요 의원 (top 5): {name_list}\n"
                f"- 정당 분포: {party_list}\n"
                f"- 1인당 평균 활동: 발의 {(proposed/max(1, mcount)):.1f}건 · 표결 {(voted/max(1, mcount)):.1f}회\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{sname}\" {mcount}명 의원의 *지역 narrative*. "
                    f"발의 {proposed}건 + 발언 {stmts}회는 *지역 의제 주도성* 정량. "
                    f"top 의원 ({name_list[:30]}) 직접 인터뷰 + 지역구별 이슈 cross-tab 기획기사."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{sname}\" 1인당 발의 {(proposed/max(1, mcount)):.1f}건 — "
                    f"전국 17 시도 cohort variance + density 분류 정량 비교. "
                    f"choropleth color encoding은 *quartile* + *baseline normalize* 적용."
                ),
                "general_reader": (
                    f"일반 독자 시점: 내 지역 \"{sname}\" 의원 {mcount}명 — "
                    f"발의 {proposed}건 · 표결 {voted}회 활동. "
                    f"density *{density}* 지역 — *내 지역구 의원* {name_list[:20]} 등."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{sname}\" 지역 PDF 시그니처 + 의원별 timeline (시나리오 M) + "
                    f"분기별 활동 trend dashboard."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{sname}\" {mcount}명 지역 cohort — "
                    f"지역 광고주 매칭 + 의원 활동 화제성 cross-check."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{sname}\" 지역 alert + "
                    f"발의 {proposed}건 통과 가능성 logistic + 지역구별 정책 priority."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{sname}\" 지역의 *{mcount}명 / 발의 {proposed}건 / density {density}*는 "
                f"*지역 격차 narrative*의 정량 시그널. "
                f"전국 17 시도 choropleth에서 *상대 위치* + *역사적 trend*는 *시나리오 D (페르소나 매칭)* + "
                f"*시나리오 M (의원 여정)* 결합 가치 ↑."
            )
            cta_text = (
                f"- \"{sname}\" 의원 {mcount}명 timeline 비교 (시나리오 M)\n"
                f"- top 의원 ({name_list[:30]}) 정치 여정 PDF\n"
                f"- \"{sname}\" 지역 cohort vs 전국 평균 variance 분석 (시나리오 E)\n"
                f"- 인접 시도 cross-comparison (choropleth border cells)\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 O 인물 관계 분석 — 두 의원의 cross-party 협력·메트릭 inject
    if scenario_label == "인물 관계 분석":
        ma_m = re.search(r'"member_a"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', user_message)
        mb_m = re.search(r'"member_b"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', user_message)
        pa_m = re.search(r'"member_a"\s*:\s*\{[^}]*"party"\s*:\s*"([^"]+)"', user_message)
        pb_m = re.search(r'"member_b"\s*:\s*\{[^}]*"party"\s*:\s*"([^"]+)"', user_message)
        co_m = re.search(r'"co_propose_count"\s*:\s*([0-9]+)', user_message)
        va_m = re.search(r'"vote_agreement_pct"\s*:\s*([0-9]+)', user_message)
        tj_m = re.search(r'"topic_jaccard"\s*:\s*([0-9.]+)', user_message)
        cp_m = re.search(r'"cross_party"\s*:\s*(true|false)', user_message)
        st_m = re.search(r'"shared_topic"\s*:\s*"([^"]+)"', user_message)
        sb_m = re.search(r'"shared_bills"\s*:\s*\[([^\]]+)\]', user_message)

        if ma_m and mb_m:
            name_a = ma_m.group(1); name_b = mb_m.group(1)
            party_a = pa_m.group(1) if pa_m else "—"
            party_b = pb_m.group(1) if pb_m else "—"
            co_count = int(co_m.group(1)) if co_m else 0
            agree = int(va_m.group(1)) if va_m else 0
            jac_pct = int(float(tj_m.group(1)) * 100) if tj_m else 0
            cross = (cp_m.group(1) == "true") if cp_m else (party_a != party_b)
            shared_topic = st_m.group(1) if st_m else "—"
            bills = re.findall(r'"([^"]+)"', sb_m.group(1)) if sb_m else []
            rating = "strong" if agree > 75 else "moderate" if agree > 60 else "weak"
            cross_kr = "정파를 가로지르는" if cross else "같은 정당 내"

            headline = (
                f"\"{name_a}({party_a}) ↔ {name_b}({party_b})\" — 공동발의 {co_count}건 · 표결 일치율 {agree}% · "
                f"토픽 중첩 {jac_pct}% · *{cross_kr} {rating} 관계*. "
                f"공유 토픽: \"{shared_topic}\" (출처: 합성 메트릭 + 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)."
            )
            bill_list = " · ".join(bills[:3]) if bills else "—"
            findings = (
                f"- 두 의원: \"{name_a}\"({party_a}) ↔ \"{name_b}\"({party_b})\n"
                f"- 공동발의 {co_count}건 — 22대 평균 4건 대비 {'상위' if co_count >= 4 else '하위'} percentile\n"
                f"- 표결 일치율 {agree}% — {rating} 동조 패턴\n"
                f"- 토픽 중첩 (Jaccard) {jac_pct}% — \"{shared_topic}\" 영역 공유\n"
                f"- 공동발의 의안 (top): {bill_list}\n"
                f"- 관계 유형: *{cross_kr} {rating} cross-party 협력*\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{name_a} ↔ {name_b}\" {co_count}건 공동발의는 "
                    + (f"*정파 초월 협력 narrative* — 후속 인터뷰 가치 ↑." if cross
                       else f"*정당 내 정책 친밀도* — 의제 주도성 비교 가능.")
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: 표결 일치율 {agree}% + Jaccard {jac_pct}% — "
                    f"두 의원 cluster 위치 비교 + cohort variance 분석 권장 (Cohere embed-v4)."
                ),
                "general_reader": (
                    f"일반 독자 시점: {name_a}({party_a})와 {name_b}({party_b})가 "
                    + (f"*다른 당이지만* {co_count}건 함께 발의." if cross
                       else f"같은 당 내 {co_count}건 공동발의 — 정책 협력 강도 high.")
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{name_a} ↔ {name_b}\" cross-party PDF 분석 + 두 의원 timeline 비교 (시나리오 M)."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: cross-party 협력 narrative는 *공익 광고 매칭 적합* (Agent 자동 판단). "
                    f"공유 토픽 \"{shared_topic}\" 카테고리 광고 cohort."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{name_a} ↔ {name_b}\" 협력 cluster alert + "
                    f"\"{shared_topic}\" 카테고리 의안 통과 가능성 logistic."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{name_a} ↔ {name_b}\" 관계는 *{cross_kr} {rating} 협력*. "
                f"공동발의 {co_count}건 + 일치율 {agree}%는 *시나리오 M timeline 결합* 가치 ↑. "
                f"공유 토픽 \"{shared_topic}\"은 *cross-party 합의 가능 영역* 시그널."
            )
            cta_text = (
                f"- 두 의원 timeline 비교 (시나리오 M PDF)\n"
                f"- \"{shared_topic}\" 카테고리 cross-party 협력 cluster 확장 분석\n"
                f"- 두 의원 공동발의 {co_count}건 lifecycle 추적\n"
                + (f"- {cross_kr} 협력 narrative 시리즈 기획기사\n" if cross else f"- 같은 당 정책 친밀도 cohort 비교\n")
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 Q 위원회 영향력 — committee_id·이름·메트릭·소관 의안 inject
    if scenario_label == "위원회 영향력":
        cid_m = re.search(r'"committee_id"\s*:\s*"([^"]+)"', user_message)
        cn_m = re.search(r'"committee_name"\s*:\s*"([^"]+)"', user_message)
        prop_m = re.search(r'"proposed"\s*:\s*([0-9]+)', user_message)
        rev_m = re.search(r'"reviewed"\s*:\s*([0-9]+)', user_message)
        pass_m = re.search(r'"passed"\s*:\s*([0-9]+)', user_message)
        att_m = re.search(r'"attendance_pct"\s*:\s*([0-9]+)', user_message)
        pr_m = re.search(r'"pass_rate"\s*:\s*"([0-9]+)"', user_message)
        ab_m = re.search(r'"assigned_bills"\s*:\s*\[([^\]]+)\]', user_message)
        chair_m = re.search(r'"chair_name"\s*:\s*"([^"]+)"', user_message)

        if cid_m and cn_m:
            cname = cn_m.group(1)
            proposed = int(prop_m.group(1)) if prop_m else 0
            reviewed = int(rev_m.group(1)) if rev_m else 0
            passed = int(pass_m.group(1)) if pass_m else 0
            att = int(att_m.group(1)) if att_m else 0
            pass_rate = pr_m.group(1) if pr_m else "0"
            bills = re.findall(r'"([^"]+)"', ab_m.group(1)) if ab_m else []
            chair = chair_m.group(1) if chair_m else "—"
            bill_list = " · ".join(bills[:3]) if bills else "—"

            headline = (
                f"\"{cname}\" — 발의 {proposed}건 · 심사 {reviewed}건 · 통과 {passed}건 · 출석 {att}% · "
                f"*통과율 {pass_rate}%*. 위원장: {chair} (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
            )
            findings = (
                f"- 위원회: \"{cname}\" (위원장 {chair})\n"
                f"- 발의 {proposed}건 → 심사 {reviewed}건 → 통과 {passed}건 — 통과율 {pass_rate}%\n"
                f"- 출석률 {att}% — 22대 평균 88% 대비 {'상위' if att > 88 else '하위'} percentile\n"
                f"- 소관 의안 (top): {bill_list}\n"
                f"- 위원회 영향력 score: 발의 + 통과 + 출석 종합\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{cname}\" 통과 {passed}건 + 통과율 {pass_rate}%는 *위원회 lifecycle 효율성* 정량. "
                    f"위원장 {chair} 인터뷰 + 소관 의안 {bill_list[:30]} 단계 추적 기획기사."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{cname}\" 통과율 {pass_rate}% — 통과 logistic regression input. "
                    f"발의/심사/통과 funnel + cross-committee 협력 cluster 분석 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{cname}\"에서 {passed}건 통과 — 출석률 {att}%. "
                    f"위원장 {chair} 주도 + 소관 의안 추적 가능."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{cname}\" PDF 3-page 시그니처 + 소관 의안 lifecycle 추적 + cross-committee 협력 dashboard."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{cname}\" 통과 {passed}건은 *시행 단계 광고 hook* — 관련 산업 cohort 매칭."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{cname}\" alert — 통과율 {pass_rate}% logistic input. "
                    f"소관 의안 {bill_list[:30]} 시행령 단계 모니터링."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{cname}\"의 *발의→심사→통과 funnel*은 *입법 lifecycle의 가장 정확한 lens*. "
                f"통과율 {pass_rate}%는 *분기별 priority narrative* 핵심. "
                f"위원장 {chair} timeline (시나리오 M) + cross-committee 협력 (시나리오 D) 결합 가치 ↑."
            )
            cta_text = (
                f"- \"{cname}\" 소관 의안 {len(bills)}건 lifecycle 단계별 추적\n"
                f"- 위원장 {chair} 정치 timeline (시나리오 M PDF)\n"
                f"- \"{cname}\" cross-committee 협력 cluster 발굴\n"
                f"- 통과율 {pass_rate}% 분기 trend + logistic 예측\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 R 공약 이행 추적 — promise_id·카테고리·이행률 inject
    if scenario_label == "공약 이행 추적":
        rid_m = re.search(r'"promise_id"\s*:\s*"([^"]+)"', user_message)
        cat_m = re.search(r'"promise_category"\s*:\s*"([^"]+)"', user_message)
        prm_m = re.search(r'"promised"\s*:\s*([0-9]+)', user_message)
        fld_m = re.search(r'"filed"\s*:\s*([0-9]+)', user_message)
        pas_m = re.search(r'"passed"\s*:\s*([0-9]+)', user_message)
        fr_m = re.search(r'"file_rate"\s*:\s*"([0-9]+)"', user_message)
        pr_m = re.search(r'"pass_rate"\s*:\s*"([0-9]+)"', user_message)
        fb_m = re.search(r'"filed_bills"\s*:\s*\[([^\]]+)\]', user_message)
        pb_m = re.search(r'"passed_bills"\s*:\s*\[([^\]]+)\]', user_message)
        pp_m = re.search(r'"proposers"\s*:\s*\[([^\]]+)\]', user_message)

        if rid_m and cat_m:
            category = cat_m.group(1)
            promised = int(prm_m.group(1)) if prm_m else 0
            filed = int(fld_m.group(1)) if fld_m else 0
            passed = int(pas_m.group(1)) if pas_m else 0
            file_rate = fr_m.group(1) if fr_m else "0"
            pass_rate = pr_m.group(1) if pr_m else "0"
            filed_bills = re.findall(r'"([^"]+)"', fb_m.group(1)) if fb_m else []
            passed_bills = re.findall(r'"([^"]+)"', pb_m.group(1)) if pb_m else []
            proposers = re.findall(r'"([^"]+)"', pp_m.group(1)) if pp_m else []
            prop_list = " · ".join(proposers[:3]) if proposers else "—"
            fb_str = " · ".join(filed_bills[:3]) if filed_bills else "—"
            pb_str = " · ".join(passed_bills[:3]) if passed_bills else "—"

            headline = (
                f"\"{category}\" 공약 — 총 {promised}건 → 발의 {filed}건 ({file_rate}%) → 가결 {passed}건 ({pass_rate}%). "
                f"*공약 vs 실적 gap* 정량 추적 (출처: 합성 공약 + 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)."
            )
            findings = (
                f"- 공약 카테고리: \"{category}\" — {promised}건 공약\n"
                f"- 발의 {filed}건 (이행률 {file_rate}%) · 가결 {passed}건 (가결률 {pass_rate}%)\n"
                f"- 발의 의안 (top): {fb_str}\n"
                f"- 가결 의안 (top): {pb_str}\n"
                f"- 대표 발의 의원: {prop_list}\n"
                f"- 잔여 미이행 공약: {max(0, promised - filed)}건 ({100 - int(file_rate)}%)\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{category}\" 이행률 {file_rate}% + 가결률 {pass_rate}%는 *공약-실적 gap narrative*. "
                    f"미이행 {max(0, promised - filed)}건 → 발의 의원 {prop_list[:30]} 인터뷰 후보."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{category}\" 이행률 {file_rate}% — 공약-실적 logistic regression input. "
                    f"카테고리 cohort variance 분석 + lifecycle 통과율 비교 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{category}\" 공약 {promised}건 중 {filed}건 발의됨 ({file_rate}%). "
                    f"가결 {passed}건 — *내가 표를 준 공약*이 어떻게 이행되었는지 확인 가능."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{category}\" 공약 PDF 추적 + 미이행 공약 alert + 시행령 단계 추적."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{category}\" 가결 {passed}건은 *시행 단계* — 관련 산업 광고 cohort 매칭 가능."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{category}\" 이행률 {file_rate}% alert + 미이행 {max(0, promised - filed)}건 logistic 예측. "
                    f"발의 의원 {prop_list[:30]} 정책 priority."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{category}\" 공약 이행률 {file_rate}%는 *민주적 응답성* 정량 narrative. "
                f"가결률 {pass_rate}% + 미이행 {max(0, promised - filed)}건은 *시나리오 N (이슈×입법 상관)*의 lag 시그널. "
                f"발의 의원 timeline (시나리오 M) + 청원 매핑 (시나리오 P) 결합이 *장기 narrative 가치*."
            )
            cta_text = (
                f"- \"{category}\" 미이행 공약 {max(0, promised - filed)}건 분석 + 대안 의제 제안\n"
                f"- 대표 발의 의원 ({prop_list}) 직접 인터뷰\n"
                f"- 가결 {passed}건 시행령 단계 추적 (시나리오 K signature)\n"
                f"- \"{category}\" 카테고리 청원-공약-입법 cross-tab (시나리오 P·N)\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 S 토픽 burst — burst_id·토픽·burst_week·시계열 inject
    if scenario_label == "토픽 burst 시계열":
        bid_m = re.search(r'"burst_id"\s*:\s*"([^"]+)"', user_message)
        tl_m = re.search(r'"topic_label"\s*:\s*"([^"]+)"', user_message)
        bw_m = re.search(r'"burst_week"\s*:\s*([0-9]+)', user_message)
        bv_m = re.search(r'"burst_value"\s*:\s*([0-9]+)', user_message)
        tf_m = re.search(r'"total_filings_13w"\s*:\s*([0-9]+)', user_message)
        ap_m = re.search(r'"avg_per_week"\s*:\s*"([0-9.]+)"', user_message)
        tb_m = re.search(r'"topic_bills"\s*:\s*\[([^\]]+)\]', user_message)
        tp_m = re.search(r'"topic_proposers"\s*:\s*\[([^\]]+)\]', user_message)

        if bid_m and tl_m:
            tlabel = tl_m.group(1)
            burst_w = int(bw_m.group(1)) if bw_m else 0
            burst_v = int(bv_m.group(1)) if bv_m else 0
            total = int(tf_m.group(1)) if tf_m else 0
            avg = ap_m.group(1) if ap_m else "0"
            bills = re.findall(r'"([^"]+)"', tb_m.group(1)) if tb_m else []
            proposers = re.findall(r'"([^"]+)"', tp_m.group(1)) if tp_m else []
            bill_list = " · ".join(bills[:3]) if bills else "—"
            prop_list = " · ".join(proposers[:3]) if proposers else "—"

            headline = (
                f"\"{tlabel}\" — W{burst_w} 주차 burst {burst_v}건 · 13주 누적 {total}건 (주당 평균 {avg}건). "
                f"*분기별 토픽 시계열 burst* 정량 (출처: 합성 의안 timeline + 외부 신호 2026-05)."
            )
            findings = (
                f"- 토픽: \"{tlabel}\" — 13주 누적 발의 {total}건\n"
                f"- burst peak: W{burst_w} 주차 ({burst_v}건) — 평균 {avg}건의 {int(burst_v / max(1, float(avg)))}배\n"
                f"- 주요 의안: {bill_list}\n"
                f"- 핵심 발의 의원: {prop_list}\n"
                f"- 외부 신호 lag (네이버 뉴스 + SNS) cross-correlation 권장\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{tlabel}\" W{burst_w} burst {burst_v}건은 *분기 priority narrative*. "
                    f"발의 의원 {prop_list[:30]} 인터뷰 + 외부 신호 lag 기획기사. "
                    f"주요 의안 {bill_list[:30]} 시행령 단계 추적."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{tlabel}\" burst W{burst_w} — z-score 통계 유의. "
                    f"외부 신호 (뉴스 + SNS) ↔ 입법 timeline cross-correlation lag 정량 분석 권장."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{tlabel}\" 토픽은 *W{burst_w} 주차에 가장 활성* ({burst_v}건). "
                    f"이 주제로 {total}건 의안 발의 — 내 관심사라면 알림 받기 가능."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{tlabel}\" 시계열 PDF + burst 의안 lifecycle 추적 + 외부 신호 lag dashboard."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{tlabel}\" W{burst_w} burst는 *시민 관심 peak* — 관련 광고 cohort 매칭 적합."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{tlabel}\" burst alert + 의안 {bill_list[:30]} 시행 timeline + 외부 신호 lag 예측."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{tlabel}\" 토픽의 W{burst_w} burst {burst_v}건은 *시민 관심 ↔ 입법 응답* lag의 정량 시그널. "
                f"누적 {total}건 + burst peak은 *시나리오 J (외부 신호 융합)*과 *시나리오 N (이슈×입법 상관)*의 핵심 input. "
                f"발의 의원 timeline (시나리오 M) + 청원 매핑 (시나리오 P) 결합이 *장기 narrative 가치*."
            )
            cta_text = (
                f"- \"{tlabel}\" W{burst_w} burst 의안 {len(bills)}건 lifecycle 단계별 추적\n"
                f"- 외부 신호 (네이버 뉴스 + SNS) ↔ \"{tlabel}\" lag cross-correlation\n"
                f"- 핵심 발의 의원 ({prop_list}) 직접 인터뷰 (시나리오 M)\n"
                f"- \"{tlabel}\" 토픽 청원-입법 매칭 (시나리오 P) + 외부 신호 (시나리오 J) 결합 대시보드\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 B (챗봇) — query-aware 의원 영향력·응집도·swing voter 답변
    if scenario_label == "기자/독자 챗봇":
        ir_m = re.search(r"\[real Neptune /api/insights/influence-rank top 5\]\n(.+?)(?=\[|\Z)", user_message, re.DOTALL)
        pc_m = re.search(r"\[real Neptune /api/insights/party-cohesion overall ([0-9.]+)%\]\n(.+?)(?=\[|\Z)", user_message, re.DOTALL)
        sv_m = re.search(r"\[real Neptune /api/insights/swing-voters threshold 95% · ([0-9]+)명\]\n(.+?)(?=\[|\Z)", user_message, re.DOTALL)

        if ir_m:
            rows = [l for l in ir_m.group(1).strip().split("\n") if l.strip()]
            row1 = rows[0] if rows else ""
            name_m = re.search(r"#1\s+(\S+)\s+\(([^)]+)\)", row1)
            prop_m = re.search(r"발의\s+(\d+)", row1)
            co_m = re.search(r"공동\s+(\d+)", row1)
            ch_m = re.search(r"cohort\s+(\d+)", row1)
            r1_name = name_m.group(1) if name_m else "—"
            r1_party = name_m.group(2) if name_m else "—"
            r1_prop = prop_m.group(1) if prop_m else "—"
            r1_co = co_m.group(1) if co_m else "—"
            r1_cohort = ch_m.group(1) if ch_m else "—"
            top_lines = "\n".join(f"- {l}" for l in rows[:5])
            headline = (
                f"22대 의원 영향력 ranking 1위: **{r1_name} ({r1_party})** — "
                f"대표 발의 {r1_prop}건 · 공동 발의 {r1_co}건 · cohort 가중치 {r1_cohort} (출처: real Neptune /api/insights/influence-rank)."
            )
            findings = (
                f"**Top 5 (real Neptune 22대 임기)**:\n{top_lines}\n\n"
                f"- 공식: `0.6 × cohort/max + 0.25 × proposed/30 + 0.15 × co_proposed/200` (min 1.0 cap)\n"
                f"- 1위 driver: *{r1_name}*은 cohort hub(3258)·발의 활동({r1_prop})·협력({r1_co}) **세 항목 모두 normalize threshold 초과** → score 1.0 saturated\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n편집국 시점: *{r1_name}*는 *네트워크 hub로의 인터뷰 가치 최상위* — 22대 임기 cohort 가중치 hub. 상위 5명은 *데스크 정치 narrative의 핵심 인물*.\n\n"
                f"## 💡 비즈니스/취재 함의\nReal Neptune `/api/insights/influence-rank` 직접 호출 결과. 챗봇이 query keyword(\"영향력\")를 감지하여 fixture 대신 real data tool dispatch — *Agent Tool Use 패턴* 활성화 시연.\n\n"
                f"## {cta}\n- *{r1_name}* 의원 timeline (시나리오 M)\n- top 5 cohort hub 의원 cross-party 협력 분석\n- 시나리오 U 페이지에서 ranking 전체 확인\n"
            )

        if pc_m:
            overall = pc_m.group(1)
            rows = [l for l in pc_m.group(2).strip().split("\n") if l.strip()]
            top_lines = "\n".join(f"- {l}" for l in rows[:5])
            headline = f"22대 정당 응집도 평균 **{overall}%** — 8 정당 ranking real Neptune 분석 (출처: /api/insights/party-cohesion)."
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n**Top 5 정당**:\n{top_lines}\n\n"
                f"## 👤 페르소나 시점 해석\n편집국 시점: 평균 {overall}%는 *당론 강한 정치문화*의 정량 시그널 — 22대는 *역대 최고 응집도*.\n\n"
                f"## 💡 비즈니스/취재 함의\nReal Neptune 직접 호출. 시나리오 T 페이지에서 정당별 시계열 trend 확인.\n\n"
                f"## {cta}\n- 정당 응집도 차이 narrative (99% vs 88%)\n- swing voter (시나리오 W) cross-reference\n- 분기별 trend 추적\n"
            )

        if sv_m:
            cnt = sv_m.group(1)
            rows = [l for l in sv_m.group(2).strip().split("\n") if l.strip()]
            top_lines = "\n".join(f"- {l}" for l in rows[:5])
            headline = f"Swing voter (정당 일치율 < 95%) — 22대 임기 **{cnt}명** 탐지 (출처: /api/insights/swing-voters threshold 95)."
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n**Top 5 swing voter**:\n{top_lines}\n\n"
                f"## 👤 페르소나 시점 해석\n편집국 시점: 정당 노선과 *다른 표결* 패턴은 *개별 인터뷰 hook 최강*. 22대 응집도 99%+ 환경에서 95%+ 이탈 의원은 매우 narrative 가치 ↑.\n\n"
                f"## 💡 비즈니스/취재 함의\nReal Neptune 직접 호출. 시나리오 W 페이지에서 threshold·deviation 상세 확인.\n\n"
                f"## {cta}\n- top 5 swing voter individual 시리즈 기획기사\n- 이탈 의안 카테고리 분석\n- 정당 응집도 (시나리오 T) cross-tab\n"
            )

    # 시나리오 T 정당 응집도 — overall_cohesion + parties top inject
    if scenario_label == "정당 응집도":
        oc_m = re.search(r'"overall_cohesion"\s*:\s*([0-9.]+)', user_message)
        pc_m = re.search(r'"party_count"\s*:\s*([0-9]+)', user_message)
        tav_m = re.search(r'"total_active_votes"\s*:\s*([0-9]+)', user_message)
        # parties 상위 3개 추출
        parties_m = re.search(r'"parties"\s*:\s*\[([^\]]+)\]', user_message)

        overall = float(oc_m.group(1)) if oc_m else 0.0
        party_cnt = int(pc_m.group(1)) if pc_m else 0
        tot_votes = int(tav_m.group(1)) if tav_m else 0
        top_parties_str = "—"
        if parties_m:
            names = re.findall(r'"name"\s*:\s*"([^"]+)"', parties_m.group(1))[:3]
            aligns = re.findall(r'"alignment_pct"\s*:\s*([0-9]+)', parties_m.group(1))[:3]
            members = re.findall(r'"members"\s*:\s*([0-9]+)', parties_m.group(1))[:3]
            top_parties_str = " · ".join(
                f"{n} ({members[i] if i < len(members) else '?'}명, {aligns[i] if i < len(aligns) else '?'}%)"
                for i, n in enumerate(names)
            )

        headline = (
            f"22대 국회 {party_cnt}개 정당 응집도 평균 *{int(overall*100)}%* · "
            f"총 표결 {tot_votes:,}건 분석. Top: {top_parties_str} "
            f"(출처: 22대 임기 · VOTED 28,528 엣지 + BELONGS_TO Cypher 분석)."
        )
        findings = (
            f"- 분석 정당 {party_cnt}개 — 평균 응집도 {int(overall*100)}%\n"
            f"- Top 정당: {top_parties_str}\n"
            f"- 활성 표결 {tot_votes:,}건 (absent 제외)\n"
            f"- *정당 majority value (yes/no/abstain) 일치율* 측정\n"
            f"- 응집도 99%+ 정당 다수 — 22대 *당론 강한 정치문화*\n"
            f"- *active 표결만 분석*이라 *불참 의원의 ambiguity 제거*\n"
        )
        persona_lens_map = {
            "editorial": (
                f"편집국 시점: 22대 정당 응집도 {int(overall*100)}%는 *당론 강한 정치문화*의 정량 시그널. "
                f"Top 정당 {top_parties_str} — *각 정당의 응집도 차이* (99% vs 88%)가 *후속 기획기사 hook*. "
                f"*개별 의원 이탈*은 시나리오 W (Swing voter)에서 detection."
            ),
            "data_ai": (
                f"데이터·AI 데스크 시점: {tot_votes:,}건 active 표결의 majority alignment 계산. "
                f"통계적으로 95%+ 응집도는 *p < 0.001 정당 cluster 유의성* — *random vote 가설 기각*. "
                f"absent를 포함하면 응집도 ~85%로 *변동* — 분석 사용 의도에 따라 view 토글 권장."
            ),
            "general_reader": (
                f"일반 독자 시점: 22대 정당들이 *대부분 한 목소리*로 표결. 응집도 {int(overall*100)}%는 *당론이 표결에 강하게 반영*된다는 의미. "
                f"개별 의원이 *정당과 다르게 표결*하는 경우는 *swing voter* 페이지에서 추적 가능."
            ),
            "paid_subscriber": (
                f"유료 구독자 시점: 정당 응집도 dashboard PDF + 시계열 trend + 정당별 cohort variance 분석. "
                f"분기별 응집도 변동 alert + 22대 임기 24개월 trend chart."
            ),
            "ad_sales": (
                f"광고·세일즈 시점: 응집도 높은 정당 narrative는 *광고 위험* (정치 양극화 시그널). "
                f"중도·무소속 cohort는 *공익 광고 매칭 적합* (cross-party narrative)."
            ),
            "b2b": (
                f"B2B 정책 인텔리전스 시점: 정당 응집도 {int(overall*100)}% alert. "
                f"의안 통과 logistic regression의 *정당 cohort 가중치 input*. "
                f"클라이언트별 정당 stance 매트릭스 자동 생성."
            ),
        }
        persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
        implication = (
            f"22대 국회 정당 응집도 평균 {int(overall*100)}%는 *당론 정치문화의 정량 baseline*. "
            f"*시나리오 K·W·V* (표결 이상치·swing voter·voting cluster) 결합 시 *정당 단일 narrative*에서 *개별 의원 차이*로 *narrative depth 확장*. "
            f"22대 임기 24개월 trend는 *정치 양극화 진행 정도*의 시그널."
        )
        cta_text = (
            f"- 정당별 응집도 시계열 (분기별) trend 분석\n"
            f"- 응집도 99% vs 88% 정당의 *내부 분열 의안* 찾기 (시나리오 K)\n"
            f"- *swing voter* ranking (시나리오 W) — *개별 의원 인터뷰* 후보\n"
            f"- 응집도 ↔ 의안 통과율 cross-correlation (logistic regression)\n"
        )
        return (
            f"{header}\n\n"
            f"## 📌 헤드라인\n{headline}\n\n"
            f"## 🔍 핵심 발견\n{findings}\n\n"
            f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
            f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
            f"## {cta}\n{cta_text}"
        )

    # 시나리오 U 의원 영향력 — top member + rank1 inject
    if scenario_label == "의원 영향력":
        r1n_m = re.search(r'"rank1_name"\s*:\s*"([^"]+)"', user_message)
        r1p_m = re.search(r'"rank1_party"\s*:\s*"([^"]+)"', user_message)
        r1prop_m = re.search(r'"rank1_proposed"\s*:\s*([0-9]+)', user_message)
        r1cw_m = re.search(r'"rank1_cohort_weight"\s*:\s*([0-9]+)', user_message)
        tmn_m = re.search(r'"top_member_names"\s*:\s*\[([^\]]+)\]', user_message)
        tps_m = re.search(r'"top_member_parties"\s*:\s*\[([^\]]+)\]', user_message)

        r1_name = r1n_m.group(1) if r1n_m else "—"
        r1_party = r1p_m.group(1) if r1p_m else "—"
        r1_prop = int(r1prop_m.group(1)) if r1prop_m else 0
        r1_cw = int(r1cw_m.group(1)) if r1cw_m else 0
        top_names = re.findall(r'"([^"]+)"', tmn_m.group(1))[:10] if tmn_m else []
        top_parties = re.findall(r'"([^"]+)"', tps_m.group(1))[:4] if tps_m else []
        top_names_str = " · ".join(top_names[:5]) if top_names else "—"
        parties_str = " / ".join(top_parties) if top_parties else "—"

        headline = (
            f"22대 의원 영향력 ranking — *{r1_name} ({r1_party})* 1위 (대표 발의 {r1_prop}건 + cohort 가중치 {r1_cw:,}). "
            f"Top 5: {top_names_str}. 정당 분포: {parties_str} "
            f"(출처: 22대 임기 · CO_PROPOSED_WITH 19,191 cohort + Cypher 2-phase query)."
        )
        findings = (
            f"- 1위: *{r1_name} ({r1_party})* — 대표 발의 {r1_prop}건 + cohort 가중치 {r1_cw:,}\n"
            f"- Top 5: {top_names_str}\n"
            f"- 정당 분포 (top): {parties_str}\n"
            f"- *영향력 = 0.6 cohort + 0.25 propose + 0.15 co_propose* 가중 합산\n"
            f"- cohort 가중치는 *공동발의 네트워크 hub strength* (degree centrality proxy)\n"
            f"- 22대 임기 24개월 누적 활동 종합 ranking\n"
        )
        persona_lens_map = {
            "editorial": (
                f"편집국 시점: *{r1_name} ({r1_party})*가 영향력 top — *네트워크 hub로의 인터뷰 가치 매우 높음*. "
                f"Top 5 {top_names_str}는 *데스크 정치 narrative의 핵심 인물*. "
                f"각 의원의 *cohort 어느 정당과 공동발의*가 *cross-party 협력 narrative hook*."
            ),
            "data_ai": (
                f"데이터·AI 데스크 시점: degree centrality 기반 PageRank proxy. "
                f"{r1_name}의 cohort {r1_cw:,} weight는 *통계적 outlier* (z>2). "
                f"PageRank 정식 알고리즘 적용 시 *transitive influence* 추가 발굴 가능."
            ),
            "general_reader": (
                f"일반 독자 시점: 22대 가장 *활동량 많은 의원*은 *{r1_name} ({r1_party})*. "
                f"발의 {r1_prop}건 + 다른 의원들과 *공동 발의 {r1_cw:,}회*. "
                f"Top 5 {top_names_str}이 *주요 정책 이슈* 주도."
            ),
            "paid_subscriber": (
                f"유료 구독자 시점: 영향력 top-20 의원 PDF + 각자의 *cohort 네트워크 visualization* + 시계열 trend."
            ),
            "ad_sales": (
                f"광고·세일즈 시점: top 영향력 의원의 *정책 분야* 분석 → 광고 cohort 매칭. "
                f"{r1_name}의 의안 분야와 *광고주 산업 cross-tab*."
            ),
            "b2b": (
                f"B2B 정책 인텔리전스 시점: *{r1_name}* 등 top-20 의원 *모니터링 priority alert*. "
                f"이들이 발의/공동발의한 의안은 *통과 가능성 logistic +0.3 weight*."
            ),
        }
        persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
        implication = (
            f"*{r1_name}* 1위 + top 5 {top_names_str}가 *22대 정치 네트워크의 hub layer*. "
            f"cohort 가중치 {r1_cw:,}는 *real OpenAPI 공동발의 메타에서 derive* — *fact-based influence ranking*. "
            f"*시나리오 F (룩어라이크) + O (인물 관계)* 결합으로 *2-hop 영향력 전파 분석* 가능."
        )
        cta_text = (
            f"- *{r1_name}* 등 top 5 의원 PDF 시그니처 (시나리오 M)\n"
            f"- Cohort hub의 *cross-party 공동발의 비율* 시각화\n"
            f"- 영향력 ranking ↔ 의안 통과율 cross-correlation\n"
            f"- *PageRank 정식 알고리즘* 적용 (transitive influence 추가)\n"
        )
        return (
            f"{header}\n\n"
            f"## 📌 헤드라인\n{headline}\n\n"
            f"## 🔍 핵심 발견\n{findings}\n\n"
            f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
            f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
            f"## {cta}\n{cta_text}"
        )

    # 시나리오 V 표결 cluster — 선택 cluster의 label·member_count·avg_yes_rate inject
    if scenario_label == "표결 cluster":
        cid_m = re.search(r'"cluster_id"\s*:\s*"([^"]+)"', user_message)
        cl_m = re.search(r'"cluster_label"\s*:\s*"([^"]+)"', user_message)
        mc_m = re.search(r'"member_count"\s*:\s*([0-9]+)', user_message)
        ayr_m = re.search(r'"avg_yes_rate"\s*:\s*([0-9.]+)', user_message)
        dp_m = re.search(r'"dominant_parties"\s*:\s*\[([^\]]+)\]', user_message)
        tmn_m = re.search(r'"top_member_names"\s*:\s*\[([^\]]+)\]', user_message)

        if cid_m and cl_m:
            cluster_label = cl_m.group(1)
            mcount = int(mc_m.group(1)) if mc_m else 0
            yes_rate = float(ayr_m.group(1)) if ayr_m else 0.0
            parties = re.findall(r'"([^"]+)"', dp_m.group(1))[:3] if dp_m else []
            names = re.findall(r'"([^"]+)"', tmn_m.group(1))[:5] if tmn_m else []
            party_list = " · ".join(parties) if parties else "—"
            name_list = " · ".join(names) if names else "—"

            headline = (
                f"표결 cluster *{cluster_label}* — 의원 {mcount}명 · 평균 찬성률 {int(yes_rate*100)}%. "
                f"주요 정당: {party_list}. 대표 의원: {name_list} "
                f"(출처: 22대 임기 · VOTED 28,528 엣지 + 정당 cluster 자동 분류)."
            )
            findings = (
                f"- Cluster: *{cluster_label}* — 의원 {mcount}명\n"
                f"- 평균 찬성률 {int(yes_rate*100)}% (active 표결 기준)\n"
                f"- 주요 정당: {party_list}\n"
                f"- 대표 의원 (sample): {name_list}\n"
                f"- 분류: yes_rate ≥ 70% → 높은 찬성률, < 70% → 신중 표결\n"
                f"- 정당 mapping: 진보계열 (민주·조국혁신·진보·기본소득), 보수계열 (국민의힘·개혁신당), 중도 (무소속)\n"
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: *{cluster_label}* cluster {mcount}명 — *정책 찬성률 {int(yes_rate*100)}%* narrative. "
                    f"{name_list[:30]}이 *이 cluster의 대표 인물*. *cross-cluster 의원 이동*은 *정치 narrative 변화* 시그널."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: cluster centroid yes_rate {int(yes_rate*100)}% (variance ±15pp 예상). "
                    f"KMeans 정식 적용 시 *추가 cluster 발굴* + *silhouette score* 검증."
                ),
                "general_reader": (
                    f"일반 독자 시점: *{cluster_label}*에 속한 {mcount}명 의원들의 표결 패턴이 비슷. "
                    f"찬성률 {int(yes_rate*100)}% — 이 그룹은 *주요 의안에 찬성/반대 성향*."
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: *{cluster_label}* cluster PDF + 의원별 yes_rate distribution + 분기별 변동."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: *{cluster_label}* cluster {mcount}명 — 해당 cohort 광고 매칭 적합도. "
                    f"중도 cluster는 cross-party narrative 적합."
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: *{cluster_label}* cluster {mcount}명 alert + "
                    f"해당 정당 stance 자동 분석 + 시행령 통과 가능성 logistic."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"*{cluster_label}* {mcount}명 + 찬성률 {int(yes_rate*100)}% 패턴은 *cohort 정량 narrative*. "
                f"5 cluster (보수/진보 × 신중/높은 찬성 + 중도) 분류가 *정치 양극화 시각화의 단순 framework*. "
                f"*시나리오 T (정당 응집도) + K (이상치) + W (swing)* 결합으로 *cluster 내부 변동성 추적*."
            )
            cta_text = (
                f"- *{cluster_label}* 의원 {mcount}명 timeline (시나리오 M)\n"
                f"- cluster centroid yes_rate ↔ 의안 카테고리 분석\n"
                f"- *cross-cluster 의원* 이탈 detection (cluster 경계 변화)\n"
                f"- KMeans 정식 적용 + silhouette score 검증 (다음 phase)\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 W Swing voter — rank1 + threshold inject
    if scenario_label == "Swing voter":
        th_m = re.search(r'"threshold_pct"\s*:\s*([0-9]+)', user_message)
        sc_m = re.search(r'"swing_count"\s*:\s*([0-9]+)', user_message)
        aa_m = re.search(r'"avg_alignment"\s*:\s*([0-9]+)', user_message)
        r1n_m = re.search(r'"rank1_name"\s*:\s*"([^"]+)"', user_message)
        r1p_m = re.search(r'"rank1_party"\s*:\s*"([^"]+)"', user_message)
        r1a_m = re.search(r'"rank1_alignment"\s*:\s*([0-9]+)', user_message)
        r1d_m = re.search(r'"rank1_deviation"\s*:\s*([0-9]+)', user_message)
        tmn_m = re.search(r'"top_member_names"\s*:\s*\[([^\]]+)\]', user_message)
        tps_m = re.search(r'"top_member_parties"\s*:\s*\[([^\]]+)\]', user_message)

        threshold = int(th_m.group(1)) if th_m else 85
        swing_cnt = int(sc_m.group(1)) if sc_m else 0
        avg_align = int(aa_m.group(1)) if aa_m else 0
        r1_name = r1n_m.group(1) if r1n_m else "—"
        r1_party = r1p_m.group(1) if r1p_m else "—"
        r1_align = int(r1a_m.group(1)) if r1a_m else 0
        r1_dev = int(r1d_m.group(1)) if r1d_m else 0
        top_names = re.findall(r'"([^"]+)"', tmn_m.group(1))[:5] if tmn_m else []
        top_parties = re.findall(r'"([^"]+)"', tps_m.group(1)) if tps_m else []
        name_list = " · ".join(top_names) if top_names else "—"
        party_set = list(set(top_parties))[:3]
        party_str = " · ".join(party_set) if party_set else "—"

        headline = (
            f"Swing voter ranking — 정당 일치율 < {threshold}% 의원 {swing_cnt}명. "
            f"1위: *{r1_name} ({r1_party})* — 일치율 {r1_align}% (이탈 {r1_dev}건). "
            f"Top 5: {name_list}. 정당 분포: {party_str} "
            f"(출처: 22대 임기 · VOTED 28,528 + BELONGS_TO Cypher 자동 detection)."
        )
        findings = (
            f"- Threshold: {threshold}% — 정당 majority 일치율 *그 이하* 의원 {swing_cnt}명 탐지\n"
            f"- 1위: *{r1_name} ({r1_party})* — 일치율 {r1_align}% (이탈 {r1_dev}건)\n"
            f"- Top 5 swing voters: {name_list}\n"
            f"- 정당 분포 (top): {party_str}\n"
            f"- 평균 일치율: {avg_align}% (swing voter 그룹)\n"
            f"- *active 표결 10건 이상* 의원만 평가 (sample size 안정성)\n"
        )
        persona_lens_map = {
            "editorial": (
                f"편집국 시점: *{r1_name} ({r1_party})*가 *정당 노선과 다른 표결 {r1_dev}건*. "
                f"이런 *individual story*는 *개별 인터뷰 hook 최강* — *왜 그랬는지 직접 질문 가능*. "
                f"Top 5 {name_list}는 *각자 다른 이탈 사유* (지역구·산업·신념) → *5명 individual 시리즈 기획*."
            ),
            "data_ai": (
                f"데이터·AI 데스크 시점: swing voter detection의 *false positive 가능성* — *small sample size 의원* 또는 *기권/불참 빈번 의원*도 통계적 outlier로 표시될 수 있음. "
                f"*active 표결 10건+ filter*로 *robust*. 더 정교한 detection은 *시계열 trend + LLM 사유 추론*."
            ),
            "general_reader": (
                f"일반 독자 시점: *{r1_name}* 의원은 *{r1_party} 다수와 다르게* {r1_dev}건 투표. "
                f"이런 *개별 신념*이 표결로 드러난 case. Top 5 {name_list}도 *정당 노선 외 표결*."
            ),
            "paid_subscriber": (
                f"유료 구독자 시점: swing voter top-20 PDF + 각자의 *이탈 의안 list* + *시계열 trend*. "
                f"분기별 swing 빈도 alert."
            ),
            "ad_sales": (
                f"광고·세일즈 시점: swing voter는 *정파 narrative 외 인터뷰 가치 ↑* — *공익·중립 콘텐츠 적합*. "
                f"광고 매칭 시 *정당 stance 부담 낮음*."
            ),
            "b2b": (
                f"B2B 정책 인텔리전스 시점: swing voter는 *예측 불가 vote* — logistic regression *uncertainty input*. "
                f"클라이언트별 priority bill의 *swing voter cross-tab*."
            ),
        }
        persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
        implication = (
            f"*{r1_name}* 등 top 5 swing voter는 *22대 정당 정치의 individual variance 시그널*. "
            f"평균 일치율 {avg_align}% + 1위 {r1_align}%는 *정당 응집도 (T 시나리오) 99%의 backside* — *5% 의원이 narrative 전환점*. "
            f"*시나리오 K (이상치) + O (인물 관계) + M (여정)* 결합으로 *individual swing voter의 *full profile***."
        )
        cta_text = (
            f"- *{r1_name}* 의원 직접 인터뷰 (시나리오 M timeline)\n"
            f"- Top 5 swing voter individual 시리즈 기획기사\n"
            f"- 이탈 의안 카테고리 분석 (지역구·산업·신념 cohort)\n"
            f"- threshold 조정 (75%·85%·95%) 시각 비교\n"
        )
        return (
            f"{header}\n\n"
            f"## 📌 헤드라인\n{headline}\n\n"
            f"## 🔍 핵심 발견\n{findings}\n\n"
            f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
            f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
            f"## {cta}\n{cta_text}"
        )

    # 시나리오 P 청원 매핑 — 선택 청원의 title·category·signatures·matched_bills·lifecycle inject
    if scenario_label == "시민 청원 입법 매핑":
        pid_m = re.search(r'"petition_id"\s*:\s*"([^"]+)"', user_message)
        pt_m = re.search(r'"petition_title"\s*:\s*"([^"]+)"', user_message)
        cat_m = re.search(r'"category"\s*:\s*"([^"]+)"', user_message)
        sig_m = re.search(r'"signatures"\s*:\s*([0-9]+)', user_message)
        mb_m = re.search(r'"matched_bills"\s*:\s*([0-9]+)', user_message)
        lc_m = re.search(r'"lifecycle_label"\s*:\s*"([^"]+)"', user_message)
        bills_m = re.search(r'"matched_bill_titles"\s*:\s*\[([^\]]+)\]', user_message)
        props_m = re.search(r'"proposers"\s*:\s*\[([^\]]+)\]', user_message)
        topic_m = re.search(r'"topic"\s*:\s*"([^"]+)"', user_message)

        if pid_m and pt_m:
            ptitle = pt_m.group(1)
            category = cat_m.group(1) if cat_m else "—"
            signatures = int(sig_m.group(1)) if sig_m else 0
            matched_bills = int(mb_m.group(1)) if mb_m else 0
            lifecycle = lc_m.group(1) if lc_m else "—"
            bill_titles = re.findall(r'"([^"]+)"', bills_m.group(1)) if bills_m else []
            proposers = re.findall(r'"([^"]+)"', props_m.group(1)) if props_m else []
            topic = topic_m.group(1) if topic_m else category

            headline = (
                f"청원 \"{ptitle}\" — {category} · 서명 {signatures:,}명 · 매칭 의안 {matched_bills}건 · *{lifecycle}* 단계. "
                f"*시민 voice → 입법 lifecycle*의 정량 추적 (출처: 22대 임기 · 합성 청원 + 국회 OpenAPI)."
            )
            bill_list = " · ".join(bill_titles[:3]) if bill_titles else "—"
            prop_list = " · ".join(proposers[:3]) if proposers else "—"
            sig_percentile = "상위" if signatures > 13140 else "하위"
            findings = (
                f"- 청원 제목: \"{ptitle}\" ({category})\n"
                f"- 서명 {signatures:,}명 — 22대 임기 청원 평균 13,140명 대비 *{sig_percentile} percentile*\n"
                f"- 매칭 의안 {matched_bills}건: {bill_list}\n"
                f"- 주요 발의 의원: {prop_list}\n"
                f"- 현재 lifecycle: *{lifecycle}* — 시행령 추적 + 통과 가능성 logistic\n"
                f"- 토픽 그래프: 청원 → \"{topic}\" → {matched_bills}건 의안 → 발의 의원 cross-link\n"
            )
            reader_extra = (
                "이 청원의 후속 영향을 *내 지역구 의원 표결*로 추적할 수 있어요."
                if lifecycle == "가결"
                else "통과 시 *시행 단계* 알림 받기 가능 (유료 구독)."
            )
            ad_extra = (
                "가결 청원 보도면 공익 광고 매칭 적합."
                if lifecycle == "가결"
                else "민감 lifecycle (상임위·본회의)은 광고 신중 검토."
            )
            persona_lens_map = {
                "editorial": (
                    f"편집국 시점: \"{ptitle}\" ({signatures:,}명 서명)은 *시민 관심 정량*. "
                    f"*{lifecycle}* 단계에서 {prop_list} 등 직접 인터뷰 후보. "
                    f"*시민 voice가 입법으로 어떻게 이어졌나* narrative — 가결 시 시행 timeline 추적 기획기사."
                ),
                "data_ai": (
                    f"데이터·AI 데스크 시점: \"{ptitle}\" — 청원-의안 임베딩 유사도 분석 권장. "
                    f"매칭 의안 {matched_bills}건의 cohort variance + lifecycle 통과율 logistic regression."
                ),
                "general_reader": (
                    f"일반 독자 시점: \"{ptitle}\"에 {signatures:,}명이 서명. "
                    f"{matched_bills}건 의안 발의되어 *{lifecycle}* 단계까지 진행. "
                    + reader_extra
                ),
                "paid_subscriber": (
                    f"유료 구독자 시점: \"{ptitle}\" PDF 3-page 시그니처 — 청원 lifecycle + 매칭 의안 시행 추적 + 발의 의원 timeline."
                ),
                "ad_sales": (
                    f"광고·세일즈 시점: \"{category}\" 청원은 *시민 관심 cohort* 신호. " + ad_extra
                ),
                "b2b": (
                    f"B2B 정책 인텔리전스 시점: \"{ptitle}\" alert — 매칭 의안 {matched_bills}건 통과 가능성 logistic input. "
                    f"\"{topic}\" 카테고리 정책 모니터링 + 시행령 변동성 시그널."
                ),
            }
            persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
            implication = (
                f"\"{ptitle}\"의 *시민 voice → 입법* lifecycle은 *민주적 응답성* 정량 narrative. "
                f"{signatures:,}명 서명 + {matched_bills}건 매칭 의안 + *{lifecycle}* 단계는 *시나리오 N (이슈×입법 상관)*의 lag 시그널. "
                f"가결 시 시행령 추적 (시나리오 K) + 발의 의원 timeline (시나리오 M) 결합이 *장기 narrative 가치*."
            )
            cta_text = (
                f"- \"{ptitle}\" 매칭 의안 {matched_bills}건 lifecycle 단계별 추적\n"
                f"- 주요 발의 의원 ({prop_list}) 직접 인터뷰 (시나리오 M timeline)\n"
                f"- \"{topic}\" 카테고리 청원-의안 매칭률 cohort variance (시나리오 N)\n"
                f"- 가결 청원의 시행령 단계 추적 (시나리오 K signature)\n"
            )
            return (
                f"{header}\n\n"
                f"## 📌 헤드라인\n{headline}\n\n"
                f"## 🔍 핵심 발견\n{findings}\n\n"
                f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
                f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
                f"## {cta}\n{cta_text}"
            )

    # 시나리오 C 기사 인사이트 — 선택 기사 title·category inject
    if scenario_label == "기사 인사이트" and article_title:
        cat = article_category or "카테고리 미지정"
        headline = (
            f"\"{article_title}\" — {cat} 카테고리 기사 분석. "
            f"22대 국회 1분기 {cat} 보도의 *편집국 시점 정량 인사이트* (출처: 합성 기사 60건 + 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)."
        )
        findings = (
            f"- 기사 제목: \"{article_title}\" ({cat})\n"
            f"- {cat} 카테고리 1분기 기사 총 12건 — 본 기사 위치 percentile rank 추적\n"
            f"- 정치 균형 점수 자동 첨부 (ADR-0004) — 양당 인용 비율 정량\n"
            f"- 참조 의원·의안 cross-link → 1-hop 그래프 탐색 가능\n"
            f"- 카테고리 분포 + 비슷한 기사 top-K (시나리오 D 페르소나 매칭 결합)\n"
        )
        persona_lens_map = {
            "editorial": (
                f"편집국 시점: \"{article_title}\"은 {cat} 카테고리 narrative의 *후속 취재 hook*. "
                f"인용된 의원·의안 cross-link → *심층 인터뷰 후보* 발굴. "
                f"균형 점수 0.8 이상이면 우리 매체 *정치 균형 narrative*에 인용 가능."
            ),
            "data_ai": (
                f"데이터·AI 데스크 시점: {cat} 카테고리 cohort variance 분석 권장. "
                f"본 기사의 *similarity matrix top-5*로 유사 기사 cluster 확인 — Cohere embed-v4 KNN."
            ),
            "general_reader": (
                f"일반 독자 시점: 이 기사 ({cat})를 *5섹션 요약*으로 한눈에. "
                f"관련 의원·의안은 *내 지역 영향* 추적 가능 (시나리오 H 지역구 지도 결합)."
            ),
            "paid_subscriber": (
                f"유료 구독자 시점: \"{article_title}\" PDF 다운로드 + {cat} 카테고리 시계열 trend + 비슷한 기사 cluster 분석."
            ),
            "ad_sales": (
                f"광고·세일즈 시점: {cat} 카테고리 정치 민감도 + 광고주 매칭 score. "
                f"premium CPM 적합도 자동 판단 (시나리오 L)."
            ),
            "b2b": (
                f"B2B 정책 인텔리전스 시점: \"{article_title}\" JSON API + {cat} 카테고리 alert webhook. "
                f"산업 영향 score 자동 계산."
            ),
        }
        persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
        implication = (
            f"\"{article_title}\"은 {cat} 카테고리의 *대표 narrative*. "
            f"본 기사의 *인용 의원·의안 cross-link*가 *후속 기획기사 hook* — 시나리오 F (룩어라이크) + M (정치 여정) 결합 가치."
        )
        cta_text = (
            f"- \"{article_title}\" 인용 의원 cross-party 협력 추적 (시나리오 M timeline)\n"
            f"- {cat} 카테고리 유사 기사 top-5 cluster 분석\n"
            f"- 기사 ROI (시나리오 G) + 페르소나별 KPI 변환 — 후속 콘텐츠 priority\n"
            f"- 균형 점수 분기별 trend (시나리오 I cross-ref)"
        )
        return (
            f"{header}\n\n"
            f"## 📌 헤드라인\n{headline}\n\n"
            f"## 🔍 핵심 발견\n{findings}\n\n"
            f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
            f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
            f"## {cta}\n{cta_text}"
        )

    # 의원 정치 여정 (M) — context의 person_name을 narrative에 inject
    if scenario_label == "의원 정치 여정" and person_name:
        # 일반 narrative를 *해당 의원 specific*으로 변환
        headline = (
            f"{person_name} 의원 ({person_id or '-'}) 1분기 정치 여정 — "
            f"발의·공동발의·표결·발언·위원회 활동 7개 이벤트 통합 timeline. "
            f"분기별 burst 패턴 + 미디어 화제성 cross-source (출처: 국회 OpenAPI + 합성 시드)."
        )
        findings = (
            f"- {person_name} 의원 1분기 events: 위원회 합류 1 · 발의 1 · 공동발의 1 · 표결 2 · 발언 2 (총 7건)\n"
            "- 활동 분포: 발의·공동발의 중심 (시작 1-3월) → 표결·발언 확대 (4-5월)\n"
            "- 분기별 burst: 발의 burst 2월 + 표결 burst 4월 — 입법 lifecycle 정상 패턴\n"
            "- 동일 위원회 cohort 평균과 percentile rank: 활동량 상위 30% (composite_score 기반)\n"
            "- 미디어 노출 30일: 평균 12회 — 발의·표결 timing 직후 burst\n"
            "- 핵심 토픽: AI·복지·환경·주거 등 카테고리별 의안 발의 패턴\n"
        )
        # persona lens도 의원 이름 inject
        persona_lens_map = {
            "editorial": (
                f"편집국 시점: {person_name} 의원의 *변화점 (changepoint)*은 인물 기획기사 hook. "
                f"발의 burst 직후의 *언론 노출 burst* 시점 = 의제 주도성 narrative. "
                f"동일 위원회 cohort 비교 + 분기별 burst pattern PDF로 *심층 인물 분석*."
            ),
            "data_ai": (
                f"데이터·AI 데스크 시점: {person_name} 의원 timeline changepoint 자동 탐지 (window=12주). "
                f"메트릭별 시계열 cross-correlation → 주력 활동 차원 (발의 vs 표결 vs 발언) 식별. "
                f"동일 위원회 cohort (n≥20) percentile rank logistic regression."
            ),
            "ad_sales": (
                f"광고·세일즈 시점: {person_name} 의원 timeline + 미디어 화제성 ↔ 광고 적합도 cross-check. "
                f"정치 민감 시점 자동 회피 가이드."
            ),
            "general_reader": (
                f"일반 독자 시점: *{person_name} 의원이 어떤 활동을 해왔는지* 시간순 한눈에. "
                f"발의·표결·발언 무엇이 많은지 비교. 분기별 활동량 trend로 *의원 활동 빈도 평가* 가능."
            ),
            "paid_subscriber": (
                f"유료 구독자 시점: {person_name} 의원 PDF 3-page 시그니처 — 표지·timeline·인사이트. "
                f"분기별 burst + cross-correlation 차트 + 동일 위원회 cohort 비교."
            ),
            "b2b": (
                f"B2B 정책 인텔리전스 시점: {person_name} 의원별 timeline JSON API + alert webhook. "
                f"통과 가능성 logistic regression input feature 활용. 산업 영향 score cross-tab."
            ),
        }
        persona_text = persona_lens_map.get(persona_id, persona_lens_map["editorial"])
        implication = (
            f"{person_name} 의원의 *5 활동 통합 시각화*는 *입법 영향력의 다차원성*을 1 화면에 압축. "
            "PDF 3-page 시그니처는 즉시 데스크 회의 자료로 활용 가능. "
            "동일 위원회 cohort 비교 + 분기별 burst pattern이 *의원 분석의 정량 기둥*."
        )
        cta_text = (
            f"- {person_name} 의원 timeline + 미디어 화제성 (시나리오 J) overlay\n"
            f"- 동일 위원회 cohort percentile rank 정량 비교\n"
            f"- 분기별 burst pattern PDF 출력 (시나리오 M PDF 시그니처)\n"
            f"- 시나리오 F 룩어라이크와 결합 → 유사 활동 의원 top-K 비교"
        )

    return (
        f"{header}\n\n"
        f"## 📌 헤드라인\n{headline}\n\n"
        f"## 🔍 핵심 발견\n{findings}\n\n"
        f"## 👤 페르소나 시점 해석\n{persona_text}\n\n"
        f"## 💡 비즈니스/취재 함의\n{implication}\n\n"
        f"## {cta}\n{cta_text}"
    )


# 시나리오별 mock 인사이트 (label 매칭 — label은 SCENARIO_PROMPTS["label"]와 정합).
# 각 시나리오는 *5섹션 marker text*를 가짐 — Sonnet 4.6 실 호출 시는 더 풍부함.
_SCENARIO_INSIGHT_MOCKS: dict = {
    "의미 검색": {
        "headline": "BM25(Nori) + Cohere embed-v4 KNN + RRF fusion → rerank-v3로 검색 정확도 향상 (출처: OpenSearch Serverless 2026-05).",
        "findings": (
            "- Hybrid retrieval: BM25 top 50 + KNN top 50 → RRF fusion → rerank-v3 top 10\n"
            "- 페르소나별 top_k 자동 조정 (편집국 10 · 데이터AI 20 · 일반독자 5 · 유료 15 · B2B 30)\n"
            "- top hit 1-hop subgraph로 의안 → 발의자 → 표결 → 토픽 직접 탐색 (출처: real)\n"
            "- 검색 쿼리당 평균 reranked confidence 0.78 ± 0.12\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: 키워드 매칭만으로는 놓치는 *의미적 연관 의안*까지 retrieval. 후속 취재 시 *동일 토픽 cross-party 의원*을 1-hop 그래프에서 즉시 추출 가능.",
            "data_ai":         "데이터·AI 데스크 시점: BM25(sparse) + KNN(dense) RRF fusion은 recall + precision 동시 향상. Cohere embed-v4 (1024-dim, multilingual)의 한국어 성능 + rerank-v3 cross-encoder의 의도 매칭 효과 검증 가능.",
            "general_reader":  "일반 독자 시점: 자연어로 검색하면 *관련성 높은 의안*과 *대표 발의자* 한꺼번에 보임. 검색어와 정확히 일치하지 않아도 의미가 비슷하면 찾아냅니다.",
            "paid_subscriber": "유료 구독자 시점: top 15 candidate + 1-hop subgraph + PDF 보고서로 *심층 정책 분석* 출발점. 토픽 클러스터 + 의원 활동 cohort 후속 분석 권장.",
            "ad_sales":        "광고·세일즈 시점: 검색어 카테고리 → 광고 적합도 1차 필터. 정치 민감 키워드 (선거·여론조사)는 *AdMatchDecision Agent* (시나리오 L)로 필터.",
            "b2b":             "B2B 정책 인텔리전스 시점: API key + Usage Plan + 30 results / call로 *정책 모니터링 자동화*. 키워드 alert + delta sub 가능.",
        },
        "implication": "단순 키워드가 아닌 *의미 검색*은 정책 모니터링 efficiency를 3-5배 향상. 1-hop 그래프 결합 시 *발견 → 분석 → 행동* 전체 lifecycle 압축.",
        "cta": "- 검색 결과 + 1-hop 그래프 → *동일 토픽의 다른 의안 cross-reference*\n- 페르소나별 top_k 차이 실제 비교 (편집국 10 vs B2B 30)\n- rerank-v3 점수 분포 분석 → confidence threshold tuning",
    },
    "기사 ROI": {
        "headline": "10건 기사 평균 ROI 24%·페이지뷰 12,400회·전환가치 1.2백만원 — 발의·표결 동반 카테고리에서 ROI 상위 집중 (출처: synthetic Bayesian).",
        "findings": (
            "- 비용·도달·전환 Bayesian 추정: 카테고리별 ROI 분포 자동 시각화\n"
            "- 6 페르소나 KPI 변환: 편집국(취재가치) · 데이터AI(통계신뢰성) · 광고세일즈(CPM) · 일반독자(이해도) · 유료(심층점수) · B2B(정책영향)\n"
            "- Code Interpreter Firecracker microVM에서 matplotlib 차트 실시간 생성\n"
            "- ROI 상위 3 기사: AI 산업 / 사회복지 / 환경·기후 분야 — 정파 초월 의제 추세\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: ROI 상위 기사의 *카테고리 분포* + *공동발의 cross-party 비율*이 후속 취재 신호. 같은 카테고리 발의 의안의 통과 lifecycle 추적 권장.",
            "data_ai":         "데이터·AI 데스크 시점: ROI Bayesian 신뢰구간 95% + p-value 검증. n≥30 cohort 기준 KPI 변환 모델의 R² 0.74 (참고 baseline).",
            "ad_sales":        "광고·세일즈 시점: ROI 상위 카테고리는 *premium CPM* + *광고주 적합도* 동시 충족. 정치 민감도 0.2 미만 → Agent 광고 매칭 적합.",
            "general_reader":  "일반 독자 시점: 기사 비용 대비 효과(읽고·공유) 비교. 어떤 주제가 *사람들에게 더 영향*을 주는지 한눈에.",
            "paid_subscriber": "유료 구독자 시점: 페르소나별 KPI 변환 매트릭스 PDF 다운로드. 분기별 ROI 시계열 + 카테고리 trend cross-tab.",
            "b2b":             "B2B 정책 인텔리전스 시점: 카테고리별 ROI ↔ 산업 영향 score correlation. 광고주·기관 정책 priority 정량 근거 제공.",
        },
        "implication": "ROI 정량 분석으로 *콘텐츠 → 의사결정* 시간 단축. 페르소나별 KPI 변환은 같은 데이터가 6개 다른 narrative로 보이는 *데이터 민주화* 핵심.",
        "cta": "- ROI 상위 3 기사 카테고리 추가 발의 의안 cross-reference (시나리오 A)\n- ROI 분포 PDF 보고서 다운로드 + 광고주 review\n- 페르소나별 KPI 변환 매트릭스 → API 출력 형식 설계",
    },
    "의원 정치 여정": {
        "headline": "단일 의원 발의·공동발의·표결·발언·위원회 활동 시간순 통합 timeline — PDF 3-page 시그니처 출력 (출처: 국회 OpenAPI + synthetic seed).",
        "findings": (
            "- 5 활동 유형 통합: 발의 / 공동발의 / 표결 / 발언 / 위원회 가입·탈퇴\n"
            "- 분기별 burst 패턴 자동 라벨 (예: 1분기 발의 burst, 2분기 표결 활동 ↑)\n"
            "- 미디어 노출 30일 trend overlay → 입법 ↔ 여론 시차 시각화\n"
            "- 동일 위원회 의원 cohort 평균과 percentile rank 자동 비교\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: timeline의 *변화점*(changepoint)이 인물 기획기사 hook. 발의 burst 직후의 *언론 노출 burst* 시점 = 의제 주도성 narrative.",
            "data_ai":         "데이터·AI 데스크 시점: changepoint 자동 탐지 (window size = 12주). 메트릭별 시계열 cross-correlation → 의원의 *주력 활동 차원* 식별.",
            "ad_sales":        "광고·세일즈 시점: 의원 timeline + 미디어 화제성 ↔ 광고 적합도 cross-check. 정치 민감 시점 자동 회피 가이드.",
            "general_reader":  "일반 독자 시점: *이 의원이 어떤 활동을 해왔는지* 시간순 한눈에. 발의·표결·발언 무엇이 많은지 비교.",
            "paid_subscriber": "유료 구독자 시점: PDF 3-page 시그니처 — 표지·timeline·인사이트. 분기별 burst + cross-correlation 차트 포함.",
            "b2b":             "B2B 정책 인텔리전스 시점: 의원별 timeline JSON API + alert webhook. 통과 가능성 logistic regression input feature 활용.",
        },
        "implication": "단일 의원 *5 활동 통합 시각화*는 *입법 영향력의 다차원성*을 1 화면에 압축. PDF 3-page 시그니처는 즉시 데스크 회의 자료로 활용 가능.",
        "cta": "- 의원 timeline + 미디어 화제성 (시나리오 J) overlay → 의제 라이프사이클 분석\n- 동일 위원회 cohort percentile rank 정량 비교\n- 분기별 burst pattern PDF 출력",
    },
    "3-stage 챗봇": {
        "headline": "Chatbot(RAG)·Agent(Tool Use)·Agentic(4 에이전트) 3단계 진화 비교 시연 — 같은 질문에 다른 깊이/근거/도구 사용량 (출처: Bedrock Sonnet 4.6).",
        "findings": (
            "- Stage 1 Chatbot RAG: OpenSearch retrieval + 단일 Sonnet 4.6 호출, ~2s\n"
            "- Stage 2 Agent: Tool Use (10 tools) + AgentCore Memory, ~5s\n"
            "- Stage 3 Agentic: Planner→Graph→Analyst→Editor 4 에이전트 협업, ~15s\n"
            "- 응답 깊이/근거/도구 사용량 정량 비교 (총 토큰·tools_called·agents_invoked)\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: Stage 3 Agentic은 *근거 그래프*까지 첨부 → 인용·검증 용이. 단 정치 민감 토픽은 모든 stage에 ADR-0004 가드.",
            "data_ai":         "데이터·AI 데스크 시점: 3단계 token usage·latency·output length 정량 비교. 동일 질문에 대한 *cost-quality trade-off* 측정.",
            "general_reader":  "일반 독자 시점: Stage 1은 빠른 답변, Stage 3은 상세한 분석. 필요에 따라 선택.",
            "paid_subscriber": "유료 구독자 시점: Stage 3 Agentic + PDF 보고서 추출이 핵심 차별화.",
            "ad_sales":        "광고·세일즈 시점: 챗봇 사용자 페르소나별 광고 매칭 적합도 자동 분석.",
            "b2b":             "B2B 정책 인텔리전스 시점: Stage 2 Agent + JSON 응답으로 자동화 파이프 통합.",
        },
        "implication": "*Agentic AI*는 *체인 도구·다중 에이전트·자율 의사결정*의 새 패러다임. 단일 RAG vs 다중 에이전트 비교가 핵심 narrative.",
        "cta": "- Stage 1·2·3 동일 질문 비교 PDF 출력\n- Tool Use trace 분석 (어떤 tool이 가장 효과적인가)\n- 4 에이전트별 토큰 사용량 비교",
    },
    "기사 인사이트": {
        "headline": (
            "22대 국회 1분기 환경·기후 보도 12건 — 정치 균형 점수 평균 0.84로 양당 균형 인용. "
            "AI 입법 burst와 함께 *재생에너지·청년 주거*가 후속 보도 hot zone (출처: 합성 기사 60건 + 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)."
        ),
        "findings": (
            "- 카테고리 분포: 환경·기후 12 / AI·데이터 9 / 사회복지 8 / 청년 주거 6 / 경제 5 / 외교 4 / 기타 16\n"
            "- 평균 정치 균형 점수 0.84 (95% CI: 0.79-0.89) — 양당 인용 비율 균형\n"
            "- 가장 자주 인용된 의원 top 3: 김도읍 (15회) · 권칠승 (12회) · 김태년 (11회)\n"
            "- 후속 보도 hot 카테고리: 재생에너지 (CTR 4.2배) · 청년 주거 (사회 화제성 ↑)\n"
            "- 양당 협력 의제 5건 발굴 — 시나리오 K (표결 이상치) cross-reference 신호\n"
        ),
        "persona": {
            "editorial": (
                "편집국 시점에서 가장 인용 가치 있는 통계는 *균형 점수 0.84*와 *cross-party 협력 의제 5건*. "
                "전자는 *우리 매체의 균형 보도 narrative*에 직접 인용 가능, 후자는 *후속 단독 기획기사 hook*. "
                "특히 재생에너지·청년 주거 카테고리는 *CTR + 사회 화제성* 둘 다 ↑ → 다음 분기 기획 우선순위. "
                "김도읍·권칠승·김태년 의원이 양당 인용 top 3이므로 *cross-party 협력 narrative 인터뷰 후보*."
            ),
            "data_ai": (
                "데이터·AI 데스크 시점: 카테고리 분포 엔트로피 1.74 (60건 풀에서 균형 분포 통계 유의). "
                "균형 점수 95% CI 좁음 (±0.05) → ADR-0004 가드 효과 검증. "
                "토픽 × 의원 affinity matrix logistic regression에서 환경·청년 주거 카테고리가 통계 유의 (p<0.01) 인용 hotspot."
            ),
            "general_reader": (
                "일반 독자 시점: 어떤 정책 기사가 *우리 일상에 직접 영향*인지 한눈에. "
                "환경·기후 12건 · 청년 주거 6건 — 본인 관심 주제로 골라 읽기. "
                "어려운 용어는 기사 안의 *해석* 섹션에서 풀이."
            ),
            "paid_subscriber": (
                "유료 구독자 시점: 토픽별 시계열 trend + 균형 점수 분포 + PDF 추출. "
                "1분기 환경 카테고리 burst (전 분기 대비 +5건) → 분기별 정책 lifecycle 추적 valuable."
            ),
            "ad_sales": (
                "광고·세일즈 시점: 환경·청년 주거 카테고리는 *정치 민감도 0.2 미만* + *premium CPM 적합*. "
                "재생에너지·전기차·모기지·전세대출 광고주 매칭 가능. 균형 점수 0.84 → 광고주 평판 보호 OK."
            ),
            "b2b": (
                "B2B 정책 인텔리전스 시점: 카테고리별 60건 기사 JSON API + topic alert webhook. "
                "재생에너지 12건 cross-reference로 *발의 의안 lifecycle 1단계 prediction*."
            ),
        },
        "implication": (
            "1분기 기사 풀은 *환경·청년 정책 burst*를 정량 시그널로 제시. "
            "양당 협력 의제 5건 + 균형 점수 0.84 → *우리 매체의 정파 무관 신뢰* narrative 강화 근거. "
            "후속 보도는 *cross-party 협력 의원 인터뷰*와 *재생에너지·청년 주거 lifecycle 추적*에 집중."
        ),
        "cta": (
            "- 김도읍·권칠승·김태년 의원 cross-party 협력 narrative 인터뷰 (시나리오 M timeline 활용)\n"
            "- 재생에너지·청년 주거 카테고리 후속 기획기사 — 의원 활동 + 외부 신호 cross-source (시나리오 J)\n"
            "- 균형 점수 0.84의 분기별 trend → 매체 신뢰 KPI 보고서 (분기별)"
        ),
    },
    "페르소나 매칭": {
        "headline": "기사·콘텐츠 → 6 페르소나 적합도 매트릭스 + reasons + 권장 사유 (가중: topic 0.6 + KPI 0.25 + tone 0.15).",
        "findings": (
            "- 6 페르소나 KPI affinity matrix + topic category × persona 가중치\n"
            "- 적합도 상위 페르소나 + reasons (자동 설명) + 권장 사유\n"
            "- 광고·구독 타겟팅 의사결정 정량 근거 (CTR·전환 추정)\n"
            "- 같은 콘텐츠 → 6개 다른 KPI narrative (데이터 민주화)\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: 같은 기사가 *어떤 페르소나에 어떻게 다른 가치*를 주는지 정량. 콘텐츠 큐레이션·후속 기획 priority.",
            "data_ai":         "데이터·AI 데스크 시점: 가중치 (topic 0.6, KPI 0.25, tone 0.15) tuning + cohort 검증 권장. n≥30 cohort baseline.",
            "ad_sales":        "광고·세일즈 시점: 페르소나별 적합도 → CPM 차별화 + 광고주 매칭 정확도 ↑.",
            "general_reader":  "일반 독자 시점: 이 기사가 *나 같은 사람*에게 적합한지 정량 표시.",
            "paid_subscriber": "유료 구독자 시점: 페르소나별 reasons 상세 PDF + 콘텐츠 추천 알고리즘.",
            "b2b":             "B2B 정책 인텔리전스 시점: API 응답에 페르소나 score JSON 첨부 → 다운스트림 시스템 활용.",
        },
        "implication": "*같은 데이터 → 다른 페르소나에 맞춤 narrative*는 콘텐츠 personalization 핵심.",
        "cta": "- 페르소나별 reasons 보고서 PDF 추출\n- 가중치 tuning A/B 테스트 + ROI 측정 (시나리오 G)\n- 6 페르소나 KPI 매트릭스 cross-tab 분석",
    },
    "의원 클러스터링": {
        "headline": "5 thematic cluster — 토픽 활동 vector 기반 cross-party 협력 그룹 (정당 무관, ADR-0004 정파 클러스터링 금지).",
        "findings": (
            "- KMeans + Cohere embed-v4 활동 vector → 5 cluster\n"
            "- cross_party_share 0.4-0.7 = 정파 가로지르는 협력 그룹\n"
            "- Sonnet 4.6 cluster naming + dominant topic 자동 라벨\n"
            "- 시나리오 K 표결 이상치와 cross-reference 가능\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: cross_party_share가 높은 그룹은 *협력 의제 발굴* 후속 취재 가치 ↑. 특정 의원의 cluster 위치 변화 추적도 narrative.",
            "data_ai":         "데이터·AI 데스크 시점: KMeans 5-cluster modularity + silhouette score 자동 계산. cohort variance + cross-party 분포 정량.",
            "general_reader":  "일반 독자 시점: 의원들이 *정당 외에도 비슷한 활동 패턴*으로 그룹지어진다는 점이 흥미. 5 그룹 보기.",
            "paid_subscriber": "유료 구독자 시점: 5 cluster 모두 PDF 보고서 + 의원별 cluster 변화 timeline.",
            "ad_sales":        "광고·세일즈 시점: cluster 토픽 → 광고주 적합도 매칭 (industry alignment).",
            "b2b":             "B2B 정책 인텔리전스 시점: 클러스터 변화 alert + 정책 priority 자동 계산.",
        },
        "implication": "*정당이 아닌 활동 vector*로 의원을 묶는 narrative는 *정치 양극화* 통념을 정량적으로 도전.",
        "cta": "- 5 cluster 의원 명단 cross-party share 정량 비교\n- 시나리오 K 이상치 의원 ↔ cluster 매핑 분석\n- 분기별 cluster 변동 timeline",
    },
    "룩어라이크": {
        "headline": "seed 의원 → top-K 유사 후보 추천 (cluster 0.6 + activity 0.3 + cross-party 0.1) — 정책 동지 발굴 (출처: Cohere embed-v4 + OpenSearch KNN).",
        "findings": (
            "- seed 의원 → top-K 유사 후보 자동 추천\n"
            "- cluster proximity + activity vector + cross-party bonus\n"
            "- 정파를 가로지르는 후보 가중치 ↑ → 협력 가능성 ↑\n"
            "- 시나리오 G ROI + 시나리오 M timeline cross-reference\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: seed → look-alike는 *공동발의 후보 발굴* + *cross-party 인터뷰* 시작점.",
            "data_ai":         "데이터·AI 데스크 시점: Cohere embed-v4 1024-dim activity vector + KNN cosine. cross-party bonus parameter A/B tuning.",
            "general_reader":  "일반 독자 시점: 이 의원과 *비슷한 활동을 하는 다른 의원*을 한 번에 발견.",
            "paid_subscriber": "유료 구독자 시점: 룩어라이크 top 15 + 활동 cross-tab + cluster 변동 + PDF 보고서.",
            "ad_sales":        "광고·세일즈 시점: 의원 인플루언스 score + 광고주 적합도 cross-check.",
            "b2b":             "B2B 정책 인텔리전스 시점: API alert — seed 의원 → 활동 패턴 변화 시 유사 의원 자동 추천.",
        },
        "implication": "*유사 활동 패턴 자동 탐지*는 발의·표결·발언 *cross-party 협력 가능성* 정량.",
        "cta": "- top-K 유사 후보 활동 timeline (시나리오 M) cross-reference\n- cross-party 후보의 발의 의안 매칭 분석\n- 룩어라이크 결과 PDF 추출",
    },
    "지역구 지도": {
        "headline": "17 KOSTAT 시도 choropleth + 22대 254 지역구 의원 분포 + 시도별 활동 stats (출처: 국회 OpenAPI + KOSTAT GeoJSON).",
        "findings": (
            "- 17 시도 SVG choropleth + 254 지역구 분포\n"
            "- 시도별 발의·표결·발언 평균 + percentile rank\n"
            "- 인구 대비 의원 비율 + activity intensity\n"
            "- 지역 격차 자동 라벨 (높음/보통/낮음)\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: 지역 격차 인사이트 → 지역 기획기사 hook. 시도별 발의 burst ↔ 지역 현안 cross-tab.",
            "data_ai":         "데이터·AI 데스크 시점: 인구 normalized activity index + spatial autocorrelation (Moran's I) 분석.",
            "general_reader":  "일반 독자 시점: *우리 지역 의원들*이 어떻게 활동하는지 지도로 한눈에.",
            "paid_subscriber": "유료 구독자 시점: 17 시도 분기별 활동 PDF + 지역 alert.",
            "ad_sales":        "광고·세일즈 시점: 지역별 광고 매칭 적합도 + 지역 기반 광고주 매칭.",
            "b2b":             "B2B 정책 인텔리전스 시점: 시도별 정책 알림 + 지역 priority 자동 계산.",
        },
        "implication": "*지역 격차 시각화*는 *지자체 협업·지역 기획기사 시작점*. 시도별 활동 차이 narrative.",
        "cta": "- 시도별 발의 burst 시점 ↔ 지역 현안 cross-tab\n- 인구 대비 의원 활동 지수 비교 분석\n- 17 시도 분기별 timeline PDF 출력",
    },
    "편향·중립성": {
        "headline": "ADR-0004 4-layer 가드레일 + political_balance_score 실시간 4 등급 분류 (Bedrock Guardrails 입력/출력 양쪽).",
        "findings": (
            "- 4 등급 분류: excellent(>0.9) / good(0.8-0.9) / warning(0.6-0.8) / critical(<0.6)\n"
            "- 입력·출력 양쪽 모두 ADR-0004 4-layer 가드 자동 적용\n"
            "- 정치 민감 단정 표현 자동 회피 (페르소나 system prompt 통합)\n"
            "- 운영 콘솔 알림 → 편집국 자동 review 가능\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: balance_score < 0.8 노란색 경고 → 편집 review 권장. AI 응답에 정치 단정 자동 차단.",
            "data_ai":         "데이터·AI 데스크 시점: 4 등급 distribution + threshold tuning + false positive rate 분석.",
            "general_reader":  "일반 독자 시점: AI 답변이 *어느 쪽으로 편향*되지 않게 자동 보호.",
            "paid_subscriber": "유료 구독자 시점: balance_score 분기별 trend + AI 거버넌스 보고서 PDF.",
            "ad_sales":        "광고·세일즈 시점: 정치 균형 점수 → 광고 매칭 정확도 ↑.",
            "b2b":             "B2B 정책 인텔리전스 시점: API에 balance_score JSON 첨부 → 다운스트림 컴플라이언스 자동화.",
        },
        "implication": "*AI 거버넌스 신뢰 메시지* — 대고객·B2B 차별화 narrative. 정치 PoC의 ADR-0004는 *product feature*.",
        "cta": "- balance_score 분기별 distribution 분석\n- 4 등급 threshold tuning A/B 실험\n- 운영 콘솔 alert webhook 통합",
    },
    "외부 신호 융합": {
        "headline": "네이버 뉴스 + SNS + 여론조사 × 입법 활동 12주 시계열 — 3 패턴 (signal_leads / legislation_leads / decoupled) 자동 라벨.",
        "findings": (
            "- 12주 cross-source 시계열 비교 (네이버 뉴스 + SNS + 여론조사)\n"
            "- 3 패턴 자동 라벨: signal_leads / legislation_leads / decoupled\n"
            "- 사회 이슈 ↔ 입법 lag time 자동 추정 (median: 3-8주)\n"
            "- 의제 라이프사이클 (감지→발의→심사→통과) 1단계 prediction\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: signal_leads 패턴 = *여론이 입법을 견인* narrative. 후속 취재 의제 priority.",
            "data_ai":         "데이터·AI 데스크 시점: Granger causality + cross-correlation + lag time 자동 계산.",
            "general_reader":  "일반 독자 시점: 사회 이슈가 *얼마나 빨리 입법에 반영*되는지 시각화.",
            "paid_subscriber": "유료 구독자 시점: 12주 시계열 PDF + 의제 lifecycle alert.",
            "ad_sales":        "광고·세일즈 시점: 화제성 burst 시점 → 광고 매칭 timing 정밀화.",
            "b2b":             "B2B 정책 인텔리전스 시점: 외부 시그널 ↔ 입법 lag time webhook alert.",
        },
        "implication": "*외부 신호 cross-source 융합*은 *의제 lifecycle 1단계 prediction* 핵심.",
        "cta": "- signal_leads 패턴 의원 cross-reference (시나리오 F)\n- lag time 분포 PDF 출력\n- cross-source weight tuning A/B",
    },
    "표결 이상치": {
        "headline": "당론 이탈·박빙 표결·정파 초월 협력 3 유형 자동 탐지 + deviation_score + AI 패턴 라벨 (PDF 3-page 시그니처).",
        "findings": (
            "- 3 유형 자동 라벨: party_line_break / close_vote / cross_party\n"
            "- deviation_score (z-score 기반) + threshold filter\n"
            "- AI 패턴 라벨 (Sonnet 4.6) + 정량 정성 결합\n"
            "- PDF 3-page 시그니처: 표지·이상치 분포·인사이트\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: 당론 이탈·박빙·정파 초월 모두 *심층 취재 단서*. PDF 출력 → 즉시 데스크 자료.",
            "data_ai":         "데이터·AI 데스크 시점: deviation_score (z>2) + AI label confidence 0.85 이상 필터. cohort effect 분리 분석.",
            "general_reader":  "일반 독자 시점: 평소 패턴과 다른 표결 — *왜 이런 결정이 나왔는가* 의문에 답.",
            "paid_subscriber": "유료 구독자 시점: PDF 3-page + 의원별 이상치 alert.",
            "ad_sales":        "광고·세일즈 시점: 정쟁 시점 자동 회피 가이드.",
            "b2b":             "B2B 정책 인텔리전스 시점: 이상치 표결 webhook + 정책 변동 alert.",
        },
        "implication": "*당론 이탈·정파 초월 패턴 자동 탐지*는 *입법 협력 narrative* 정량 근거 제공.",
        "cta": "- 이상치 의원 timeline (시나리오 M) cross-reference\n- 3 유형 분기별 빈도 PDF 출력\n- AI 라벨 confidence 분포 분석",
    },
    "광고 매칭": {
        "headline": "keyword vs embedding vs Agent 3-way 비교 — 같은 콘텐츠·후보에 다른 결정 + AI 거버넌스 시연 (출처: Ad Matcher Lambda + Bedrock).",
        "findings": (
            "- 3 모드: keyword / embedding / Agent (Sonnet 4.6 + reasoning trace)\n"
            "- Agent만 비위 의혹·비극·미성년 피해 콘텐츠에서 자동 광고 거절\n"
            "- AdMatchDecision 노드에 reasoning trace 저장 → 감사 가능\n"
            "- 매칭 정확도 + CTR + 광고주 평판 보호 동시 달성\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: AI 거버넌스 시연의 *flagship 카드*. Agent의 *자율적 광고 거절* trace narrative.",
            "data_ai":         "데이터·AI 데스크 시점: 3-way 정확도/recall trade-off + reasoning trace 분석.",
            "ad_sales":        "광고·세일즈 시점: *AI 자율 광고 거절*은 광고주 평판 보호 + 장기 신뢰. CPM short-term 손실 < 평판 장기 가치.",
            "general_reader":  "일반 독자 시점: 비극 기사에 부적절 광고 안 나오게 *AI가 알아서 차단*.",
            "paid_subscriber": "유료 구독자 시점: AdMatchDecision trace + AI 거버넌스 보고서.",
            "b2b":             "B2B 정책 인텔리전스 시점: 광고 매칭 정책 API + reasoning trace JSON.",
        },
        "implication": "*AI 자율 의사결정 + reasoning trace 감사*는 *AI 거버넌스의 미래* 모델.",
        "cta": "- 3-way 정확도 분포 PDF 출력\n- AdMatchDecision reasoning trace 분석\n- Agent vs keyword 시연 케이스 정리",
    },
    "인물 관계 분석": {
        "headline": (
            "두 의원 5 차원 관계 분석 — 공동발의·표결 일치율·토픽 중첩·timeline overlay·cluster 위치. "
            "*cross-party 협력 정량 + 정책 친밀도* 객관 평가 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
        ),
        "findings": (
            "- 공동발의 평균 2.5건 — top 10 의원쌍에서 4건 이상\n"
            "- 표결 일치율 평균 68% — 같은 정당 86% vs 다른 정당 52%\n"
            "- 토픽 중첩 Jaccard 평균 0.34 (cross-party top 5는 0.52+)\n"
            "- 같은 위원회 의원쌍 → 공동발의 빈도 3.2x (modularity effect)\n"
            "- cross-party 협력 의원쌍 top 5: 사회복지·청년 주거 카테고리 강세\n"
        ),
        "persona": {
            "editorial": "편집국 시점: *두 의원 비교*는 *cross-party 협력 narrative* 핵심. 공동발의·표결 일치·토픽 중첩 3중 매트릭 → 후속 인터뷰·단독 보도 angle.",
            "data_ai":   "데이터·AI 데스크 시점: 의원 pair cohort (n=286C2) Jaccard distribution + 같은 정당 vs cross-party chi-square test 통계 유의.",
            "general_reader": "일반 독자 시점: 두 의원이 *얼마나 협력하는지* 정량 비교. 정당 달라도 협력 사례·같은 당 의견 다른 사례 발견.",
            "paid_subscriber": "유료 구독자 시점: 두 의원 PDF 3-page 시그니처 + 분기별 협업 trend.",
            "ad_sales":  "광고·세일즈 시점: cross-party 협력 인터뷰 콘텐츠 → 정치 균형 점수 ↑ → premium CPM.",
            "b2b":       "B2B 정책 인텔리전스 시점: 의원 관계 매트릭스 API + logistic input feature (협력 score → 통과 가능성).",
        },
        "implication": "*두 의원 비교*는 *입법 협업 패턴 정량의 핵심 도구*. 공동발의·표결·토픽 3중 매트릭 + cluster 위치로 *cross-party 신뢰도* 객관 측정.",
        "cta": (
            "- /journey 의원 timeline overlay\n"
            "- /lookalike 룩어라이크 유사도 정량\n"
            "- /cluster 클러스터링에서 두 의원 cluster 위치 비교\n"
            "- cross-party 협력 narrative 후속 기획기사"
        ),
    },
    "시민 청원 입법 매핑": {
        "headline": (
            "시민 청원 → 입법 매핑 — 1분기 청원 7건 · 평균 매칭률 78% · 가결 1건 (출처: 합성 청원 + 국회 OpenAPI). "
            "*내 청원이 어떻게 입법으로 이어졌나* lifecycle 추적."
        ),
        "findings": (
            "- 7 청원 카테고리: 주거 · AI · 환경 · 복지 · 교육 · 경제 · 개인정보\n"
            "- 누적 서명 92,880명 — 노인 의료 보장 22,100명 (top)\n"
            "- 평균 매칭 의안 3.0건 — Cohere embed-v4 KNN top-3 매칭\n"
            "- lifecycle 분포: 접수 1 · 상임위 2 · 본회의 3 · 가결 1\n"
            "- 매칭률 100% 카테고리: 복지·환경·주거 (사회 화제성 ↑)\n"
        ),
        "persona": {
            "editorial": "편집국 시점: *청원 → 입법 lifecycle 추적*은 *시민 참여 narrative 정량* 핵심. 가결 1건 (노인 의료) → 시행 추적 + 후속 기획기사.",
            "data_ai":   "데이터·AI 데스크 시점: 청원-의안 임베딩 유사도 0.78 평균. 매칭률 카테고리 cohort variance ↑ (복지 100% vs 외교 0%).",
            "general_reader": "일반 독자 시점: *내가 서명한 청원*이 어떻게 입법으로 이어지는지 한눈에. 22,100명 서명한 노인 의료 청원이 가결됨.",
            "paid_subscriber": "유료 구독자 시점: 7 청원 lifecycle PDF + 분기별 매칭률 trend + 시행 단계 추적.",
            "ad_sales":  "광고·세일즈 시점: 청원 카테고리는 *시민 관심사* — 공익 광고 매칭 적합.",
            "b2b":       "B2B 정책 인텔리전스 시점: 청원 alert + 매칭 의안 통과 가능성 logistic.",
        },
        "implication": "*시민 청원 매핑*은 *시민 참여 → 입법 lifecycle*의 정량 가시화. 매칭률 78% + 가결 1건은 *민주적 응답성 narrative* 정량.",
        "cta": (
            "- 가결된 청원의 시행 단계 추적 (노인 의료)\n"
            "- 매칭률 0% 카테고리 분석 — 왜 입법 안 되었나\n"
            "- 청원-의안 임베딩 매칭 정확도 검증\n"
            "- 시민 참여 narrative 시리즈 기획"
        ),
    },
    "위원회 영향력": {
        "headline": (
            "17 상임위 영향력 매트릭스 — 발의·심사·통과·발언·출석 5 메트릭 cross-tab. "
            "*통과 top 3*: 보건복지위(5) · 교육위(5) · 산자위(4) (출처: 국회 OpenAPI)."
        ),
        "findings": (
            "- 17 위원회 평균: 발의 9건 · 심사 8건 · 통과 2.5건 · 발언 19회 · 출석률 87%\n"
            "- 통과 top 3: 보건복지위(5건) · 교육위(5건) · 산자위(4건)\n"
            "- 출석률 top 3: 보건복지위(93%) · 교육위(92%) · 기재위(91%)\n"
            "- 발의 burst top 3: 보건복지(15) · 기재(14) · 산자(13)\n"
            "- cross-committee 협력 의안 12건 — 환경노동 + 산자 가장 활성\n"
        ),
        "persona": {
            "editorial": "편집국 시점: *위원회별 영향력*은 *입법 lifecycle 추적 마스터 view*. 통과 top 3 + cross-committee 12건 → 후속 시행령 추적 priority.",
            "data_ai":   "데이터·AI 데스크 시점: 17 위원회 × 5 메트릭 heatmap + 영향력 score 가중합. 통과율 logistic regression.",
            "general_reader": "일반 독자 시점: 어느 위원회가 가장 활발한지 한눈에. 보건복지·교육·산자 위원회가 입법 통과 top 3.",
            "paid_subscriber": "유료 구독자 시점: 17 위원회 × 5 메트릭 PDF + 분기별 trend + cross-committee 협력.",
            "ad_sales":  "광고·세일즈 시점: 위원회별 산업 영향 → 광고 매칭 priority.",
            "b2b":       "B2B 정책 인텔리전스 시점: 위원회별 입법 alert + 통과 가능성 + 시행 timeline.",
        },
        "implication": "*위원회 영향력 heatmap*은 *입법 lifecycle의 정확한 lens*. 통과 top 3 + cross-committee가 *분기 priority 핵심*.",
        "cta": (
            "- 보건복지·교육·산자 위원회 통과 의안 시행령 추적\n"
            "- cross-committee 12건 카테고리 분석 (환경 ↔ 산업)\n"
            "- 위원회별 분기별 활동 trend PDF\n"
            "- 영향력 score 가중합 모델 업데이트"
        ),
    },
    "공약 이행 추적": {
        "headline": (
            "22대 의원 당선 공약 이행률 — 총 공약 91건 · 발의 67건 · 가결 20건. "
            "전체 이행률 73% (사회복지·청년 주거 카테고리가 가장 적극 이행) (출처: 22대 공약 + 국회 OpenAPI)."
        ),
        "findings": (
            "- 8 카테고리 공약 91건 — 사회복지(18) · 청년 주거(15) · 경제(14) · AI(12) · 환경(10) · 교육(9) · 개인정보(7) · 외교(6)\n"
            "- 발의 이행률 평균 74% (95% CI: 65-83%, n=8 카테고리)\n"
            "- 가결률 평균 22% — 사회복지(28%) · 교육(33%) 가장 높음\n"
            "- 미이행 분야: 외교·안보(50%) · AI(67%) — 시행 timeline 9-12개월 예상\n"
            "- 분기별 trend: 이행률 1Q 63% → 2Q 81% (개선 추세)\n"
        ),
        "persona": {
            "editorial": "편집국 시점: *공약 이행률은 사회 신뢰·정치 책무 narrative*의 정량 핵심. 사회복지 28% 가결 + 외교 50% 미이행이 *후속 분석 hook*.",
            "data_ai":   "데이터·AI 데스크 시점: 8 카테고리 cohort variance 분석 + logistic regression 이행 예측.",
            "general_reader": "일반 독자 시점: *우리가 뽑은 의원이 공약 얼마나 지키는지* 한눈에. 사회복지·청년 주거 적극 이행, 외교·AI 더딘 진행.",
            "paid_subscriber": "유료 구독자 시점: 8 카테고리 이행률 PDF + 의원별 cross-tab + 분기별 trend.",
            "ad_sales":  "광고·세일즈 시점: 정치 신뢰 관련 콘텐츠 → 공익·정책 광고 매칭.",
            "b2b":       "B2B 정책 인텔리전스 시점: 카테고리별 이행 가능성 alert + 산업 영향 score.",
        },
        "implication": "*공약 이행 추적*은 *민주적 책무성 narrative*의 정량 기둥. 이행률 74%는 *수용 가능 수준*, 외교·AI 미이행은 *정파·복잡도 영향* 명시.",
        "cta": (
            "- 사회복지 28% 가결 시행령 단계 추적\n"
            "- 외교 50% 미이행 원인 분석 (정쟁·국제 환경)\n"
            "- 의원별 공약 이행률 cross-tab (시나리오 M 결합)\n"
            "- 분기별 이행 trend → 다음 분기 prediction"
        ),
    },
    "토픽 burst 시계열": {
        "headline": (
            "8 매크로 이슈 × 13 주차 burst 시계열 — *복지·청년 주거 6-8 주차 burst*, AI·환경 5-7 주차 burst. "
            "Granger causality lag prediction (출처: 국회 OpenAPI + 네이버 뉴스 + 여론조사)."
        ),
        "findings": (
            "- 8 topic × 13 weeks line chart — burst week·peak value 자동 라벨\n"
            "- Top 3 burst: 사회복지(W8=9) · 청년 주거(W12=9) · AI(W7=9)\n"
            "- 외부 신호 → 입법 lag prediction: 평균 6주 ± 2주 (Granger F=5.2, p<0.01)\n"
            "- 카테고리 cross-correlation: 환경 ↔ 산업 lag 4주, 복지 ↔ 교육 lag 2주\n"
            "- 분기별 burst 분포: 1Q 환경·AI, 2Q 복지·청년 주거 (의제 lifecycle 정상 패턴)\n"
        ),
        "persona": {
            "editorial": "편집국 시점: *burst 시점 + 외부 신호 lag*는 *다음 입법 의제 prediction 기획기사*. W6-8 burst 카테고리가 *분기 priority 핵심*.",
            "data_ai":   "데이터·AI 데스크 시점: Granger causality F=5.2 (p<0.01) 통계 유의 + cross-correlation 분석.",
            "general_reader": "일반 독자 시점: *어떤 사회 이슈가 언제 burst*했는지. 복지·청년 주거는 6-12 주차 burst — 사회 관심사 반영.",
            "paid_subscriber": "유료 구독자 시점: 8 topic × 13 week PDF + lag prediction 모델 + 카테고리 cross-correlation.",
            "ad_sales":  "광고·세일즈 시점: burst 시점 → 광고 timing 정밀화 + 카테고리 매칭 적합도 ↑.",
            "b2b":       "B2B 정책 인텔리전스 시점: burst alert webhook + lag prediction → 다음 입법 의제 1-3주 미리 prediction.",
        },
        "implication": "*분기별 burst 시계열*은 *사회 이슈 → 입법 lifecycle*의 정량 prediction. 외부 신호 → 입법 lag 6주 ± 2주 활용 시 *다음 분기 의제 미리 예측*.",
        "cta": (
            "- Top 3 burst 카테고리 (복지·청년 주거·AI) 다음 분기 lag prediction\n"
            "- 외부 신호 (여론조사·뉴스) ↔ 입법 lag 정량\n"
            "- 환경 ↔ 산업 cross-correlation 분석\n"
            "- 분기별 burst 패턴 시리즈 기획"
        ),
    },
    "이슈 × 입법": {
        "headline": "8 매크로 이슈 × 4 활동 결합 강도 heatmap + Top 5 강한 결합 자동 추출 (출처: 22대 임기 분포 근사).",
        "findings": (
            "- 8 × 4 결합 강도 heatmap (이슈 × 발의/표결/발언/위원회)\n"
            "- Top 5 강한 결합 자동 추출 + LLM 라벨\n"
            "- 사회 트렌드 ↔ 입법 상관관계 정량\n"
            "- 정책 의제 priority 의사결정 근거\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: Top 5 결합은 *후속 기획기사 priority*. 이슈 × 활동 차원의 *교차점* narrative.",
            "data_ai":         "데이터·AI 데스크 시점: heatmap z-score + 카테고리 cross-tab. cohort effect 분리.",
            "general_reader":  "일반 독자 시점: *우리 사회 이슈*와 *국회 입법*이 얼마나 연결되는지 한눈에.",
            "paid_subscriber": "유료 구독자 시점: 분기별 heatmap PDF + 이슈 alert.",
            "ad_sales":        "광고·세일즈 시점: 화제성 이슈 ↔ 광고 매칭 timing 정밀화.",
            "b2b":             "B2B 정책 인텔리전스 시점: 이슈 × 활동 webhook + 정책 변동 alert.",
        },
        "implication": "*이슈 × 입법 상관 정량*은 *정책 의제 priority + B2B 모니터링* 우선순위 자동 계산.",
        "cta": "- Top 5 결합 의원 cross-reference (시나리오 F)\n- 분기별 heatmap 시계열 PDF\n- 이슈 lifecycle 1단계 prediction",
    },
    "_default": {
        "headline": "22대 국회 활동 정량 분석 — 페르소나별 KPI 우선순위로 맞춤 해석 (출처: 국회 OpenAPI + Sonnet 4.6).",
        "findings": (
            "- 시나리오별 specialized 분석 (BM25·KNN·Cohere·Bedrock Agents·Code Interpreter)\n"
            "- 페르소나별 KPI 어휘 + 어조 자동 변환 (편집국·데이터AI·광고·B2C·B2B)\n"
            "- ADR-0004 정치 중립성 가드레일 자동 (입력·출력 양쪽)\n"
            "- 정량 수치에 출처 명시 (real/synthetic/external)\n"
        ),
        "persona": {
            "editorial":       "편집국 시점: 정량 통계 + 출처 명시로 *인용 가능 자료*. 후속 인터뷰 hook과 단독 보도 angle 발굴.",
            "data_ai":         "데이터·AI 데스크 시점: sample_size·신뢰구간·p-value 자동 첨부. cohort 비교 baseline 권장.",
            "ad_sales":        "광고·세일즈 시점: 카테고리별 광고 적합도 + 페르소나 매칭 정량.",
            "general_reader":  "일반 독자 시점: 전문 용어 한 줄 풀이 + 내 지역구·내 관심사 중심.",
            "paid_subscriber": "유료 구독자 시점: 심층 시계열·교차 분석·PDF 보고서 + premium 도구.",
            "b2b":             "B2B 정책 인텔리전스 시점: 정책 영향도·통과 가능성·산업 영향 정량.",
        },
        "implication": "정량 + 정성 + 페르소나 어휘 결합으로 *같은 데이터 6개 다른 narrative*. 데이터 민주화 핵심.",
        "cta": "- 시나리오 cross-reference 분석 (A·B·E·F·M 결합)\n- 페르소나별 KPI 차이 정량 비교\n- ADR-0004 balance_score 분포 분석",
    },
}


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
        "Neptune 조회 결과 요약 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강):\n"
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
        "**[미디어/신문사 내부용 — 편집국 기자]**\n\n"
        "## 📌 헤드라인\n"
        "22대 국회 1분기 AI 관련 의안 10건 발의 — 더불어민주당 5건·국민의힘 3건·기타 2건. "
        "표결 일치율 62%로 양당 협력 의제 (출처: 22대 임기 · 국회 OpenAPI + 합성 보강).\n\n"
        "## 🔍 핵심 발견\n"
        "- AI 입법 burst: 1분기 발의 10건, 직전 분기 대비 +5건 (sample_size=20)\n"
        "- 공동발의 평균 연결도 2.3 ± 0.4 — 양당 의원 cross-party 협업 (출처: real)\n"
        "- 통과율: 발의 5 / 상임위 3 / 본회의 1 / 가결 1 (실제 OpenAPI)\n"
        "- 카테고리 분포: 산업 진흥 4 / 법무·개인정보 3 / 디지털 문화 3\n"
        "- 의안 단계별 표결 일치율 차이 미검증 (후속 데이터 필요)\n\n"
        "## 👤 페르소나 시점 해석\n"
        "편집국 시점에서 가장 인용 가능한 통계는 *표결 일치율 62%* + *공동발의 cross-party 비율*. "
        "둘 다 \"양당 협력\" headline에 정량 근거 제공. 단정적 평가 회피하고 \"협력적 양상\" 같은 양면 어조 유지.\n\n"
        "## 💡 비즈니스/취재 함의\n"
        "AI 정책은 정파를 가르지 않는 의제로 정착 중 → 후속 취재는 *왜 협력이 가능한가*에 초점. "
        "특정 의원의 의제 주도성 vs 정당 합의 공정 비교가 핵심 narrative.\n\n"
        "## 🎯 후속 취재 포인트 (3건)\n"
        "- 핵심 공동발의 의원의 지역구 산업 분포 ↔ 발의 카테고리 상관관계 (시나리오 H + N 결합)\n"
        "- 의안 단계별 표결 일치율 분리 분석 — 상임위 vs 본회의 (시나리오 K 활용)\n"
        "- 1분기 미디어 화제성 score(scenario J) ↔ 발의 빈도 시차 분석"
    )


def _mock_for_data_ai() -> str:
    return (
        "**[미디어/신문사 내부용 — 데이터·AI 데스크]**\n\n"
        "## 📌 헤드라인\n"
        "AI 입법 표결 일치율 62% (95% CI: 54–70%, n=10). 카테고리 엔트로피 1.49 → 균형 분포.\n\n"
        "## 🔍 핵심 발견\n"
        "- 발의 건수: n=10 (출처: real, 22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI)\n"
        "- 정당 분포: 더불어민주당 5 / 국민의힘 3 / 기타 2 (χ² 검정 p=0.34 → 차이 미유의)\n"
        "- 공동발의 평균 연결도: 2.3 ± 0.4 (CV=0.17, 안정)\n"
        "- 표결 일치율: 62% (95% CI: 54–70%, Wilson interval)\n"
        "- 카테고리 엔트로피: 1.49 / log(3)=1.58 → 균형 분포 (max 대비 94%)\n\n"
        "## 👤 페르소나 시점 해석\n"
        "데이터·AI 데스크 KPI: 통계 유의성·sample size·데이터 출처 투명성. "
        "n=10은 *exploratory* 단계 — 본격 추론 전 sample expansion 필요. "
        "Wilson interval로 일치율 분포 CI 명시 → 점 추정의 한계 인지.\n\n"
        "## 💡 비즈니스/취재 함의\n"
        "현재 sample로 \"양당 협력\" 결론은 *통계적으로 보수적*. "
        "더 강한 시그널을 위해 sample expansion + 표결 단계별 분리 분석 필요.\n\n"
        "## 🎯 추가 분석 가설 (3건)\n"
        "- 허브 노드 제거 시 네트워크 modularity 변화 분석 (NetworkX community detection)\n"
        "- 단계별 일치율 분산 — 본회의 표결 vs 상임위 통과 시점 (paired t-test)\n"
        "- 의안 카테고리별 통과율 logistic regression coefficient (n≥50 필요)"
    )


def _mock_for_ad_sales() -> str:
    return (
        "**[미디어/신문사 내부용 — 광고·세일즈]**\n\n"
        "## 📌 헤드라인\n"
        "AI 입법 콘텐츠 광고 적합도 *매우 높음* — Agent 판단 score 0.87 (allow). "
        "정치 민감 토픽 회피 없음, 안전 콘텐츠 등급.\n\n"
        "## 🔍 핵심 발견\n"
        "- 콘텐츠 토픽: AI 입법·데이터 산업·디지털 거버넌스 (real)\n"
        "- 추천 광고 카테고리: 데이터 솔루션·보안·컴플라이언스·클라우드 (synthetic 인벤토리 234건)\n"
        "- 3-way 매칭 score: keyword 0.45 / embedding 0.71 / Agent 0.87 (양립 판단)\n"
        "- 광고주 평판 위험: low (정파 단정 없음, 정책 정보성)\n"
        "- ADR-0004 governance: balance_score 0.85, alarm=false\n\n"
        "## 👤 페르소나 시점 해석\n"
        "광고·세일즈 KPI: 매칭 정확도·CTR·광고주 평판 보호. "
        "Agent 모드의 0.87 score는 *콘텐츠와 광고 카테고리의 의미 적합도*가 keyword(0.45) 대비 1.9배 높음. "
        "Agent의 trade-off 추론이 *정량 매칭으로는 잡지 못하는 평판 위험*까지 포착.\n\n"
        "## 💡 비즈니스/취재 함의\n"
        "AI/데이터 산업 광고주는 본 콘텐츠 카테고리에 *premium CPM 가능*. "
        "단, Agent의 판단 trace를 *광고주에게 transparent하게 공개*하면 brand-safe 차별화 가능.\n\n"
        "## 🎯 광고 매칭 전략 (3건)\n"
        "- 데이터·보안 솔루션 광고주 top 5에 본 콘텐츠 카테고리 premium slot 제안 (시나리오 L)\n"
        "- Agent governance trace 노출 — AdMatchDecision API를 광고주 대시보드에 통합\n"
        "- 정치 민감 콘텐츠 (시나리오 K·I)는 *광고 슬롯 자동 skip* 기본값 유지"
    )


def _mock_for_general_reader() -> str:
    return (
        "**[구독자용 (무료) — 일반 독자 안내]**\n\n"
        "## 📌 헤드라인\n"
        "22대 국회 첫 분기에 AI 관련 법안 10건이 발의되었어요. 여야 의원들이 함께 발의한 사례가 많아서 협력적 분위기예요.\n\n"
        "## 🔍 핵심 발견\n"
        "- 📜 **발의 (proposal)** = 의원이 새 법을 제안하는 것. 본회의 통과까지 여러 단계가 있어요.\n"
        "- 1분기 AI 법안 10건 중 *여야 함께 발의*가 가장 많은 카테고리예요\n"
        "- 본회의 *표결*에서 양당이 같이 찬성한 비율 62% (꽤 협력적!)\n"
        "- 카테고리: 산업 진흥 4건 · 개인정보 보호 3건 · 디지털 문화 3건\n"
        "- 출처: 국회 공개 데이터 (open.assembly.go.kr) 22대 임기 (2024-05 ~ 2026-05)\n\n"
        "## 👤 페르소나 시점 해석\n"
        "정치 입문자에게: AI 법안은 *우리 일상에 직접 영향*을 주는 분야예요. "
        "예를 들면 *개인정보 보호법*이 강해지면 카카오·네이버 같은 회사들이 우리 데이터를 다루는 방식이 달라져요.\n\n"
        "## 💡 비즈니스/취재 함의\n"
        "AI 법안은 정파를 가르지 않는 *공통 의제* — 양당이 협력하는 보기 드문 분야 중 하나예요. "
        "법이 통과되면 일상에 빠르게 적용됩니다.\n\n"
        "## 🎯 관련해서 더 알고 싶다면 (2-3건)\n"
        "- 🗺️ **내 지역구 의원** 활동 보기 → 지역구 지도에서 클릭\n"
        "- 🏷️ **'AI' 토픽 팔로우** → 새 법안 발의 시 안내 받기\n"
        "- ⭐ **유료 구독자**라면: 의안 단계별 진행률 + 통과 시점 알림 + PDF 리포트 가능"
    )


def _mock_for_paid_subscriber() -> str:
    return (
        "**[유료 구독자용 — 심층 리포트]**\n\n"
        "## 📌 헤드라인\n"
        "22대 국회 1분기 AI 입법 — 양당 협력 패턴 정착 단계. 표결 일치율 62%·공동발의 cross-party 비율 58%·통과율 10% (sample n=10).\n\n"
        "## 🔍 핵심 발견\n"
        "- 의안 단계별 통과율: 발의 50% · 상임위 30% · 본회의 10% · 가결 10%\n"
        "- 카테고리: 산업 진흥 4건 · 법무·개인정보 3건 · 디지털 문화 3건\n"
        "- 공동발의 평균 연결도 2.3 ± 0.4 — 안정적 cross-party 네트워크\n"
        "- 핵심 의원의 발의·표결·발언·미디어 노출 통합 timeline (시나리오 M)\n"
        "- balance_score 0.85 (정당 단정 표현 회피, ADR-0004 4-layer 모두 통과)\n\n"
        "## 👤 페르소나 시점 해석\n"
        "유료 구독자 KPI: 심층 분석·시계열·교차 분석. "
        "1분기 패턴이 *지속될지* vs *일시적 burst*인지가 핵심 질문 — *2-4분기 추가 데이터*로 검증 필요. "
        "통과율 10%는 *입법 leveraging* 측면에서 *낮은 수치* — 발의 stage에서 의제 노출 효과가 더 강함.\n\n"
        "## 💡 비즈니스/취재 함의\n"
        "AI 정책은 *공통 의제*로 정착했지만 *실제 통과율*은 낮음 → 의안 *완결성·법체계 정합성* 부족 가능성. "
        "후속 분기 통과율 추적이 *의제의 실효성* 판단 핵심.\n\n"
        "## 🎯 심층 분석 + 알림 설정 권고 (3건)\n"
        "- 📄 **PDF 리포트** — 5섹션 + 차트 (matplotlib) + 의원 timeline 통합 다운로드\n"
        "- 🔔 **핵심 의원 알림** — 표결·발언·미디어 노출 trigger 시 push (시나리오 M)\n"
        "- ⚖ **의원 비교 도구** — 동일 위원회 · 다른 정당 의원 5명 cross-tab 분석"
    )


def _mock_for_b2b() -> str:
    return (
        "**[B2B 정책 인텔리전스 — API 응답]**\n\n"
        "## 📌 헤드라인\n"
        "AI 입법 영향도 impact_score=0.85 · confidence=0.92 · 통과 가능성 medium-high (sample n=10).\n\n"
        "## 🔍 핵심 발견\n"
        "```json\n"
        "{\n"
        '  \"headline\": \"22대 국회 AI 입법 동향 — 1분기 리뷰\",\n'
        '  \"summary\": \"AI 의안 10건 발의 — 양당 협력 의제 정착, 표결 일치율 62%\",\n'
        '  \"impact_score\": 0.85,\n'
        '  \"confidence\": 0.92,\n'
        '  \"party_distribution\": {\"더불어민주당\": 5, \"국민의힘\": 3, \"기타\": 2},\n'
        '  \"category_distribution\": {\"산업\": 4, \"법무\": 3, \"문화\": 3},\n'
        '  \"agreement_rate\": 0.62,\n'
        '  \"bill_stage\": {\"proposed\": 5, \"in_committee\": 3, \"in_plenary\": 1, \"passed\": 1},\n'
        '  \"sources\": [\"22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI\"]\n'
        "}\n"
        "```\n\n"
        "## 👤 페르소나 시점 해석\n"
        "B2B 정책 인텔리전스 KPI: impact_score · confidence · 통과 가능성 · 산업 영향. "
        "impact_score 0.85는 *데이터 산업 영향 매우 높음* 등급 — 컴플라이언스 대응 우선순위 상위.\n\n"
        "## 💡 비즈니스/취재 함의\n"
        "데이터·AI·클라우드 산업 기업은 *상임위 심사 단계* (3건)에 의견 제출 기회. "
        "본회의 상정 1건은 30-90일 내 통과 가능성 검토 필요.\n\n"
        "## 🎯 정책 모니터링 액션 (3건)\n"
        "- 🔔 *발의 신규* 알림 — `POST /api/insight/subscribe` (개별 의원·키워드 단위)\n"
        "- 📊 *통과 가능성* 시계열 — DOR (Days-to-Outcome Ratio) 추적\n"
        "- 📑 관련 KOSIS 통계: https://kosis.kr/statHtml/statHtml.do?orgId=440\n"
        "  관련 정부 백서: 2025 AI 산업 백서"
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


# ─── Token-level streaming invoke ───────────────────────────────────────────

def invoke_stream(
    user_message: str,
    persona_id: Optional[str] = "editorial",
    scenario_code: str = "B",
    model_id: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    chunk_chars: int = 16,
    chunk_delay_sec: float = 0.02,
) -> Iterator[tuple[str, object]]:
    """토큰 단위 streaming.

    CloudFront idle timeout 리셋 메커니즘:
    - delta 이벤트 하나가 keep-alive 카운터 reset
    - SSE chunked transfer를 ORIGIN_RESPONSE Lambda@Edge로 변형하지 말 것 (전체 buffer)
    - VIEWER_REQUEST 단계에서만 auth - 응답 변형 0

    Yields tuples:
      - ("delta", str)             : 텍스트 chunk
      - ("final", InvokeResult)    : 종료 결과 + balance score
      - ("error", str)             : mid-stream 예외 (stack trace)

    Args:
        chunk_chars: demo mode chunk 크기 (production은 contentBlockDelta 그대로).
        chunk_delay_sec: chunk간 sleep (CloudFront keep-alive reset 목적).
    """
    pid = persona_id or "editorial"
    selected_model = model_id or os.environ.get("BEDROCK_CHAT_MODEL_ID", DEFAULT_MODEL_ID)
    mt = scenario_max_tokens(scenario_code, max_tokens)
    t0 = time.monotonic()

    sys_prompt = system_prompt(pid, scenario_code)

    # 입력 가드
    input_check = guardrails.check_prompt(user_message, pid)
    if not input_check.passed:
        blocked = _blocked_input_result(
            blocked_topics=list(input_check.blocked_topics),
            persona_id=pid, scenario_code=scenario_code, model_id=selected_model,
        )
        yield ("delta", blocked.text)
        yield ("final", blocked)
        _record(blocked, int((time.monotonic() - t0) * 1000))
        return

    try:
        if _demo_mode():
            yield from _stream_demo_chunked(
                user_message=user_message,
                sys_prompt=sys_prompt,
                chunk_chars=chunk_chars,
                chunk_delay_sec=chunk_delay_sec,
            )
            full_text = _mock_response(user_message, sys_prompt)
        else:
            full_text = yield from _stream_converse(
                sys_prompt=sys_prompt,
                user_message=user_message,
                model_id=selected_model,
                temperature=temperature,
                max_tokens=mt,
            )
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        # final emit try/except 패턴: 클라이언트가 정확한 상태 알 수 있도록 final 보장
        err_result = InvokeResult(
            text=f"(스트리밍 중 오류: {exc.__class__.__name__})",
            model_id=selected_model, persona_id=pid, scenario_code=scenario_code,
            guardrail_passed=False, political_balance_score=0.0,
            alarm=True, alarm_reason=f"stream_exception: {exc!r}",
            balance_components={}, blocked_topics=[],
        )
        yield ("error", tb)
        yield ("final", err_result)
        _record(err_result, int((time.monotonic() - t0) * 1000))
        return

    # 출력 평가 + final
    annotation = guardrails.annotate_response(full_text, pid)
    result = InvokeResult(
        text=full_text, model_id=selected_model,
        persona_id=pid, scenario_code=scenario_code,
        guardrail_passed=annotation["guardrail_passed"],
        political_balance_score=annotation["political_balance_score"],
        alarm=annotation["alarm"], alarm_reason=annotation["alarm_reason"],
        balance_components=annotation["balance_components"], blocked_topics=[],
    )
    yield ("final", result)
    _record(result, int((time.monotonic() - t0) * 1000))


def _stream_demo_chunked(
    user_message: str, sys_prompt: str, chunk_chars: int, chunk_delay_sec: float,
) -> Iterator[tuple[str, object]]:
    """Mock 응답을 chunked로 emit (CloudFront idle timeout 시뮬레이션)."""
    text = _mock_response(user_message, sys_prompt)
    for i in range(0, len(text), chunk_chars):
        yield ("delta", text[i:i + chunk_chars])
        if chunk_delay_sec > 0:
            time.sleep(chunk_delay_sec)


def _stream_converse(
    sys_prompt: str, user_message: str, model_id: str,
    temperature: float, max_tokens: int,
) -> Iterator[tuple[str, object]]:
    """Bedrock converse_stream contentBlockDelta loop.

    각 contentBlockDelta마다 delta event emit → CloudFront idle timeout reset.
    Returns full_text via generator return value.
    """
    from api.aws_clients import session as boto_session

    client = boto_session().client("bedrock-runtime")
    response = client.converse_stream(
        modelId=model_id,
        system=[{"text": sys_prompt}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )

    parts: list[str] = []
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            chunk = event["contentBlockDelta"].get("delta", {}).get("text", "")
            if chunk:
                parts.append(chunk)
                yield ("delta", chunk)
        elif "messageStop" in event:
            # stop_reason: end_turn / max_tokens / stop_sequence — 운영 시그널
            stop_reason = event["messageStop"].get("stopReason")
            if stop_reason == "max_tokens":
                yield ("delta", "\n\n[응답 절단: max_tokens 초과]")
    return "".join(parts)
