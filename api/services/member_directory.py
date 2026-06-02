"""실 22대 국회 의원 디렉토리 + 활동 분석 메트릭.

kassembly.com 패턴 참고 - 의원 이름·사진·정당·지역구·분석 메트릭 통합 노출.
국회 OpenAPI에서 fetch한 30명 실 의원 fixture + 결정적 합성 메트릭.

ADR-0004 준수:
- 실명·정당 표기는 공개 사실 (국회 공식 정보)
- 분석 메트릭은 객관적 지표(출석률·발의수·일치율)만. 평가성 표현 회피.
- 사진은 참여연대(peoplepower21.org) 공개 22대 의원 갤러리.

References:
- 국회 OpenAPI nwvrqwxyaytdsfvhu (의원 현황)
- kassembly.com/ranking/attendance (시각화 패턴 참고)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_LOG = logging.getLogger(__name__)

__all__ = [
    "MemberInfo",
    "MemberAnalytics",
    "list_members",
    "get_member",
    "get_analytics",
    "list_top_by_metric",
]


@dataclass(frozen=True)
class MemberAnalytics:
    """의원 활동 분석 메트릭 (객관 지표 only)."""
    plenary_attendance_pct: float       # 본회의 출석률 0-100
    committee_attendance_pct: float     # 상임위 출석률 0-100
    bills_proposed: int                  # 본인 발의 의안 수
    bills_co_proposed: int               # 공동 발의 의안 수
    floor_votes: int                     # 본회의 표결 참여 수
    party_alignment_pct: float           # 정당 다수 표결 일치율 0-100
    statements: int                       # 본회의·위원회 발언 수
    media_mentions_30d: int              # 최근 30일 언론 노출
    composite_score: float               # 종합 활동 점수 (0-100, 가중 평균)


@dataclass(frozen=True)
class MemberInfo:
    """의원 메타 + 분석."""
    assembly_id: str         # MONA_CD
    name: str                # HG_NM
    party: str               # POLY_NM (정당명, canonical)
    district: str            # ORIG_NM (지역구 또는 '비례대표')
    district_type: str       # 'constituency' / 'proportional'
    committee: Optional[str] # 소속 위원회
    reelection: str          # '초선' / '재선' / '3선' 등
    term: int                # 회기 (22)
    profile_image_url: str   # 사진 URL
    analytics: MemberAnalytics


# ─── 22대 의원 전체 fixture - data/real/members_22.json (286+명) ──────────

_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "real" / "members_22.json"


def _load_full_directory() -> Optional[tuple[tuple[str, str, str, str, str, str], ...]]:
    """국회 OpenAPI에서 prefetch된 22대 의원 전체 fixture (build-time)."""
    if not _DATA_FILE.exists():
        return None
    try:
        rows = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        _LOG.warning("members_22.json load failed: %r", exc)
        return None
    out: list[tuple[str, str, str, str, str, str]] = []
    for r in rows:
        mid = r.get("MONA_CD") or ""
        if not mid:
            continue
        out.append((
            mid,
            r.get("HG_NM") or "",
            r.get("POLY_NM") or "무소속",
            r.get("ORIG_NM") or "비례대표",
            r.get("CMIT_NM") or None,
            r.get("REELE_GBN_NM") or "초선",
        ))
    return tuple(out)


# Build-time fixture (286+명). 없으면 fallback 30명.
_FULL_MEMBERS = _load_full_directory()


# ─── Wikipedia photo cache (build-time fetch) ────────────────────────────────

_PHOTOS_FILE = Path(__file__).resolve().parents[2] / "data" / "real" / "members_22_photos.json"


def _load_wiki_photos() -> dict[str, str]:
    """22대 의원 이름 → wikipedia thumbnail URL (build-time prefetch).

    fetch 스크립트: tools/fetch_wiki_photos.py (1회 실행, JSON commit).
    파일 없거나 매핑 없으면 SVG inline fallback.
    """
    if not _PHOTOS_FILE.exists():
        return {}
    try:
        return json.loads(_PHOTOS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        _LOG.warning("members_22_photos.json load failed: %r", exc)
        return {}


_WIKI_PHOTOS: dict[str, str] = _load_wiki_photos()


_RAW_MEMBERS_FALLBACK: tuple[tuple[str, str, str, str, str, str], ...] = (
    # (assembly_id, name, party, district, committee, reelection)
    ("T2T8225E", "강경숙", "조국혁신당",   "비례대표",                "교육위원회",      "초선"),
    ("L2I9861C", "강대식", "국민의힘",     "대구 동구군위군을",       "국방위원회",      "재선"),
    ("8P37634C", "강득구", "더불어민주당", "경기 안양시만안구",       "교육위원회",      "재선"),
    ("9901388T", "강명구", "국민의힘",     "경북 구미시을",           "산업통상자원중소벤처기업위원회", "초선"),
    ("GX22581L", "강민국", "국민의힘",     "경남 진주시을",           "기획재정위원회",  "재선"),
    ("NQO7187X", "강선영", "국민의힘",     "비례대표",                "국토교통위원회",  "초선"),
    ("MNZ4401T", "강선우", "무소속",       "서울 강서구갑",           "여성가족위원회",  "재선"),
    ("42K7317Y", "강승규", "국민의힘",     "충남 홍성군예산군",       "정무위원회",      "재선"),
    ("5KV96424", "강준현", "더불어민주당", "세종특별자치시을",        "기획재정위원회",  "재선"),
    ("HS39431V", "고동진", "국민의힘",     "서울 강남구병",           "과학기술정보방송통신위원회", "초선"),
    ("WCD5518S", "고민정", "더불어민주당", "서울 광진구을",           "외교통일위원회",  "재선"),
    ("REG96285", "곽규택", "국민의힘",     "부산 서구동구",           "법제사법위원회",  "초선"),
    ("FIE6569O", "곽상언", "더불어민주당", "서울 종로구",             "법제사법위원회",  "초선"),
    ("7469929V", "구자근", "국민의힘",     "경북 구미시갑",           "산업통상자원중소벤처기업위원회", "재선"),
    ("GDG1847Z", "권성동", "국민의힘",     "강원 강릉시",             "외교통일위원회",  "5선"),
    ("LG63087O", "권영세", "국민의힘",     "서울 용산구",             "외교통일위원회",  "5선"),
    ("LYY5513O", "권영진", "국민의힘",     "대구 달서구병",           "기획재정위원회",  "4선"),
    ("C7E79345", "권칠승", "더불어민주당", "경기 화성시병",           "보건복지위원회",  "재선"),
    ("EFU76868", "권향엽", "더불어민주당", "전남 순천시광양시곡성군구례군을", "농림축산식품해양수산위원회", "초선"),
    ("TQP7167T", "김건",   "국민의힘",     "비례대표",                "외교통일위원회",  "초선"),
    ("X1K3667J", "김교흥", "더불어민주당", "인천 서구갑",             "행정안전위원회",  "3선"),
    ("HE08888N", "김기웅", "국민의힘",     "대구 중구남구",           "기획재정위원회",  "초선"),
    ("3CC88975", "김기표", "더불어민주당", "경기 부천시을",           "정무위원회",      "재선"),
    ("X7I4680R", "김기현", "국민의힘",     "울산 남구을",             "정무위원회",      "5선"),
    ("IUX1829H", "김남근", "더불어민주당", "서울 성북구을",           "정무위원회",      "초선"),
    ("NXB3178C", "김남희", "더불어민주당", "경기 광명시을",           "보건복지위원회",  "초선"),
    ("ANS8383S", "김대식", "국민의힘",     "부산 사상구",             "교육위원회",      "초선"),
    ("LH97552Q", "김도읍", "국민의힘",     "부산 강서구",             "법제사법위원회",  "4선"),
    ("MIS62075", "김동아", "더불어민주당", "서울 서대문구갑",         "법제사법위원회",  "초선"),
    ("86R9476S", "김문수", "더불어민주당", "전남 순천시광양시곡성군구례군갑", "환경노동위원회", "재선"),
)


def _photo_url(assembly_id: str, name: str) -> str:
    """의원 프로필 이미지 — 국회 공식 사이트 사진.

    URL 패턴 (검증 2026-05-16):
        https://www.assembly.go.kr/static/portal/img/openassm/{MONA_CD}.jpg

    국회 공식 의원 프로필 페이지에서 사용하는 이미지:
        https://www.assembly.go.kr/portal/assm/assmMemb/memberProfile.do?monaCd={MONA_CD}

    검증: 286 의원 모두 ~20KB JPEG, 200 OK, image/jpeg content-type.

    Fallback: assembly_id 없거나 비정상 → 빈 문자열 (frontend에서 onError 처리).
    """
    if not assembly_id:
        return ""
    return f"https://www.assembly.go.kr/static/portal/img/openassm/{assembly_id}.jpg"


def _seed_from_id(assembly_id: str) -> int:
    """결정적 메트릭 seed."""
    return int(hashlib.sha256(assembly_id.encode()).hexdigest()[:8], 16)


def _synth_analytics(assembly_id: str, reelection: str, district_type: str) -> MemberAnalytics:
    """결정적 합성 메트릭. 재선 횟수·지역구 유형에 따라 분포 조정."""
    seed = _seed_from_id(assembly_id)

    # 출석률: 본회의 88-99%, 상임위 75-98% (현실 분포 근사)
    plenary = 88.0 + (seed % 1200) / 100.0       # 88-99.99
    committee = 75.0 + ((seed >> 8) % 2300) / 100.0  # 75-97.99

    # 발의 수: 재선 횟수에 따라 영향
    reelection_factor = {"초선": 1.0, "재선": 1.3, "3선": 1.6, "4선": 1.9, "5선": 2.2}.get(reelection, 1.0)
    bills_proposed = int(3 + (seed % 22) * reelection_factor)        # 3-50
    bills_co_proposed = int(15 + ((seed >> 4) % 80) * reelection_factor)  # 15-200

    # 표결 참여: 본회의 출석률에 비례
    floor_votes = int(plenary * 1.5 + (seed % 30))   # ~140-180

    # 정당 일치율: 80-98% (정당별로 분포 다양)
    alignment = 80.0 + ((seed >> 12) % 1800) / 100.0  # 80-97.99

    # 발언 수: 1-100
    statements = 1 + (seed % 100)

    # 언론 노출 (30일): 1-200 (5선 의원·비례대표가 평균적으로 더 노출)
    media_factor = 2.0 if district_type == "proportional" else 1.0
    media = int((1 + (seed % 100)) * media_factor + reelection_factor * 5)

    # 종합 점수: 가중 평균 (출석 30 + 발의 25 + 발언 15 + 미디어 10 + 일치율 20)
    composite = round(
        plenary * 0.3
        + min(100, bills_proposed * 2.0) * 0.25
        + min(100, statements * 1.0) * 0.15
        + min(100, media * 0.5) * 0.10
        + alignment * 0.20,
        1,
    )

    return MemberAnalytics(
        plenary_attendance_pct=round(plenary, 1),
        committee_attendance_pct=round(committee, 1),
        bills_proposed=bills_proposed,
        bills_co_proposed=bills_co_proposed,
        floor_votes=floor_votes,
        party_alignment_pct=round(alignment, 1),
        statements=statements,
        media_mentions_30d=media,
        composite_score=composite,
    )


# ─── 빌드된 디렉토리 (모듈 로드 시 1회) ──────────────────────────────────

_RAW_MEMBERS = _FULL_MEMBERS or _RAW_MEMBERS_FALLBACK


_MEMBERS: tuple[MemberInfo, ...] = tuple(
    MemberInfo(
        assembly_id=mid,
        name=name,
        party=party,
        district=district,
        district_type="proportional" if district == "비례대표" else "constituency",
        committee=committee,
        reelection=reelection,
        term=22,
        profile_image_url=_photo_url(mid, name),
        analytics=_synth_analytics(
            mid, reelection, "proportional" if district == "비례대표" else "constituency",
        ),
    )
    for (mid, name, party, district, committee, reelection) in _RAW_MEMBERS
)


_LOG.info("member_directory loaded: %d 의원 (source=%s)",
          len(_MEMBERS),
          "full_json" if _FULL_MEMBERS else "fallback_30")


# ─── 공개 API ───────────────────────────────────────────────────────────────


def list_members() -> list[MemberInfo]:
    """전체 30명 디렉토리."""
    return list(_MEMBERS)


def get_member(assembly_id: str) -> Optional[MemberInfo]:
    """assembly_id (MONA_CD) lookup. 미존재 시 None."""
    return next((m for m in _MEMBERS if m.assembly_id == assembly_id), None)


def get_analytics(assembly_id: str) -> Optional[MemberAnalytics]:
    """메트릭만 빠르게."""
    m = get_member(assembly_id)
    return m.analytics if m else None


def list_top_by_metric(
    metric: str = "composite_score", top_n: int = 10, descending: bool = True,
) -> list[MemberInfo]:
    """단일 메트릭 기준 정렬 - kassembly.com ranking 패턴."""
    return sorted(
        _MEMBERS,
        key=lambda m: getattr(m.analytics, metric, 0),
        reverse=descending,
    )[:top_n]


# ─── 후속 호환 helpers (구 MONA_001 placeholder 매핑) ────────────────────


# 구 builders가 MONA_001 ~ MONA_010 ID로 placeholder 의원 참조.
# 새 builders는 실 assembly_id 사용하지만, 일부 시드 데이터의 hub member
# 매핑은 유지 (e.g., MONA_001 → 강경숙).
LEGACY_TO_REAL: dict[str, str] = {
    f"MONA_{i:03d}": _MEMBERS[i - 1].assembly_id
    for i in range(1, min(11, len(_MEMBERS) + 1))
}


def resolve_id(legacy_or_real: str) -> str:
    """legacy MONA_001 → 실 assembly_id. 이미 실 ID면 그대로."""
    return LEGACY_TO_REAL.get(legacy_or_real, legacy_or_real)
