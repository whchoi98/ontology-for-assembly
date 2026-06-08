"""의원 디렉토리 + 랭킹 라우터 (kassembly 패턴).

엔드포인트:
- GET /api/members                    30 의원 메타 (이름·정당·지역구·사진·메트릭)
- GET /api/members/{assembly_id}      단일 의원 디테일
- GET /api/members/ranking/{metric}   메트릭 기준 정렬 (composite/plenary/bills/...)

ADR-0004 준수: 객관 지표만, 평가성 표현 없음. 정당명·이름은 공개 사실.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.services import member_directory

router = APIRouter(prefix="/api/members", tags=["members"])


# 허용된 정렬 메트릭 (whitelist - injection 방지)
ALLOWED_METRICS: tuple[str, ...] = (
    "composite_score",
    "plenary_attendance_pct",
    "committee_attendance_pct",
    "bills_proposed",
    "bills_co_proposed",
    "floor_votes",
    "party_alignment_pct",
    "statements",
    "media_mentions_30d",
)


class MemberAnalyticsModel(BaseModel):
    plenary_attendance_pct: float
    committee_attendance_pct: float
    bills_proposed: int
    bills_co_proposed: int
    floor_votes: int
    party_alignment_pct: float
    statements: int
    media_mentions_30d: int
    composite_score: float


class MemberInfoModel(BaseModel):
    assembly_id: str
    name: str
    party: str
    district: str
    district_type: str
    committee: Optional[str] = None
    reelection: str
    term: int
    profile_image_url: str
    analytics: MemberAnalyticsModel


class MemberListResponse(BaseModel):
    persona_id: str
    total: int
    members: list[MemberInfoModel]


class RankingEntryModel(BaseModel):
    rank: int
    member: MemberInfoModel
    metric_value: float


class RankingResponse(BaseModel):
    persona_id: str
    metric: str
    descending: bool
    top_n: int
    entries: list[RankingEntryModel]
    persona_note: str


def _to_model(m: member_directory.MemberInfo) -> MemberInfoModel:
    a = m.analytics
    return MemberInfoModel(
        assembly_id=m.assembly_id, name=m.name, party=m.party,
        district=m.district, district_type=m.district_type,
        committee=m.committee, reelection=m.reelection, term=m.term,
        profile_image_url=m.profile_image_url,
        analytics=MemberAnalyticsModel(
            plenary_attendance_pct=a.plenary_attendance_pct,
            committee_attendance_pct=a.committee_attendance_pct,
            bills_proposed=a.bills_proposed,
            bills_co_proposed=a.bills_co_proposed,
            floor_votes=a.floor_votes,
            party_alignment_pct=a.party_alignment_pct,
            statements=a.statements,
            media_mentions_30d=a.media_mentions_30d,
            composite_score=a.composite_score,
        ),
    )


def _persona_note(pid: str, metric: str) -> str:
    label = {
        "composite_score": "종합 활동 점수",
        "plenary_attendance_pct": "본회의 출석률",
        "committee_attendance_pct": "상임위 출석률",
        "bills_proposed": "발의 의안 수",
        "bills_co_proposed": "공동발의 수",
        "floor_votes": "본회의 표결 참여",
        "party_alignment_pct": "정당 다수 일치율",
        "statements": "발언 수",
        "media_mentions_30d": "최근 30일 언론 노출",
    }.get(metric, metric)
    if pid == "editorial":
        return f"{label} 상위 의원 - 단독 인터뷰·심층 취재 후보 (객관 지표 - 평가 X)."
    if pid == "data_ai":
        return f"{label} 분포 분석 - 이상치 의원 + 정당·지역구별 cross-tab 권장."
    if pid == "general_reader":
        return f"내 지역 의원이 어디쯤 있는지 한눈에 볼 수 있어요. {label} 기준 순위."
    if pid == "b2b":
        return f"응답의 entries[].metric_value 직접 활용. 시계열 추적 가능."
    return f"{label} 기준 정렬."


@router.get("", response_model=MemberListResponse)
def list_members(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> MemberListResponse:
    """30 의원 디렉토리."""
    pid = x_persona_id or "editorial"
    members = member_directory.list_members()
    return MemberListResponse(
        persona_id=pid,
        total=len(members),
        members=[_to_model(m) for m in members],
    )


@router.get("/ranking/{metric}", response_model=RankingResponse)
def ranking(
    metric: str,
    top_n: int = Query(20, ge=1, le=50),
    descending: bool = Query(True),
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> RankingResponse:
    """단일 메트릭 정렬 (kassembly 랭킹 패턴)."""
    pid = x_persona_id or "editorial"
    if metric not in ALLOWED_METRICS:
        raise HTTPException(400, f"metric must be one of {ALLOWED_METRICS}")
    top = member_directory.list_top_by_metric(metric=metric, top_n=top_n, descending=descending)
    return RankingResponse(
        persona_id=pid,
        metric=metric,
        descending=descending,
        top_n=top_n,
        entries=[
            RankingEntryModel(
                rank=i + 1,
                member=_to_model(m),
                metric_value=float(getattr(m.analytics, metric)),
            )
            for i, m in enumerate(top)
        ],
        persona_note=_persona_note(pid, metric),
    )


@router.get("/{assembly_id}", response_model=MemberInfoModel)
def get_member(
    assembly_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> MemberInfoModel:
    """단일 의원 디테일 + 메트릭."""
    real_id = member_directory.resolve_id(assembly_id)
    m = member_directory.get_member(real_id)
    if m is None:
        raise HTTPException(404, f"의원 '{assembly_id}' 없음")
    return _to_model(m)


class NewsItemModel(BaseModel):
    title: str
    link: str
    description: str
    pub_date: str
    source: str = "naver_news"


class MemberNewsResponse(BaseModel):
    member_id: str
    name: str
    query: str
    total: int
    items: list[NewsItemModel]


@router.get("/{assembly_id}/news", response_model=MemberNewsResponse)
def get_member_news(assembly_id: str, limit: int = 5) -> MemberNewsResponse:
    """의원 이름 기반 네이버 뉴스 검색 (인물 페이지 연관 기사 섹션).

    실 네이버 뉴스는 글로벌 DEMO_PUBLIC_MODE와 **독립** — 유효한 키가 주입돼 있으면
    (Secrets Manager → task env NAVER_NEWS_API_CLIENT_ID/SECRET) 데모 모드여도 실 기사를
    우선 사용한다. 'demo-mode' placeholder·미설정·호출 실패·결과 0건이면 결정적 mock으로
    fallback (출처 배지 mock_naver_news로 구분).
    (사용자 신고 2026-06-08: 데모 mock 기사가 실 기사처럼 보이고 링크가 무관 결과로 이동.)
    """
    import os
    import re
    import logging
    real_id = member_directory.resolve_id(assembly_id)
    m = member_directory.get_member(real_id)
    if m is None:
        raise HTTPException(404, f"의원 '{assembly_id}' 없음")

    items: list[NewsItemModel] = []
    client_id = os.environ.get("NAVER_NEWS_API_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_NEWS_API_CLIENT_SECRET", "")
    has_real_creds = (
        bool(client_id) and bool(client_secret)
        and client_id != "demo-mode" and client_secret != "demo-mode"
    )
    if has_real_creds:
        # 실 네이버 검색 API (DEMO_PUBLIC_MODE와 무관 — 키만 있으면 실 호출)
        try:
            import requests
            resp = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
                params={"query": f"{m.name} 의원", "display": limit, "sort": "date"},
                timeout=10,
            )
            resp.raise_for_status()
            for it in resp.json().get("items", []):
                items.append(NewsItemModel(
                    title=re.sub(r"<[^>]+>", "", it.get("title", "")),
                    link=it.get("link", ""),
                    description=re.sub(r"<[^>]+>", "", it.get("description", "")),
                    pub_date=it.get("pubDate", ""),
                ))
        except Exception:
            logging.getLogger("api.routers.members").warning(
                "naver news fetch failed for %s; falling back to mock", real_id, exc_info=True)
            items = []
    if not items:
        # 키 미설정 / placeholder / 실 호출 실패 / 결과 0건 → 결정적 mock fallback
        items = _mock_news_for(m.name, m.party, m.district, limit)

    return MemberNewsResponse(
        member_id=real_id, name=m.name, query=f"{m.name} 의원",
        total=len(items), items=items,
    )


def _mock_news_for(name: str, party: str, district: str, limit: int) -> list[NewsItemModel]:
    """ADR-0004 준수 mock: 평가성 표현 없이 객관 사실 패턴만."""
    from datetime import datetime, timedelta
    base = datetime.now()
    import urllib.parse
    templates = [
        (f"{name} 의원, {district} 지역 현안 간담회 개최",
         f"{name} 의원은 {district} 주민들과 지역 현안 논의 자리를 가졌다고 밝혔다."),
        (f"국회 본회의서 {name} 의원 발언 — 정책 우선순위 강조",
         f"{name} 의원이 본회의에서 정책 우선순위를 강조하며 발언했다."),
        (f"{name} 의원, 신규 법안 발의 — 산업계 관심",
         f"{name} 의원 발의 법안이 산업계와 시민단체의 관심을 받고 있다."),
        (f"상임위에서 {name} 의원, 데이터 거버넌스 질의",
         f"국회 상임위원회에서 {name} 의원이 데이터 거버넌스 관련 질의를 진행했다."),
        (f"{name} 의원실, 정책 토론회 공동주최",
         f"{name} 의원실이 학계·산업계 인사들과 정책 토론회를 공동주최했다."),
        (f"{name} 의원, 청년 정책 간담회 참석",
         f"{name} 의원이 청년 정책 관련 간담회에 참석해 의견을 청취했다."),
    ]
    items = []
    # 각 기사의 *title*을 검색 query로 → 각 기사가 *고유 검색 결과*로 이동.
    # 사용자 신고: 모든 연관 기사가 동일 의원 검색 결과로 → 기사별 unique link.
    for i, (title, desc) in enumerate(templates[:limit]):
        encoded_title = urllib.parse.quote(title)
        link = f"https://search.naver.com/search.naver?where=news&query={encoded_title}"
        items.append(NewsItemModel(
            title=title, link=link,
            description=desc,
            pub_date=(base - timedelta(days=i*2)).strftime("%a, %d %b %Y %H:%M:%S +0900"),
            source="mock_naver_news",
        ))
    return items
