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

_DISTRICT_KEYWORDS = (
    # 광역시·도
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    # 주요 행정구 / 지역구 keyword
    "분당", "수지", "기흥", "처인", "정자", "야탑",
    "강남", "서초", "송파", "강동", "강북", "강서", "관악", "광진", "구로",
    "금천", "노원", "도봉", "동대문", "동작", "마포", "서대문", "성동", "성북",
    "양천", "영등포", "용산", "은평", "종로", "중랑",
    "해운대", "수영", "남구", "동구", "북구", "중구",
    "수원", "성남", "고양", "용인", "안양", "안산", "부천", "광명", "평택",
    "화성", "오산", "시흥", "군포", "의왕", "하남", "구리", "남양주", "파주",
    "김포", "이천", "안성", "여주", "양주", "포천", "동두천", "가평", "양평",
    "춘천", "원주", "강릉", "동해", "삼척", "속초", "태백", "홍천", "횡성",
    "청주", "충주", "제천", "보은", "옥천", "영동", "증평", "진천",
    "천안", "공주", "보령", "아산", "서산", "논산", "계룡", "당진",
    "전주", "군산", "익산", "정읍", "남원", "김제",
    "목포", "여수", "순천", "나주", "광양",
    "포항", "경주", "김천", "안동", "구미", "영주", "영천", "상주", "문경", "경산",
    "창원", "진주", "통영", "사천", "김해", "밀양", "거제", "양산",
    "비례대표",
)


def _detect_district_keyword(query: str) -> Optional[str]:
    """Query에서 지역구 keyword 감지.

    "분당갑 국회의원" → "분당"
    "강남을 의원" → "강남"
    "성남시 의원" → "성남"
    여러 후보 매치 시 가장 긴 keyword 우선.
    """
    matches = [k for k in _DISTRICT_KEYWORDS if k in query]
    if not matches:
        return None
    return max(matches, key=len)


def _detect_member_name(query: str):
    """Query에서 의원 이름 감지. 286명 directory 전수 매칭.

    "김은혜 의원의 의정활동 이력은?" → "김은혜" → assembly_id 반환
    "윤준병 발의 의안" → "윤준병"

    False positive 방지: 의원 이름과 명시적 keyword(*의원·발의·여정·이력·표결·활동·국회*)가 같이 등장한 경우만 매칭.
    """
    # CONTEXT keyword 없이는 의원 이름 매칭 X (false positive 회피)
    if not any(k in query for k in ("의원", "발의", "여정", "이력", "표결", "활동", "국회", "공약", "의정")):
        return None
    try:
        from api.services import member_directory
        # 가장 긴 이름 우선 매칭 (e.g., "김은혜" > "김은")
        members = sorted(member_directory.list_members(), key=lambda m: -len(getattr(m, "name", "") or ""))
        for m in members:
            name = getattr(m, "name", "") or ""
            if len(name) >= 2 and name in query:
                return m
    except Exception:
        return None
    return None


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

    # Stage 1 RAG는 도구 호출 없이 *raw 검색 결과만으로 답*하는 한계 노출.
    # 단, query keyword가 명확한 ranking 질문이면 RAG-stub 형태 답변 (검색결과를 정렬한 단순 list).
    qlow = query.lower()
    rag_stub = ""
    # 의원 이름 직접 검색은 RAG로도 답변 가능 — 단순 lookup
    named_member = _detect_member_name(query)
    if named_member:
        try:
            mid = getattr(named_member, "assembly_id", "")
            name = getattr(named_member, "name", "—")
            party = getattr(named_member, "party", "—")
            district = getattr(named_member, "district", "—")
            committee = getattr(named_member, "committee", None) or "—"
            from api.services import journey_builder
            jr = journey_builder.build_journey(mid)
            stats = (jr.stats if jr else None) or {}
            stats_line = (
                f"발의 {stats.get('proposed', '?')}건 · 공동발의 {stats.get('co_proposed','?')}건 "
                f"· 표결 {stats.get('voted','?')}건"
            )
            rag_stub = (
                f"\n\n[real /api/journey/{mid} · 의원 이력]\n"
                f"- {name} ({party}) — {district}\n"
                f"- 위원회: {committee}\n"
                f"- {stats_line}\n"
            )
        except Exception:
            pass
    # 지역구 lookup은 RAG로 가능 — 검색결과를 1개 답변으로 단순 노출
    district_keyword = _detect_district_keyword(query)
    if not rag_stub and district_keyword and ("의원" in query or "대표" in query or "국회" in query or "지역구" in query):
        try:
            from api.services import member_directory
            matched = [m for m in member_directory.list_members() if district_keyword in (getattr(m, "district", "") or "")]
            if matched:
                lines = "\n".join(
                    f"- {getattr(m,'name','')} ({getattr(m,'party','')}) — {getattr(m,'district','')}"
                    for m in matched[:5]
                )
                rag_stub = (
                    f"\n\n[real /api/members district='{district_keyword}' · {len(matched)}명]\n{lines}"
                )
        except Exception:
            pass
    if "영향력" in query or "influence" in qlow:
        rag_stub = (
            f"\n\n[RAG 답변 — 단순 검색 요약, 정량 계산 없음]\n"
            f"OpenSearch BM25+KNN 검색 결과 {len(hits)}건 중 의원·의안 키워드 매칭만 가능. "
            f"단순 RAG는 *공동발의 cohort 가중치 계산이나 ranking algorithm을 실행할 수 없으므로* "
            f"\"영향력 1위는 누구\"라는 질문에 *직접 답할 수 없음*. "
            f"Agent/Agentic mode가 필요함."
        )
    elif "응집도" in query or "cohesion" in qlow:
        rag_stub = (
            f"\n\n[RAG 답변 — 단순 검색 요약]\n"
            f"RAG는 정당 majority value 계산 불가. Agent/Agentic mode 사용 권장."
        )
    elif "swing" in qlow or "이탈" in query:
        rag_stub = (
            f"\n\n[RAG 답변 — 단순 검색 요약]\n"
            f"RAG는 정당 majority 일치율 계산 불가. Agent/Agentic mode 사용 권장."
        )

    augmented_query = (
        f"{query}\n\n--- 참고 자료 ---\n{context_text}{rag_stub}\n\n"
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

    # 도구 5: query-aware real-data fetch (의원 영향력·응집도·swing voter·지역구·의원 이름)
    extra_context = ""
    qlow = query.lower()
    try:
        # 5z) 의원 이름 lookup (예: "김은혜 의원의 의정활동 이력은?")
        named_member = _detect_member_name(query)
        if named_member:
            tools_called.append("member_journey_lookup")
            mid = getattr(named_member, "assembly_id", "")
            name = getattr(named_member, "name", "—")
            party = getattr(named_member, "party", "—")
            district = getattr(named_member, "district", "—")
            committee = getattr(named_member, "committee", None) or "—"
            reelection = getattr(named_member, "reelection", None) or "—"
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
        # 5a) 지역구 이름 lookup (예: "분당갑 국회의원은?", "강남을 의원" 등)
        district_keyword = _detect_district_keyword(query)
        if district_keyword and ("의원" in query or "대표" in query or "국회" in query or "지역구" in query):
            from api.services import member_directory
            all_members = member_directory.list_members()
            matched = [m for m in all_members if district_keyword in (getattr(m, "district", "") or "")]
            if matched:
                tools_called.append("district_member_lookup")
                lines = []
                for m in matched[:5]:
                    name = getattr(m, "name", "—")
                    party = getattr(m, "party", "—")
                    district = getattr(m, "district", "—")
                    committee = getattr(m, "committee", None) or "—"
                    reelection = getattr(m, "reelection", None) or "—"
                    lines.append(f"- {name} ({party}) — {district} · 위원회: {committee} · {reelection}")
                extra_context = (
                    f"\n\n[real /api/members district='{district_keyword}' · {len(matched)}명]\n"
                    + "\n".join(lines)
                )
                sources_used.extend([
                    {"id": getattr(m, "assembly_id", ""), "title": f"{getattr(m,'name','')} ({getattr(m,'party','')})", "source": "real", "node_type": "Person"}
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
            sources_used.extend([
                {"id": m.assembly_id, "title": f"{m.name} ({m.party})", "source": "real", "node_type": "Person"}
                for m in top
            ])
    except Exception:
        pass

    # 종합 답변
    context_summary = (
        f"검색 결과 {len(hits)}건. "
        f"의안 {len(bill_rows)}건, 의원 {len(person_rows)}명, 표결 {len(vote_rows)}건 조회."
        + extra_context
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
