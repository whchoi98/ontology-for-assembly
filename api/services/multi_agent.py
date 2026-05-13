"""4-에이전트 협업 파이프라인 - Stage 3 (Agentic AI) 구현.

Planner → Graph → Analyst → Editor 순차 실행. 단순 도구 호출(Stage 2)을 넘어
에이전트가 자율적으로 계획·검색·해석·작성하며 필요 시 재질의한다.

PoC MVP 단계: 각 에이전트는 별도 system_prompt로 `bedrock.invoke` 호출.
실 다중 에이전트 프레임워크(Strands, AutoGen 등)는 Phase 2에서 통합.

References:
- spec §3.3 시나리오 B 상세 (3-stage 진화 비교)
- spec §7 multi_agent 컴포넌트 노트
"""
from __future__ import annotations

from typing import Optional, TypedDict

from api.services import bedrock, cohort, neptune, opensearch

__all__ = ["AGENT_PROMPTS", "AgenticResult", "run_agentic_pipeline"]


# 4 에이전트의 역할 정의. 모든 에이전트는 NEUTRALITY_GUARD_SUFFIX 자동 첨부됨
# (bedrock.invoke 통과 시 persona.system_prompt에서).
AGENT_PROMPTS: dict[str, str] = {
    "planner": (
        "[당신은 Planner 에이전트입니다] "
        "사용자 질문을 3-5개의 하위 과제로 분해하세요. "
        "각 과제는 한 줄 명령형으로 작성합니다. "
        "출력 형식: '1. <과제>\\n2. <과제>\\n3. <과제>'"
    ),
    "graph": (
        "[당신은 Graph 쿼리 에이전트입니다] "
        "Planner의 하위 과제를 Cypher 쿼리로 변환하고, "
        "Neptune 결과를 한 문단으로 요약하세요. 노드 개수와 핵심 패턴을 명시하세요."
    ),
    "analyst": (
        "[당신은 분석가 에이전트입니다] "
        "Graph 결과를 해석하고, 추가로 확인할 가설 1-2개를 제시하세요. "
        "필요 시 'Graph 에이전트에 재질의 필요: <쿼리>' 형식으로 명시할 수 있습니다."
    ),
    "editor": (
        "[당신은 편집장 에이전트입니다] "
        "Planner의 과제 분해, Graph 결과, Analyst 해석을 종합하여 "
        "기자가 바로 사용할 수 있는 기사 초안 형식으로 정리하세요. "
        "마지막에 '후속 취재 포인트' 2-3개를 bullet로 제시하세요."
    ),
}


class AgenticResult(TypedDict):
    """Agentic 파이프라인 결과. Stage 3의 표준 응답 형식.

    `agents_invoked` 순서가 그대로 운영 콘솔 트레이스에 노출되므로 자율 협업 흔적이
    유지된다. `plan_text` / `graph_text` / `analyst_text` 는 디버깅·시연용.
    """
    text: str
    agents_invoked: list[str]
    sources_used: list[dict]
    tools_called: list[str]
    political_balance_score: float
    alarm: bool
    plan_text: str
    graph_text: str
    analyst_text: str


def run_agentic_pipeline(
    query: str,
    persona_id: Optional[str] = "editorial",
) -> AgenticResult:
    """4 에이전트 순차 실행. Stage 3 메인 엔트리.

    Flow:
        1. Planner: 질문 → 하위 과제 N개
        2. Graph: 하위 과제 → Cypher → Neptune 결과 요약
        3. Analyst: Graph 결과 → 해석 + 가설
        4. Editor: 모든 컨텍스트 → 기사 초안 + 후속 취재 포인트
    """
    agents_invoked: list[str] = []
    sources_used: list[dict] = []
    tools_called: list[str] = []

    # ─── 1. Planner ──────────────────────────────────────────────────────────
    planner_result = _invoke_agent("planner", query, persona_id)
    plan_text = planner_result.text
    agents_invoked.append("planner")

    # ─── 2. Graph (Neptune + OpenSearch 도구 호출) ─────────────────────────
    sources = cohort.select(persona_id, "B")
    hits = opensearch.hybrid_search(query, top_k=5, source_filter=sources)
    sources_used.extend([
        {"id": h.id, "title": h.title, "source": h.source, "node_type": h.node_type}
        for h in hits[:3]
    ])
    tools_called.append("semantic_search")

    bill_rows = neptune.open_cypher(
        "MATCH (b:Bill) RETURN b LIMIT 5",
    )
    tools_called.append("neptune_bills")

    person_rows = neptune.open_cypher(
        "MATCH (p:Person) RETURN p LIMIT 5",
    )
    tools_called.append("neptune_persons")

    graph_summary = (
        f"OpenSearch: {len(hits)}건 hit. "
        f"Neptune: 의안 {len(bill_rows)}건, 의원 {len(person_rows)}명 조회."
    )
    graph_message = f"질문: {query}\n계획:\n{plan_text}\n\n조회 결과 요약: {graph_summary}"
    graph_result = _invoke_agent("graph", graph_message, persona_id)
    agents_invoked.append("graph")

    # ─── 3. Analyst ──────────────────────────────────────────────────────────
    analyst_message = (
        f"질문: {query}\n"
        f"계획: {plan_text}\n"
        f"Graph 결과 요약: {graph_result.text}"
    )
    analyst_result = _invoke_agent("analyst", analyst_message, persona_id)
    agents_invoked.append("analyst")

    # ─── 4. Editor ──────────────────────────────────────────────────────────
    editor_message = (
        f"원 질문: {query}\n\n"
        f"--- Planner ---\n{plan_text}\n\n"
        f"--- Graph 요약 ---\n{graph_result.text}\n\n"
        f"--- Analyst 해석 ---\n{analyst_result.text}\n\n"
        f"위 내용을 종합하여 기자가 바로 사용할 수 있는 기사 초안을 작성하세요."
    )
    editor_result = _invoke_agent("editor", editor_message, persona_id)
    agents_invoked.append("editor")

    return AgenticResult(
        text=editor_result.text,
        agents_invoked=agents_invoked,
        sources_used=sources_used,
        tools_called=tools_called,
        political_balance_score=editor_result.political_balance_score,
        alarm=editor_result.alarm,
        plan_text=plan_text,
        graph_text=graph_result.text,
        analyst_text=analyst_result.text,
    )


def _invoke_agent(agent_name: str, message: str, persona_id: Optional[str]):
    """단일 에이전트 호출. 에이전트 system_prompt를 메시지에 prepend.

    PoC MVP: 별도 system_prompt 인자 미지원, message에 inline 첨부.
    Phase 2: bedrock.invoke에 system_prompt_override 인자 추가 검토.
    """
    agent_prompt = AGENT_PROMPTS[agent_name]
    full_message = f"{agent_prompt}\n\n--- 입력 ---\n{message}"
    return bedrock.invoke(full_message, persona_id=persona_id, scenario_code="B")
