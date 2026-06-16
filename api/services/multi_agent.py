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

    # Agentic mode는 자율적으로 *추가 real endpoint*까지 호출 (Stage 2보다 깊은 분석)
    extra_context = ""
    qlow = query.lower()
    try:
        # 의원 이름 lookup (예: "김은혜 의원의 의정활동 이력은?")
        from api.services.three_stage import _detect_district_keyword, _detect_member_name
        named_member = _detect_member_name(query)
        if named_member:
            mid = getattr(named_member, "assembly_id", "")
            name = getattr(named_member, "name", "—")
            party = getattr(named_member, "party", "—")
            district = getattr(named_member, "district", "—")
            committee = getattr(named_member, "committee", None) or "—"
            reelection = getattr(named_member, "reelection", None) or "—"
            # 유사-의원 intent → 시나리오 F lookalike (활동 이력 아님). 사용자 신고 2026-06-16.
            _sim_intent = (any(k in query for k in ("비슷", "유사", "닮은", "투표성향", "투표 성향", "룩어라이크"))
                           or "lookalike" in qlow or "similar" in qlow)
            _sim_done = False
            if _sim_intent:
                try:
                    from api.services import lookalike_builder
                    lr = lookalike_builder.build_lookalikes(mid, top_k=5)
                except Exception:
                    lr = None
                if lr and lr.candidates:
                    tools_called.append("lookalike_lookup")
                    cand_lines = "\n".join(
                        f"  - {c.name} ({c.party}) similarity {c.similarity:.2f}"
                        + (" · cross-party" if c.cross_party_signal else "")
                        + (f" · {c.factors[0]}" if c.factors else "")
                        for c in lr.candidates[:5]
                    )
                    extra_context = (
                        f"\n\n[real lookalike /api/lookalike/{mid} · {name} 유사 의원]\n"
                        f"- seed: {name} ({party}) · cluster {lr.seed_cluster_label or '—'}\n"
                        f"- 유사 의원 top {len(lr.candidates[:5])} (cluster + 활동 근접 + cross-party 신호):\n{cand_lines}\n"
                    )
                    sources_used.extend([
                        {"id": c.person_id, "title": f"{c.name} ({c.party})", "source": "real", "node_type": "Person"}
                        for c in lr.candidates[:5]
                    ])
                    _sim_done = True
            if not _sim_done:
                tools_called.append("member_journey_lookup")
                stats_line = ""
                events_lines = ""
                try:
                    from api.services import journey_builder
                    jr = journey_builder.build_journey(mid)
                    stats = (jr.stats if jr else None) or {}
                    stats_line = (
                        f"발의 {stats.get('proposed', '?')}건 · 공동발의 {stats.get('co_proposed','?')}건 "
                        f"· 표결 {stats.get('voted','?')}건 · 발언 {stats.get('statements','?')}건"
                    )
                    events = ((jr.events if jr else None) or [])[:5]
                    if events:
                        events_lines = "\n".join(
                            f"  - {getattr(e,'date','—')} | {getattr(e,'event_type','—')} | {(getattr(e,'title','') or '')[:60]}"
                            for e in events
                        )
                except Exception:
                    pass
                extra_context = (
                    f"\n\n[real /api/journey/{mid} · 의원 이력]\n"
                    f"- {name} ({party}) — {district}\n"
                    f"- 위원회: {committee} · {reelection}\n"
                    f"- 활동: {stats_line}\n"
                    f"- 최근 이벤트:\n{events_lines}\n"
                )
                sources_used.append({"id": mid, "title": f"{name} ({party})", "source": "real", "node_type": "Person"})
        # 지역구 lookup (예: "분당갑 국회의원은?")
        district_keyword = _detect_district_keyword(query)
        if not extra_context and district_keyword and ("의원" in query or "대표" in query or "국회" in query or "지역구" in query):
            from api.services import member_directory
            matched = [m for m in member_directory.list_members() if district_keyword in (getattr(m, "district", "") or "")]
            if matched:
                tools_called.append("district_member_lookup")
                lines = []
                for m in matched[:5]:
                    lines.append(
                        f"- {getattr(m,'name','')} ({getattr(m,'party','')}) — {getattr(m,'district','')} · 위원회: {getattr(m,'committee',None) or '—'} · {getattr(m,'reelection',None) or '—'}"
                    )
                extra_context = (
                    f"\n\n[real /api/members district='{district_keyword}' · {len(matched)}명]\n"
                    + "\n".join(lines)
                )
                sources_used.extend([
                    {"id": getattr(m,'assembly_id',''), "title": f"{getattr(m,'name','')} ({getattr(m,'party','')})", "source": "real", "node_type": "Person"}
                    for m in matched[:5]
                ])
        if "영향력" in query or "influence" in qlow:
            from api.routers.insights_advanced import get_influence_rank
            ir = get_influence_rank(limit=5)
            tools_called.append("get_influence_rank")
            top = ir.members[:5]
            extra_context = (
                "\n\n[real Neptune /api/insights/influence-rank top 5]\n"
                + "\n".join(
                    f"#{i+1} {m.name} ({m.party}) 발의 {m.proposed_count} · 공동 {m.co_proposed_count} · cohort {m.cohort_weight_sum} · score {m.influence_score*100:.0f}"
                    for i, m in enumerate(top)
                )
            )
            sources_used.extend([
                {"id": m.assembly_id, "title": f"{m.name} ({m.party})", "source": "real", "node_type": "Person"}
                for m in top
            ])
        elif "응집도" in query or "cohesion" in qlow:
            from api.routers.insights_advanced import get_party_cohesion
            pc = get_party_cohesion()
            tools_called.append("get_party_cohesion")
            top = pc.parties[:5]
            extra_context = (
                f"\n\n[real Neptune /api/insights/party-cohesion overall {pc.overall_cohesion*100:.1f}%]\n"
                + "\n".join(
                    f"#{i+1} {p.party} ({p.member_count}명) — {p.majority_alignment_pct}%"
                    for i, p in enumerate(top)
                )
            )
        elif "swing" in qlow or "이탈" in query:
            from api.routers.insights_advanced import get_swing_voters
            sv = get_swing_voters(limit=5, threshold_pct=95)
            tools_called.append("get_swing_voters")
            top = sv.members[:5]
            extra_context = (
                f"\n\n[real Neptune /api/insights/swing-voters threshold 95% · {len(sv.members)}명]\n"
                + "\n".join(
                    f"#{i+1} {m.name} ({m.party}) 일치율 {m.party_majority_alignment_pct}% · 이탈 {m.deviation_count}/{m.total_active_votes}"
                    for i, m in enumerate(top)
                )
            )
    except Exception:
        pass

    graph_summary = (
        f"OpenSearch: {len(hits)}건 hit. "
        f"Neptune: 의안 {len(bill_rows)}건, 의원 {len(person_rows)}명 조회."
        + extra_context
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
    # extra_context (real Neptune marker)도 editor message에 전달 →
    # bedrock._mock_response의 marker 감지 branch에서 real-data 답변 생성
    editor_message = (
        f"원 질문: {query}\n\n"
        f"--- Planner ---\n{plan_text}\n\n"
        f"--- Graph 요약 ---\n{graph_result.text}\n\n"
        f"--- Analyst 해석 ---\n{analyst_result.text}\n"
        f"{extra_context}\n\n"
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
