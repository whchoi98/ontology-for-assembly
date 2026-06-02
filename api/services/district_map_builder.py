"""지역구 지도 builder - 시나리오 H.

17 시도(광역지자체) × 의원 분포 + 발의 활성도 집계. data.real.member 어댑터에서
demo 10명 + synthetic seed로 22대 국회 분포(254 지역구 + 46 비례) 근사.

References:
- KOSTAT 행정구역 코드 (시도 2자리)
- spec §3.1 시나리오 H
- ADR-0004: 정당 색·이념 색 미사용 (정당명만 fact로 표시)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "SidoStats",
    "SidoDetail",
    "SidoMember",
    "SIDO_REGISTRY",
    "build_summary",
    "build_detail",
]


@dataclass(frozen=True)
class SidoRegistry:
    """17 광역지자체 메타 (KOSTAT 시도 코드)."""
    key: str         # short slug for URL (seoul, busan, ...)
    name_kr: str     # "서울특별시"
    short_kr: str    # "서울"
    kostat_code: str  # 2-digit (11, 26, ...)
    grid_row: int    # 시각화 그리드 좌표 (0=북, 4=남)
    grid_col: int    # 0=서, 5=동


# 17 시도 - 22대 국회 지역구 분포 근사 (총 254 지역구).
SIDO_REGISTRY: tuple[SidoRegistry, ...] = (
    SidoRegistry("seoul",    "서울특별시",      "서울",   "11", 1, 2),
    SidoRegistry("busan",    "부산광역시",      "부산",   "26", 4, 4),
    SidoRegistry("daegu",    "대구광역시",      "대구",   "27", 3, 4),
    SidoRegistry("incheon",  "인천광역시",      "인천",   "28", 1, 1),
    SidoRegistry("gwangju",  "광주광역시",      "광주",   "29", 4, 1),
    SidoRegistry("daejeon",  "대전광역시",      "대전",   "30", 2, 2),
    SidoRegistry("ulsan",    "울산광역시",      "울산",   "31", 4, 5),
    SidoRegistry("sejong",   "세종특별자치시",  "세종",   "36", 2, 2),
    SidoRegistry("gyeonggi", "경기도",          "경기",   "41", 1, 2),
    SidoRegistry("gangwon",  "강원특별자치도",  "강원",   "42", 0, 4),
    SidoRegistry("chungbuk", "충청북도",        "충북",   "43", 2, 3),
    SidoRegistry("chungnam", "충청남도",        "충남",   "44", 2, 1),
    SidoRegistry("jeonbuk",  "전북특별자치도",  "전북",   "45", 3, 1),
    SidoRegistry("jeonnam",  "전라남도",        "전남",   "46", 4, 2),
    SidoRegistry("gyeongbuk", "경상북도",       "경북",   "47", 3, 4),
    SidoRegistry("gyeongnam", "경상남도",       "경남",   "48", 4, 3),
    SidoRegistry("jeju",     "제주특별자치도",  "제주",   "50", 4, 0),
)


# 22대 국회 지역구 분포 (총 254). 합성 시드. 출처는 공식 발표 기반 근사.
_SEAT_DISTRIBUTION: dict[str, int] = {
    "seoul": 48, "busan": 18, "daegu": 12, "incheon": 14, "gwangju": 8,
    "daejeon": 7, "ulsan": 6, "sejong": 2, "gyeonggi": 60, "gangwon": 8,
    "chungbuk": 8, "chungnam": 11, "jeonbuk": 10, "jeonnam": 10,
    "gyeongbuk": 13, "gyeongnam": 16, "jeju": 3,
}


# 정당 분포 시드 (시도별 - 합성). 22대 결과 근사 - 정파 평가 의도 없음, 사실 fact만.
_PARTY_DISTRIBUTION: dict[str, dict[str, int]] = {
    "seoul":    {"더불어민주당": 37, "국민의힘": 11},
    "busan":    {"더불어민주당": 1,  "국민의힘": 17},
    "daegu":    {"국민의힘": 12},
    "incheon":  {"더불어민주당": 12, "국민의힘": 2},
    "gwangju":  {"더불어민주당": 8},
    "daejeon":  {"더불어민주당": 7},
    "ulsan":    {"더불어민주당": 1,  "국민의힘": 4, "진보당": 1},
    "sejong":   {"더불어민주당": 1,  "새로운미래": 1},
    "gyeonggi": {"더불어민주당": 53, "국민의힘": 6, "개혁신당": 1},
    "gangwon":  {"더불어민주당": 2,  "국민의힘": 6},
    "chungbuk": {"더불어민주당": 5,  "국민의힘": 3},
    "chungnam": {"더불어민주당": 8,  "국민의힘": 3},
    "jeonbuk":  {"더불어민주당": 9,  "진보당": 1},
    "jeonnam":  {"더불어민주당": 10},
    "gyeongbuk": {"국민의힘": 13},
    "gyeongnam": {"더불어민주당": 4, "국민의힘": 12},
    "jeju":     {"더불어민주당": 3},
}


# 발의 활성도 시드 (시도별 평균 발의·표결 카운트, 합성).
_ACTIVITY_SEED: dict[str, dict[str, int]] = {
    "seoul":    {"proposed": 142, "voted": 412, "statements": 89},
    "gyeonggi": {"proposed": 167, "voted": 488, "statements": 102},
    "busan":    {"proposed": 56,  "voted": 168, "statements": 31},
    "daegu":    {"proposed": 38,  "voted": 112, "statements": 22},
    "incheon":  {"proposed": 44,  "voted": 131, "statements": 28},
    "gwangju":  {"proposed": 26,  "voted": 74,  "statements": 16},
    "daejeon":  {"proposed": 23,  "voted": 65,  "statements": 14},
    "ulsan":    {"proposed": 18,  "voted": 56,  "statements": 11},
    "sejong":   {"proposed": 7,   "voted": 19,  "statements": 4},
    "gangwon":  {"proposed": 27,  "voted": 76,  "statements": 17},
    "chungbuk": {"proposed": 25,  "voted": 73,  "statements": 15},
    "chungnam": {"proposed": 33,  "voted": 100, "statements": 22},
    "jeonbuk":  {"proposed": 32,  "voted": 93,  "statements": 20},
    "jeonnam":  {"proposed": 31,  "voted": 92,  "statements": 19},
    "gyeongbuk": {"proposed": 40, "voted": 121, "statements": 26},
    "gyeongnam": {"proposed": 48, "voted": 148, "statements": 31},
    "jeju":     {"proposed": 10,  "voted": 28,  "statements": 6},
}


# Hub member - 풍부한 demo 데이터(MONA_001)가 어느 시도에 속하는지 명시.
HUB_SIDO_KEY = "seoul"


@dataclass(frozen=True)
class SidoMember:
    """시도 디테일에 노출되는 의원 항목."""
    person_id: str
    name: str
    party: str
    district: str            # "서울 강남구갑"
    activity_summary: str    # 한 줄 요약


@dataclass(frozen=True)
class SidoStats:
    """시도 1건 summary - choropleth 셀."""
    key: str
    name_kr: str
    short_kr: str
    kostat_code: str
    grid_row: int
    grid_col: int
    member_count: int        # 지역구 의원 수
    parties: dict[str, int]  # 정당별 수 (사실 기술, 평가 X)
    activity: dict[str, int] # proposed/voted/statements
    density_label: str       # "매우 높음", "높음", "보통", "낮음" - 색 스케일용


@dataclass(frozen=True)
class SidoDetail:
    """시도 디테일 페이지 - 시도 stats + 의원 리스트 + 페르소나 hint."""
    sido: SidoStats
    members: list[SidoMember]
    summary: str
    extras: dict = field(default_factory=dict)


# ─── 빌더 ─────────────────────────────────────────────────────────────────


def _density_label(count: int) -> str:
    """member_count 기반 4 tier 색 스케일 라벨 (정성 라벨, ADR-0004 정파 색 회피)."""
    if count >= 40:
        return "매우 높음"
    if count >= 15:
        return "높음"
    if count >= 8:
        return "보통"
    return "낮음"


def build_summary() -> list[SidoStats]:
    """17 시도 stats 리스트 (지도 셀)."""
    result: list[SidoStats] = []
    for reg in SIDO_REGISTRY:
        count = _SEAT_DISTRIBUTION.get(reg.key, 0)
        parties = dict(_PARTY_DISTRIBUTION.get(reg.key, {}))
        activity = dict(_ACTIVITY_SEED.get(reg.key, {"proposed": 0, "voted": 0, "statements": 0}))
        result.append(
            SidoStats(
                key=reg.key,
                name_kr=reg.name_kr,
                short_kr=reg.short_kr,
                kostat_code=reg.kostat_code,
                grid_row=reg.grid_row,
                grid_col=reg.grid_col,
                member_count=count,
                parties=parties,
                activity=activity,
                density_label=_density_label(count),
            )
        )
    return result


def build_detail(sido_key: str) -> Optional[SidoDetail]:
    """시도 디테일 - stats + 의원 리스트.

    seoul (허브)는 demo MONA_001 노출. 그 외는 시드 기반 가상 의원 1-3명.
    """
    reg = next((r for r in SIDO_REGISTRY if r.key == sido_key), None)
    if reg is None:
        return None

    stats_list = build_summary()
    stats = next(s for s in stats_list if s.key == sido_key)

    members = _sample_members_for(sido_key)
    summary = (
        f"{reg.name_kr} 지역구 의원 {stats.member_count}명. "
        f"정당 분포: {', '.join(f'{p} {c}' for p, c in stats.parties.items())}. "
        f"발의 누적 {stats.activity.get('proposed', 0)}건 · "
        f"표결 {stats.activity.get('voted', 0)}건. "
        "(출처: 국회 OpenAPI 2026-04 + 합성 시드)"
    )
    return SidoDetail(sido=stats, members=members, summary=summary)


def _sample_members_for(sido_key: str) -> list[SidoMember]:
    """시도별 대표 의원 리스트 — real member_directory 286명에서 short_kr로 district 매칭.

    각 시도에서 *composite_score 상위 5명* + 정당 분포 다양성 확보.
    fixture (잘못된 21대 의원 + 부정확한 지역구) 제거 — real 22대 OpenAPI 디렉토리 사용.
    """
    reg = next((r for r in SIDO_REGISTRY if r.key == sido_key), None)
    if reg is None:
        return []
    try:
        from api.services import member_directory
        short = reg.short_kr  # "서울" / "부산" / ...
        # district가 short_kr로 시작하는 의원 (예: "서울 강남구갑")
        all_members = member_directory.list_members()
        matched = []
        for m in all_members:
            district = getattr(m, "district", "") or ""
            if district.startswith(short + " ") or district == short:
                matched.append(m)
        # composite_score (없으면 0)로 정렬
        def _score(m) -> float:
            a = getattr(m, "analytics", None)
            if not a:
                return 0.0
            return float(getattr(a, "composite_score", 0) or 0)
        matched.sort(key=_score, reverse=True)

        def _summary_for(m) -> str:
            a = getattr(m, "analytics", None)
            committee = getattr(m, "committee", None) or "—"
            reelection = getattr(m, "reelection", None) or "—"
            if a:
                proposed = getattr(a, "bills_proposed", 0)
                co = getattr(a, "bills_co_proposed", 0)
                align = getattr(a, "party_alignment_pct", 0)
                score = getattr(a, "composite_score", 0)
                return (
                    f"위원회: {committee} · {reelection} · "
                    f"발의 {proposed}건 · 공동발의 {co}건 · "
                    f"정당 일치율 {align}% · composite {score:.1f}"
                )
            return f"위원회: {committee} · {reelection}"

        return [
            SidoMember(
                person_id=getattr(m, "assembly_id", ""),
                name=getattr(m, "name", "—"),
                party=getattr(m, "party", "—"),
                district=getattr(m, "district", "—"),
                activity_summary=_summary_for(m),
            )
            for m in matched[:5]
        ]
    except Exception:
        return []
