"""3-stage chat - Chatbot / Agent / Agentic AI 비교 시연 (시나리오 B 핵심).

같은 질문에 3 모드가 다르게 답한다 - 데모의 메인 차별점.

Stage 1 (Chatbot): OpenSearch top-K → Bedrock 단일 호출 (RAG).
Stage 2 (Agent): Bedrock Converse + 사전 정의 도구 4개 순차 호출 (Tool Use).
Stage 3 (Agentic): 4 에이전트(Planner/Graph/Analyst/Editor) 자율 협업.

References:
- spec §3.3 시나리오 B 상세
- spec §7 three_stage 컴포넌트 노트
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from api.services import bedrock, cohort, neptune, opensearch
from api.services.multi_agent import run_agentic_pipeline

__all__ = ["StageResult", "stage1_chatbot", "stage2_agent", "stage3_agentic", "run_all_stages"]


@dataclass(frozen=True)
class StageResult:
    """3-stage 결과 표준 형식. SSE final event payload 후보."""
    stage: str                          # "chatbot" | "agent" | "agentic"
    text: str
    sources_used: list[dict] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    agents_invoked: list[str] = field(default_factory=list)
    political_balance_score: float = 1.0
    alarm: bool = False
    duration_ms: int = 0
    extras: dict = field(default_factory=dict)  # stage-specific 부가 정보

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Stage 1 — Chatbot (RAG) ─────────────────────────────────────────────────

def stage1_chatbot(
    query: str,
    persona_id: Optional[str] = "editorial",
) -> StageResult:
    """Stage 1 - 단순 RAG.

    Flow:
        1. OpenSearch hybrid_search top-5
        2. Bedrock 단일 호출로 요약

    의도: '단순' 한계 노출. 협력 패턴, 네트워크, 표결 분석 불가.
    데모에서 청중이 "이건 좀 부족한데" 라고 느껴야 함.
    """
    t0 = time.monotonic()

    sources = cohort.select(persona_id, "B")
    hits = opensearch.hybrid_search(query, top_k=5, source_filter=sources)

    context_text = "\n".join(f"- {h.title}: {h.snippet}" for h in hits)
    augmented_query = (
        f"{query}\n\n--- 참고 자료 ---\n{context_text}\n\n"
        f"위 자료만으로 간단히 답하세요. 단순 나열로 충분합니다."
    )

    result = bedrock.invoke(
        augmented_query,
        persona_id=persona_id,
        scenario_code="B",
    )

    duration_ms = int((time.monotonic() - t0) * 1000)

    return StageResult(
        stage="chatbot",
        text=result.text,
        sources_used=[
            {"id": h.id, "title": h.title, "source": h.source, "node_type": h.node_type}
            for h in hits
        ],
        tools_called=[],
        agents_invoked=[],
        political_balance_score=result.political_balance_score,
        alarm=result.alarm,
        duration_ms=duration_ms,
        extras={"approach": "RAG", "limitation": "협력 패턴·네트워크 분석 불가"},
    )


# ─── Stage 2 — Agent (Tool Use) ──────────────────────────────────────────────

def stage2_agent(
    query: str,
    persona_id: Optional[str] = "editorial",
) -> StageResult:
    """Stage 2 - Tool use 사전 정의 워크플로.

    Flow (PoC MVP - 단순화):
        1. search_bills
        2. get_proposers
        3. cosponsor_network
        4. analyze_votes
        5. Bedrock 종합 답변

    실 Bedrock Converse tool use API 통합은 Phase 2.
    의도: '워크플로 강제' 한계 노출. 사전 정의된 흐름에 갇힘.
    """
    t0 = time.monotonic()
    tools_called: list[str] = []
    sources_used: list[dict] = []

    # 도구 1: search_bills (OpenSearch)
    sources = cohort.select(persona_id, "B")
    hits = opensearch.hybrid_search(query, top_k=10, source_filter=sources)
    tools_called.append("search_bills")
    sources_used.extend([
        {"id": h.id, "title": h.title, "source": h.source, "node_type": h.node_type}
        for h in hits[:3]
    ])

    # 도구 2: get_proposers (Neptune)
    bill_rows = neptune.open_cypher("MATCH (b:Bill) RETURN b LIMIT 5")
    tools_called.append("get_proposers")

    # 도구 3: cosponsor_network (Neptune)
    person_rows = neptune.open_cypher("MATCH (p:Person) RETURN p LIMIT 5")
    tools_called.append("cosponsor_network")

    # 도구 4: analyze_votes (Neptune)
    vote_rows = neptune.open_cypher("MATCH (v:Vote) RETURN v LIMIT 5")
    tools_called.append("analyze_votes")

    # 종합 답변
    context_summary = (
        f"검색 결과 {len(hits)}건. "
        f"의안 {len(bill_rows)}건, 의원 {len(person_rows)}명, 표결 {len(vote_rows)}건 조회."
    )
    augmented_query = (
        f"{query}\n\n--- 도구 호출 결과 ---\n{context_summary}\n\n"
        f"각 도구 결과를 종합하여 구조화된 답변을 제시하세요."
    )
    result = bedrock.invoke(
        augmented_query,
        persona_id=persona_id,
        scenario_code="B",
    )

    duration_ms = int((time.monotonic() - t0) * 1000)

    return StageResult(
        stage="agent",
        text=result.text,
        sources_used=sources_used,
        tools_called=tools_called,
        agents_invoked=[],
        political_balance_score=result.political_balance_score,
        alarm=result.alarm,
        duration_ms=duration_ms,
        extras={"approach": "Tool Use (사전 정의)", "limitation": "워크플로 외 새 질문 약함"},
    )


# ─── Stage 3 — Agentic AI (4 Agents) ──────────────────────────────────────────

def stage3_agentic(
    query: str,
    persona_id: Optional[str] = "editorial",
) -> StageResult:
    """Stage 3 - Agentic 4 에이전트 자율 협업.

    multi_agent.run_agentic_pipeline 위임.
    의도: 자율 계획·재질의·기사 초안까지 - 청중이 "이게 진짜 AI 분석" 느낌.
    """
    t0 = time.monotonic()
    result = run_agentic_pipeline(query, persona_id=persona_id)
    duration_ms = int((time.monotonic() - t0) * 1000)

    return StageResult(
        stage="agentic",
        text=result["text"],
        sources_used=result["sources_used"],
        tools_called=result["tools_called"],
        agents_invoked=result["agents_invoked"],
        political_balance_score=result["political_balance_score"],
        alarm=result["alarm"],
        duration_ms=duration_ms,
        extras={
            "approach": "Multi-Agent (Planner / Graph / Analyst / Editor)",
            "plan_text": result["plan_text"],
            "graph_text": result["graph_text"],
            "analyst_text": result["analyst_text"],
        },
    )


# ─── 3 모드 비교 (데모 메인) ─────────────────────────────────────────────────

def run_all_stages(
    query: str,
    persona_id: Optional[str] = "editorial",
) -> dict[str, StageResult]:
    """3 모드 모두 실행. 시연용 사이드바이사이드 비교.

    PoC MVP: 순차 실행. Phase 2에서 asyncio.gather로 병렬화.
    """
    return {
        "chatbot": stage1_chatbot(query, persona_id),
        "agent": stage2_agent(query, persona_id),
        "agentic": stage3_agentic(query, persona_id),
    }
