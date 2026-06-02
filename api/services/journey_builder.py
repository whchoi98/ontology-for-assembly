"""의원 정치 여정 builder - 시나리오 M (PDF 시그니처).

특정 person_id의 모든 활동(발의·공동발의·표결·발언·위원회 멤버십)을 통합하여
시간순 timeline 구성. real adapter + synthetic seed 모두 활용.

References:
- spec §3.1 시나리오 M (PDF 시그니처)
- data.real.bill/member/vote/session 어댑터
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

__all__ = ["JourneyEvent", "JourneyResult", "build_journey"]


EventType = Literal["proposed", "co_proposed", "voted", "statement", "committee_join"]


@dataclass(frozen=True)
class JourneyEvent:
    """timeline의 한 이벤트."""
    event_id: str
    date: str           # ISO 8601
    event_type: EventType
    title: str          # 한 줄 요약
    description: str    # 1-2 문장 부연
    related_id: Optional[str] = None  # bill_id / vote_id / session_id
    icon: str = ""      # UI hint


@dataclass(frozen=True)
class JourneyResult:
    person_id: str
    person_name: str
    party: Optional[str]
    term: int
    district: Optional[str]
    summary: str         # AI 요약 (PoC mock)
    events: list[JourneyEvent]
    stats: dict          # 카운트·분포


# ─── 합성 timeline seed (PDF 시그니처) ──────────────────────────────────────

def _hub_person_journey() -> JourneyResult:
    """허브 의원 (MONA_001)의 1분기 정치 여정 - 데모 메인 데이터."""
    events = [
        JourneyEvent(
            event_id="ev_001", date="2026-01-15", event_type="committee_join",
            title="과학기술정보방송통신위원회 합류",
            description="22대 국회 회기 시작과 함께 과방위 위원으로 활동 시작.",
            related_id="cmt_sci", icon="🏛",
        ),
        JourneyEvent(
            event_id="ev_002", date="2026-02-05", event_type="statement",
            title="AI 산업 진흥 종합 대책 필요성 발언",
            description="과학기술정보방송통신위원회 회의에서 AI 입법 종합 대책 마련을 촉구.",
            related_id="sess_22_001", icon="🎤",
        ),
        JourneyEvent(
            event_id="ev_003", date="2026-03-15", event_type="proposed",
            title="AI 산업 진흥 종합 대책 특별법 대표발의",
            description="과학기술정보방송통신위원회 소관. 산업 진흥 + 윤리 가이드라인 통합.",
            related_id="DEMO_AI_BILL_001", icon="📜",
        ),
        JourneyEvent(
            event_id="ev_004", date="2026-04-02", event_type="co_proposed",
            title="개인정보 보호법 일부개정법률안 공동발의",
            description="정무위 소속 의원들과 공동발의. 데이터 활용·보호 균형 사안.",
            related_id="PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3", icon="🤝",
        ),
        JourneyEvent(
            event_id="ev_005", date="2026-04-15", event_type="voted",
            title="AI 산업 진흥 특별법 본회의 표결 - 찬성",
            description="찬성 287명 중 본인 찬성. 양당 일치율 91%의 협력적 표결.",
            related_id="V_PRC_J2Y0J0X4J0E0R1G6L4Y4Q3I2_2026-04-15", icon="✅",
        ),
        JourneyEvent(
            event_id="ev_006", date="2026-04-22", event_type="statement",
            title="본회의 발언 - 양당 협력 입법 강조",
            description="AI 산업 진흥 특별법 통과 직후 본회의 발언. 정파 초월 협력 의제로 자리매김 강조.",
            related_id="sess_22_003", icon="🎤",
        ),
        JourneyEvent(
            event_id="ev_007", date="2026-05-02", event_type="voted",
            title="청년 주거지원 확대법 표결 - 찬성",
            description="양당 일치율 96% 협력 의제. 본인도 찬성 표결.",
            related_id="V_PRC_N6C4N4B8N4I4V5K0P8C8U7M6_2026-05-02", icon="✅",
        ),
        JourneyEvent(
            event_id="ev_008", date="2026-05-08", event_type="voted",
            title="데이터 산업 진흥법 표결 - 찬성",
            description="가결 (찬성 293). 본인 발의 분야(데이터·AI)와 직결.",
            related_id="V_PRC_O7D5O5C9O5J5W6L1Q9D9V8N7_2026-05-08", icon="✅",
        ),
    ]
    return JourneyResult(
        person_id="IWK63872",
        person_name="조배숙",
        party="더불어민주당",
        term=22,
        district="서울 강남구갑",
        summary=(
            "22대 국회 1분기 핵심 활동: AI 산업 진흥 종합 대책 특별법 대표발의(3/15) + "
            "양당 협력 표결 다수 참여(일치율 91% 사안 포함). 공동발의 네트워크의 허브 역할로 "
            "정파 초월 협력 패턴을 다수 보임. 과학기술정보방송통신위원회를 중심으로 데이터·AI "
            "분야 입법 활동 집중. (출처: 국회 OpenAPI 2026-01~05)"
        ),
        events=events,
        stats={
            "total_events": len(events),
            "proposed": 1,
            "co_proposed": 1,
            "voted": 3,
            "statements": 2,
            "committees": 1,
            "period_start": "2024-05-30",
            "period_end": "2026-05-08",
        },
    )


# 추가 인물 timeline (다른 패턴 시연용)
def _other_person_journey(person_id: str) -> JourneyResult:
    """다른 의원의 일반적인 1분기 활동 - 데모용 단순 timeline."""
    events = [
        JourneyEvent(
            event_id=f"{person_id}_ev_001", date="2026-02-10",
            event_type="committee_join",
            title="정무위원회 합류",
            description="22대 국회 회기 시작.",
            related_id="cmt_pol", icon="🏛",
        ),
        JourneyEvent(
            event_id=f"{person_id}_ev_002", date="2026-03-20",
            event_type="voted",
            title="AI 산업 진흥법 본회의 표결",
            description="찬성 표결 - 양당 협력 의제.",
            related_id="V_PRC_J2Y0J0X4J0E0R1G6L4Y4Q3I2_2026-04-15", icon="✅",
        ),
        JourneyEvent(
            event_id=f"{person_id}_ev_003", date="2026-04-25",
            event_type="co_proposed",
            title="개인정보 보호법 개정 공동발의",
            description="정무위 소속 의원들과 함께.",
            related_id="PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3", icon="🤝",
        ),
    ]
    return JourneyResult(
        person_id=person_id,
        person_name="김태년",
        party="국민의힘",
        term=22,
        district="부산 해운대구갑",
        summary=(
            f"{person_id} 의원의 22대 임기 활동: 정무위 중심 데이터·법무 분야 입법 활동. "
            "표결 3건 + 공동발의 1건 참여. (출처: 국회 OpenAPI 2026-01~05)"
        ),
        events=events,
        stats={
            "total_events": len(events),
            "proposed": 0,
            "co_proposed": 1,
            "voted": 1,
            "statements": 0,
            "committees": 1,
            "period_start": "2024-05-30",
            "period_end": "2026-04-25",
        },
    )


# ─── 공개 API ───────────────────────────────────────────────────────────────

def build_journey(person_id: str) -> Optional[JourneyResult]:
    """의원 정치 여정 timeline 구성.

    Phase 4e: ENABLE_NEPTUNE_REAL=true이면 real PROPOSED·CO_PROPOSED·VOTED Cypher query 사용.
    Fallback: 합성 fixture.
    """
    import os
    if os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            real = _build_real_journey(person_id)
            if real and real.events:
                return real
        except Exception as e:
            print(f"[journey_builder] real query fail: {type(e).__name__}: {e}, fallback to fixture", flush=True)

    # Fixture fallback
    if person_id == "IWK63872":
        return _hub_person_journey()
    if person_id.startswith("MONA_"):
        return _other_person_journey(person_id)
    return None


def _build_real_journey(person_id: str) -> Optional[JourneyResult]:
    """real PROPOSED + CO_PROPOSED + VOTED → 의원 timeline."""
    from api.services import neptune as nep

    # Step 1: Person 메타 (flat projection)
    pres = nep.open_cypher(
        "MATCH (p:Person {assembly_id: $pid}) "
        "RETURN p.name AS name, p.party_id AS party_id, p.district_id AS district_id "
        "LIMIT 1",
        parameters={"pid": person_id},
    )
    prows = pres.rows if hasattr(pres, "rows") else pres.get("results", [])
    if not prows:
        return None
    pr = prows[0]
    person_name = pr.get("name") or person_id
    party = pr.get("party_id")
    district = pr.get("district_id")

    events: list[JourneyEvent] = []

    # Step 2: PROPOSED events (대표 발의 — real source만, real-vote placeholder 제외)
    p_res = nep.open_cypher(
        "MATCH (p:Person {assembly_id: $pid})-[:PROPOSED]->(b:Bill) "
        "WHERE b.title IS NOT NULL AND b.title <> '' "
        "RETURN b.bill_id AS bid, b.title AS title, b.proposed_date AS dt "
        "ORDER BY b.proposed_date DESC LIMIT 10",
        parameters={"pid": person_id},
    )
    p_rows = p_res.rows if hasattr(p_res, "rows") else p_res.get("results", [])
    for i, r in enumerate(p_rows):
        events.append(JourneyEvent(
            event_id=f"ev_p_{i}",
            date=str(r.get("dt") or ""),
            event_type="proposed",
            title=f"[대표 발의] {r.get('title') or r.get('bid','?')}",
            description=f"의안 {r.get('bid','')}를 대표 발의.",
            related_id=r.get("bid"),
            icon="📝",
        ))

    # Step 3: CO_PROPOSED events (공동 발의 — real source만)
    cp_res = nep.open_cypher(
        "MATCH (p:Person {assembly_id: $pid})-[:CO_PROPOSED]->(b:Bill) "
        "WHERE b.title IS NOT NULL AND b.title <> '' "
        "RETURN b.bill_id AS bid, b.title AS title, b.proposed_date AS dt "
        "ORDER BY b.proposed_date DESC LIMIT 10",
        parameters={"pid": person_id},
    )
    cp_rows = cp_res.rows if hasattr(cp_res, "rows") else cp_res.get("results", [])
    for i, r in enumerate(cp_rows):
        events.append(JourneyEvent(
            event_id=f"ev_cp_{i}",
            date=str(r.get("dt") or ""),
            event_type="co_proposed",
            title=f"[공동 발의] {r.get('title') or r.get('bid')}",
            description=f"의안 {r.get('bid','')}에 공동 발의 참여.",
            related_id=r.get("bid"),
            icon="🤝",
        ))

    # Step 4: VOTED events (표결 — top 15)
    v_res = nep.open_cypher(
        "MATCH (p:Person {assembly_id: $pid})-[v:VOTED]->(b:Bill) "
        "RETURN b.bill_id AS bid, b.title AS title, v.value AS val, v.date AS dt "
        "ORDER BY v.date DESC LIMIT 15",
        parameters={"pid": person_id},
    )
    v_rows = v_res.rows if hasattr(v_res, "rows") else v_res.get("results", [])
    val_kr = {"yes": "찬성", "no": "반대", "abstain": "기권", "absent": "불참"}
    for i, r in enumerate(v_rows):
        vdate_raw = str(r.get("dt") or "")[:8]
        vdate = (
            f"{vdate_raw[:4]}-{vdate_raw[4:6]}-{vdate_raw[6:8]}"
            if len(vdate_raw) == 8 else vdate_raw
        )
        choice = val_kr.get(r.get("val") or "absent", r.get("val") or "?")
        events.append(JourneyEvent(
            event_id=f"ev_v_{i}",
            date=vdate,
            event_type="voted",
            title=f"[표결: {choice}] {r.get('title') or r.get('bid')}",
            description=f"의안 {r.get('bid','')}에 *{choice}* 투표.",
            related_id=r.get("bid"),
            icon="🗳️",
        ))

    # Sort events by date desc
    events.sort(key=lambda e: e.date or "", reverse=True)

    # Stats
    proposed_cnt = sum(1 for e in events if e.event_type == "proposed")
    co_proposed_cnt = sum(1 for e in events if e.event_type == "co_proposed")
    voted_cnt = sum(1 for e in events if e.event_type == "voted")
    dates = [e.date for e in events if e.date]
    period_start = min(dates) if dates else "2024-05-30"
    period_end = max(dates) if dates else "2026-05-20"

    stats = {
        "proposed": proposed_cnt,
        "co_proposed": co_proposed_cnt,
        "voted": voted_cnt,
        "statements": 0,
        "period_start": period_start,
        "period_end": period_end,
    }

    summary = (
        f"22대 임기 (2024-05 ~ 2026-05) {person_name} 의원 ({party}, {district}) "
        f"real timeline: 발의 {proposed_cnt}건 + 공동발의 {co_proposed_cnt}건 + 표결 {voted_cnt}건. "
        f"PROPOSED/CO_PROPOSED/VOTED 엣지 from Neptune (출처: 22대 임기 · 국회 OpenAPI + 합성 보강)."
    )

    return JourneyResult(
        person_id=person_id,
        person_name=person_name,
        party=party,
        term=22,
        district=district,
        summary=summary,
        events=events,
        stats=stats,
    )
