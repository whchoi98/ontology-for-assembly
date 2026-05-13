"""국회 OpenAPI 정당 어댑터.

엔드포인트: 국회 의원·당적 정보 또는 ALLBILL 결합. PoC는 합성·정규화된 6 정당 fixture.
정당 목록은 자주 변하지 않으므로 캐싱 적합.

References:
- 정당 정식 등록명 카탈로그 (이념 라벨 0개)
- data/schemas.py Party
"""
from __future__ import annotations

import os
from datetime import date
from typing import Iterator, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Party

__all__ = ["fetch_parties", "PARTY_ENDPOINT"]


PARTY_ENDPOINT = os.environ.get("ASSEMBLY_API_PARTY_ENDPOINT", "nyozqwxvtfpfknpqz")


def _row_to_party(row: dict) -> Party:
    party_id = str(row.get("POLY_CD", "") or row.get("PARTY_ID", "")).strip()
    name = str(row.get("POLY_NM", "") or row.get("PARTY_NM", "")).strip()
    return Party(
        party_id=party_id or f"party_{abs(hash(name)) % 10**8:08d}",
        name=name,
        founded_date=None,
        source="real",
    )


def fetch_parties(
    *,
    max_rows: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Party]:
    """정당 목록 조회."""
    if demo_mode():
        yield from _demo_parties(max_rows)
        return
    cli = client or AssemblyClient()
    yielded = 0
    seen: set[str] = set()
    for row in cli.iter_all_pages(PARTY_ENDPOINT, p_size=50):
        party = _row_to_party(row)
        if party.party_id in seen:
            continue
        seen.add(party.party_id)
        yield party
        yielded += 1
        if max_rows is not None and yielded >= max_rows:
            break


def _demo_parties(max_rows: Optional[int]) -> Iterator[Party]:
    """결정적 mock - guardrails.KNOWN_PARTIES와 정렬."""
    samples = [
        {"POLY_CD": "p_dpk", "POLY_NM": "더불어민주당"},
        {"POLY_CD": "p_ppp", "POLY_NM": "국민의힘"},
        {"POLY_CD": "p_jp", "POLY_NM": "정의당"},
        {"POLY_CD": "p_pp", "POLY_NM": "진보당"},
        {"POLY_CD": "p_rp", "POLY_NM": "개혁신당"},
        {"POLY_CD": "p_ind", "POLY_NM": "무소속"},
    ]
    count = 0
    for row in samples:
        yield _row_to_party(row)
        count += 1
        if max_rows is not None and count >= max_rows:
            break
