"""국회 OpenAPI 위원회 어댑터.

엔드포인트: `npffdutiapkzbfyvr` (위원회별 의원 현황 - 위원회·소속의원 매핑).
실 API → Pydantic Committee 노드.

References:
- 국회 OpenAPI npffdutiapkzbfyvr
- data/schemas.py Committee
"""
from __future__ import annotations

import os
from typing import Iterator, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Committee

__all__ = ["fetch_committees", "COMMITTEE_ENDPOINT"]


COMMITTEE_ENDPOINT = os.environ.get("ASSEMBLY_API_COMMITTEE_ENDPOINT", "npffdutiapkzbfyvr")


# 국회 위원회 유형 정규화.
TYPE_MAP: dict[str, str] = {
    "상임위원회": "standing",
    "특별위원회": "special",
    "상설특별위원회": "permanent",
}


def _row_to_committee(row: dict) -> Committee:
    cmt_id = str(row.get("CMIT_CD", "") or row.get("COMMITTEE_ID", "")).strip()
    name = str(row.get("CMIT_NM", "") or row.get("COMMITTEE_NM", "")).strip()
    raw_type = str(row.get("CMIT_KIND_NM", "") or "").strip()
    type_normalized = TYPE_MAP.get(raw_type, "standing")
    chair = (str(row.get("HG_NM", "") or row.get("CHAIRMAN_NM", "")).strip() or None)
    return Committee(
        committee_id=cmt_id or f"cmt_{abs(hash(name)) % 10**8:08d}",
        name=name,
        type=type_normalized,  # type: ignore[arg-type]
        chair_person_id=chair,
        source="real",
    )


def fetch_committees(
    *,
    age: int = 22,
    max_rows: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Committee]:
    """위원회 목록 페이징 조회."""
    if demo_mode():
        yield from _demo_committees(max_rows)
        return
    cli = client or AssemblyClient()
    params = {"AGE": str(age)} if age else None
    yielded = 0
    seen_ids: set[str] = set()
    for row in cli.iter_all_pages(COMMITTEE_ENDPOINT, p_size=100, params=params):
        committee = _row_to_committee(row)
        if committee.committee_id in seen_ids:
            continue
        seen_ids.add(committee.committee_id)
        yield committee
        yielded += 1
        if max_rows is not None and yielded >= max_rows:
            break


def _demo_committees(max_rows: Optional[int]) -> Iterator[Committee]:
    """결정적 mock 위원회. 22대 국회 주요 상임위·특별위 8개."""
    samples = [
        {"CMIT_CD": "cmt_sci", "CMIT_NM": "과학기술정보방송통신위원회",
         "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_pol", "CMIT_NM": "정무위원회", "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_cul", "CMIT_NM": "문화체육관광위원회", "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_ind", "CMIT_NM": "산업통상자원중소벤처기업위원회",
         "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_lnd", "CMIT_NM": "국토교통위원회", "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_hlt", "CMIT_NM": "보건복지위원회", "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_env", "CMIT_NM": "환경노동위원회", "CMIT_KIND_NM": "상임위원회"},
        {"CMIT_CD": "cmt_bud", "CMIT_NM": "예산결산특별위원회", "CMIT_KIND_NM": "특별위원회"},
    ]
    count = 0
    for row in samples:
        yield _row_to_committee(row)
        count += 1
        if max_rows is not None and count >= max_rows:
            break
