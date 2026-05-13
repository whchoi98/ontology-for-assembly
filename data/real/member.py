"""국회 OpenAPI 의원 어댑터 - data/real/member.py.

엔드포인트: `nwvrqwxyaytdsfvhu` (국회의원 현황).

실 API → Pydantic Person 매핑:
- MONA_CD       → assembly_id (의원 고유 ID)
- HG_NM         → name (한글 이름)
- POLY_NM       → party_id (정당 - 별도 lookup 필요, 임시로 name 사용)
- ORIG_NM       → district_id (지역구 - 별도 KOSTAT 코드 변환 필요)
- ELECT_GBN_NM  → election_district_type (지역구/비례)

References:
- 국회 OpenAPI nwvrqwxyaytdsfvhu
- data/schemas.py Person
"""
from __future__ import annotations

import os
from typing import Iterator, Literal, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Person

__all__ = ["fetch_members", "MEMBER_ENDPOINT"]


MEMBER_ENDPOINT = os.environ.get("ASSEMBLY_API_MEMBER_ENDPOINT", "nwvrqwxyaytdsfvhu")


# 지역구 유형 정규화.
DISTRICT_TYPE_MAP: dict[str, Literal["constituency", "proportional"]] = {
    "지역구": "constituency",
    "비례대표": "proportional",
    "비례": "proportional",
}


def _row_to_person(row: dict, term: int = 22) -> Person:
    """국회 API row → Pydantic Person.

    party_id·district_id는 임시로 이름 그대로 사용. Phase 3에서 표준 코드 매핑 추가.
    """
    elect_kind = str(row.get("ELECT_GBN_NM", "") or "").strip()
    return Person(
        assembly_id=str(row.get("MONA_CD", "")).strip(),
        name=str(row.get("HG_NM", "")).strip(),
        term=term,
        district_id=(str(row.get("ORIG_NM", "") or "").strip() or None),
        party_id=(str(row.get("POLY_NM", "") or "").strip() or None),
        profile_image_url=None,  # API에 직접 노출 안 됨 - 별도 endpoint 필요
        election_district_type=DISTRICT_TYPE_MAP.get(elect_kind),
        source="real",
    )


def fetch_members(
    *,
    term: int = 22,
    max_rows: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Person]:
    """현역 국회의원 페이징 조회.

    Args:
        term: 회기 (기본 22대).
        max_rows: 최대 가져올 의원 수.
        client: 테스트용 사용자 클라이언트.

    Yields:
        Person nodes (source="real").
    """
    if demo_mode():
        yield from _demo_members(term=term, max_rows=max_rows)
        return

    cli = client or AssemblyClient()
    yielded = 0
    for row in cli.iter_all_pages(MEMBER_ENDPOINT, p_size=100):
        yield _row_to_person(row, term=term)
        yielded += 1
        if max_rows is not None and yielded >= max_rows:
            break


# ─── Demo mock fixture ──────────────────────────────────────────────────────

def _demo_members(term: int, max_rows: Optional[int]) -> Iterator[Person]:
    """결정적 mock 의원. 합성 generator의 MONA_001-MONA_100과 호환 형식.

    정당 분포 균형 (5/3/2 비율 가까이).
    """
    samples = [
        {"MONA_CD": "MONA_001", "HG_NM": "○○○", "POLY_NM": "더불어민주당",
         "ORIG_NM": "서울 강남구갑", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_002", "HG_NM": "△△△", "POLY_NM": "국민의힘",
         "ORIG_NM": "부산 해운대구갑", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_003", "HG_NM": "□□□", "POLY_NM": "더불어민주당",
         "ORIG_NM": "경기 성남시분당구", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_004", "HG_NM": "◇◇◇", "POLY_NM": "정의당",
         "ORIG_NM": "비례대표", "ELECT_GBN_NM": "비례대표"},
        {"MONA_CD": "MONA_005", "HG_NM": "▽▽▽", "POLY_NM": "국민의힘",
         "ORIG_NM": "대구 수성구갑", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_006", "HG_NM": "▲▲▲", "POLY_NM": "더불어민주당",
         "ORIG_NM": "전북 전주시갑", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_007", "HG_NM": "●●●", "POLY_NM": "개혁신당",
         "ORIG_NM": "비례대표", "ELECT_GBN_NM": "비례대표"},
        {"MONA_CD": "MONA_008", "HG_NM": "◆◆◆", "POLY_NM": "국민의힘",
         "ORIG_NM": "인천 연수구갑", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_009", "HG_NM": "★★★", "POLY_NM": "더불어민주당",
         "ORIG_NM": "광주 서구갑", "ELECT_GBN_NM": "지역구"},
        {"MONA_CD": "MONA_010", "HG_NM": "☆☆☆", "POLY_NM": "무소속",
         "ORIG_NM": "강원 춘천시", "ELECT_GBN_NM": "지역구"},
    ]
    count = 0
    for row in samples:
        yield _row_to_person(row, term=term)
        count += 1
        if max_rows is not None and count >= max_rows:
            break
