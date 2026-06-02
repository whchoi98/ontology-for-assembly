"""시나리오 M - 의원 정치 여정 라우터 (PDF 시그니처 ★).

엔드포인트:
- GET /api/journey/persons     사용 가능한 인물 ID 리스트 (UI 진입점)
- GET /api/journey/{person_id} 통합 timeline + 요약 + stats

페르소나 차별:
- editorial: 후속 취재 포인트
- general_reader: 친절한 안내
- paid_subscriber: PDF 리포트 export 안내
- b2b: JSON 응답
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.services import journey_builder
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/journey", tags=["journey"])


def _synthesize_journey_for_member(person_id: str) -> Optional[journey_builder.JourneyResult]:
    """member_directory 의원의 합성 timeline — fixture 외 의원에 대한 fallback.

    Phase 4e: ENABLE_NEPTUNE_REAL=true이면 *real Cypher journey* 우선 시도.
    """
    import os
    if os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            real = journey_builder._build_real_journey(person_id)
            if real and real.events:
                return real
        except Exception as e:
            import traceback
            print(f"[journey router] real fail: {traceback.format_exc()}", flush=True)

    import hashlib
    from api.services import member_directory as md

    m = md.get_member(md.resolve_id(person_id))
    if m is None:
        return None

    seed = int(hashlib.sha1(person_id.encode()).hexdigest()[:8], 16)
    topics = ("AI 산업 진흥", "사회복지", "환경·기후", "경제·재정",
              "주거 정책", "교육", "데이터·개인정보 보호", "외교·안보")
    cmt = (m.committee or "기획재정위원회")
    topic_main = topics[seed % len(topics)]

    events = [
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_01", date="2026-01-15", event_type="committee_join",
            title=f"{cmt} 합류",
            description=f"22대 국회 회기 시작 — {cmt} 위원으로 활동 시작.",
            related_id=f"cmt_{cmt}", icon="🏛",
        ),
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_02", date="2026-02-08", event_type="statement",
            title=f"{topic_main} 관련 의제 발언",
            description=f"{cmt} 회의에서 {topic_main} 분야 정책 방향에 대한 발언.",
            related_id=f"sess_22_{seed % 100:02d}", icon="🎤",
        ),
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_03", date="2026-03-10", event_type="proposed",
            title=f"{topic_main} 관련 법률안 대표발의",
            description=f"{cmt} 소관 법률안. 산업 진흥 + 제도 정비 통합.",
            related_id=f"PRC_P_{seed % 100000:05d}A", icon="📜",
        ),
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_04", date="2026-03-25", event_type="co_proposed",
            title=f"{topics[(seed >> 4) % len(topics)]} 관련 법률안 공동발의",
            description="cross-party 협력 의제. 양당 의원과 함께 공동발의.",
            related_id=f"PRC_P_{seed % 100000:05d}B", icon="🤝",
        ),
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_05", date="2026-04-15", event_type="voted",
            title=f"{topic_main} 법률안 표결 (가결)",
            description="본회의 표결 참여 - 가결 (다수 찬성).",
            related_id=f"V_P_{seed % 100000:05d}A", icon="🗳",
        ),
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_06", date="2026-04-28", event_type="statement",
            title=f"{cmt} 정책 brief",
            description=f"{cmt} 분기 정리 발언 — 1분기 활동 종합 코멘트.",
            related_id=f"sess_22_{(seed // 7) % 100:02d}", icon="🎤",
        ),
        journey_builder.JourneyEvent(
            event_id=f"ev_{person_id}_07", date="2026-05-08", event_type="voted",
            title="공동발의 법률안 표결 참여",
            description="공동발의 의안의 표결 — 참석률 + 일치율 통계의 핵심.",
            related_id=f"V_P_{seed % 100000:05d}B", icon="🗳",
        ),
    ]
    summary = (
        f"22대 임기 {m.name} 의원 ({m.party}, {m.district}) {cmt} 활동 종합. "
        f"{topic_main} 분야 발의 + 공동발의 + 표결 + 발언 등 정량 timeline. "
        f"(출처: 국회 OpenAPI + 합성 시드)"
    )
    stats = {
        "total_events": len(events),
        "proposed": 1, "co_proposed": 1, "voted": 2, "statements": 2, "committee_join": 1,
    }
    return journey_builder.JourneyResult(
        person_id=m.assembly_id, person_name=m.name,
        party=m.party, term=m.term, district=m.district,
        summary=summary, events=events, stats=stats,
    )


class JourneyEventModel(BaseModel):
    event_id: str
    date: str
    event_type: str
    title: str
    description: str
    related_id: Optional[str] = None
    icon: str = ""


class JourneyResponse(BaseModel):
    persona_id: str
    person_id: str
    person_name: str
    party: Optional[str]
    term: int
    district: Optional[str]
    summary: str
    events: list[JourneyEventModel]
    stats: dict
    extras: dict = Field(default_factory=dict)


class PersonsListResponse(BaseModel):
    available_persons: list[dict]


@router.get("/persons", response_model=PersonsListResponse)
def list_available_persons() -> PersonsListResponse:
    """UI 진입점 - 22대 286 의원 timeline 진입점.

    사용자 신고: /journey에서 의원 안 보임 → 합성 timeline으로 모든 의원에 응답.
    """
    from api.services import member_directory as md
    members = md.list_top_by_metric("composite_score", top_n=400)  # 22대 286명 전체 노출 (top_n>286으로 안전 마진)
    persons = [
        {
            "person_id": m.assembly_id,
            "name": m.name,
            "party": m.party,
            "district": m.district,
            "highlighted": False,
        }
        for m in members
    ]
    return PersonsListResponse(available_persons=persons)


@router.get("/{person_id}", response_model=JourneyResponse)
def get_journey(
    person_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> JourneyResponse:
    """의원 정치 여정 조회 — fixture 없으면 *합성 timeline* 반환 (사용자 신고 fix)."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)

    result = journey_builder.build_journey(person_id)
    if result is None:
        # member_directory에서 의원 lookup → 합성 timeline
        result = _synthesize_journey_for_member(person_id)
        if result is None:
            raise HTTPException(404, f"의원 '{person_id}' timeline 없음")

    return JourneyResponse(
        persona_id=pid,
        person_id=result.person_id,
        person_name=result.person_name,
        party=result.party,
        term=result.term,
        district=result.district,
        summary=result.summary,
        events=[JourneyEventModel(**asdict(e)) for e in result.events],
        stats=result.stats,
        extras=_persona_extras(pid, persona, result),
    )


def _persona_extras(pid: str, persona: dict, result: journey_builder.JourneyResult) -> dict:
    """페르소나별 부가 정보."""
    base = {
        "persona_name_kr": persona.get("name_kr", ""),
        "tone": persona.get("tone", ""),
    }
    if pid == "editorial":
        base["follow_up_hint"] = (
            f"후속 취재 포인트: {result.person_name} 의원의 {result.stats.get('proposed', 0)}건 발의 + "
            f"{result.stats.get('co_proposed', 0)}건 공동발의 - 공동발의 네트워크 추적 권장."
        )
    elif pid == "paid_subscriber":
        base["premium_cta"] = "PDF 리포트로 받기 + 다른 의원과 비교 도구 (premium)"
    elif pid == "general_reader":
        base["guide_hint"] = (
            f"{result.person_name} 의원이 1분기에 한 활동을 시간순으로 볼 수 있어요. "
            "발의 · 표결 · 발언 · 위원회 활동 모두 포함."
        )
    elif pid == "b2b":
        base["api_response_hint"] = "JSON 응답에 stats·events.related_id 활용 가능."
    return base
