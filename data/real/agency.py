"""국회 OpenAPI 국정감사 대상 기관 어댑터.

엔드포인트: `nbslryaivedhrfyer` (국정감사 대상기관 - PoC).

실 API → Pydantic Agency. 정부/공기업/헌법기관 분류.

References:
- 국회 OpenAPI 국정감사 관련
- data/schemas.py Agency
"""
from __future__ import annotations

import os
from typing import Iterator, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Agency

__all__ = ["fetch_agencies", "AGENCY_ENDPOINT"]


AGENCY_ENDPOINT = os.environ.get("ASSEMBLY_API_AGENCY_ENDPOINT", "nbslryaivedhrfyer")


# 기관 유형 정규화.
TYPE_MAP: dict[str, str] = {
    "정부부처": "government",
    "정부기관": "government",
    "공공기관": "public_enterprise",
    "공기업": "public_enterprise",
    "헌법기관": "constitutional_organ",
}


def _row_to_agency(row: dict) -> Agency:
    agency_id = str(row.get("AGENCY_CD", "") or row.get("ORG_CD", "")).strip()
    name = str(row.get("AGENCY_NM", "") or row.get("ORG_NM", "")).strip()
    raw_type = str(row.get("AGENCY_TYPE", "") or row.get("ORG_KIND_NM", "")).strip()
    normalized_type = TYPE_MAP.get(raw_type, "government")
    return Agency(
        agency_id=agency_id or f"agency_{abs(hash(name)) % 10**8:08d}",
        name=name,
        type=normalized_type,  # type: ignore[arg-type]
        source="real",
    )


def fetch_agencies(
    *,
    max_rows: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Agency]:
    """국정감사 대상 기관 목록."""
    if demo_mode():
        yield from _demo_agencies(max_rows)
        return
    cli = client or AssemblyClient()
    yielded = 0
    seen: set[str] = set()
    for row in cli.iter_all_pages(AGENCY_ENDPOINT, p_size=100):
        agency = _row_to_agency(row)
        if agency.agency_id in seen:
            continue
        seen.add(agency.agency_id)
        yield agency
        yielded += 1
        if max_rows is not None and yielded >= max_rows:
            break


def _demo_agencies(max_rows: Optional[int]) -> Iterator[Agency]:
    """결정적 mock - 다양한 부처·공기업·헌법기관."""
    samples = [
        {"AGENCY_CD": "ag_moe", "AGENCY_NM": "교육부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_mof", "AGENCY_NM": "기획재정부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_msit", "AGENCY_NM": "과학기술정보통신부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_motie", "AGENCY_NM": "산업통상자원부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_mohw", "AGENCY_NM": "보건복지부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_me", "AGENCY_NM": "환경부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_moel", "AGENCY_NM": "고용노동부", "AGENCY_TYPE": "정부부처"},
        {"AGENCY_CD": "ag_kepco", "AGENCY_NM": "한국전력공사", "AGENCY_TYPE": "공기업"},
        {"AGENCY_CD": "ag_korail", "AGENCY_NM": "한국철도공사", "AGENCY_TYPE": "공기업"},
        {"AGENCY_CD": "ag_bok", "AGENCY_NM": "한국은행", "AGENCY_TYPE": "공공기관"},
        {"AGENCY_CD": "ag_supreme", "AGENCY_NM": "대법원", "AGENCY_TYPE": "헌법기관"},
        {"AGENCY_CD": "ag_cci", "AGENCY_NM": "감사원", "AGENCY_TYPE": "헌법기관"},
    ]
    count = 0
    for row in samples:
        yield _row_to_agency(row)
        count += 1
        if max_rows is not None and count >= max_rows:
            break
