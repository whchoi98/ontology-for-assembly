"""국회 OpenAPI 표결 어댑터 - data/real/vote.py.

엔드포인트: `nojepdqqaweusdfbi` (본회의 표결정보).

실 API → Pydantic Vote 매핑:
- BILL_ID        → bill_id
- VOTE_DATE      → date
- PROC_RESULT_CD → result (passed/rejected/withdrawn)
- ATTEND_NUM     → attendance_count

각 row는 1 의안 × 1 표결 = 1 Vote 노드. 개별 의원 선택(yes/no/abstain/absent)은
관계 속성(VOTED choice)에 별도 저장 - vote_choice() 헬퍼 참조.

References:
- 국회 OpenAPI nojepdqqaweusdfbi
- data/schemas.py Vote, VoteChoice, VoteResult
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Iterator, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Vote, VoteResult

__all__ = ["fetch_votes", "VOTE_ENDPOINT", "RESULT_MAP"]


VOTE_ENDPOINT = os.environ.get("ASSEMBLY_API_VOTE_ENDPOINT", "nojepdqqaweusdfbi")


# 처리 결과 → VoteResult 정규화.
RESULT_MAP: dict[str, VoteResult] = {
    "가결": "passed",
    "원안가결": "passed",
    "수정가결": "passed",
    "통과": "passed",
    "부결": "rejected",
    "폐기": "rejected",
    "철회": "withdrawn",
    "취소": "withdrawn",
}


def _normalize_result(value: str) -> VoteResult:
    return RESULT_MAP.get((value or "").strip(), "passed")


def _parse_date(value: str) -> date:
    if not value:
        return date.today()
    value = value.strip().replace(".", "-").replace("/", "-")
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return date.today()


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, AttributeError):
        return default


def _row_to_vote(row: dict) -> Vote:
    """국회 API row → Pydantic Vote.

    vote_id는 BILL_ID + VOTE_DATE 조합으로 deterministic.
    """
    bill_id = str(row.get("BILL_ID", "")).strip()
    vote_date_str = str(row.get("VOTE_DATE", "")).strip()
    vote_date = _parse_date(vote_date_str)
    # vote_id: 한 의안에 여러 표결이 있을 수 있으므로 BILL_ID + DATE 조합
    vote_id = f"V_{bill_id}_{vote_date.isoformat()}"
    return Vote(
        vote_id=vote_id,
        bill_id=bill_id,
        date=vote_date,
        result=_normalize_result(str(row.get("PROC_RESULT_CD", ""))),
        attendance_count=_safe_int(row.get("ATTEND_NUM"), default=0),
        source="real",
    )


def fetch_votes(
    *,
    age: int = 22,
    max_rows: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Vote]:
    """본회의 표결 페이징 조회.

    Args:
        age: 회기.
        max_rows: 최대 row 수.
        client: 테스트 클라이언트.

    Yields:
        Vote nodes (source="real").
    """
    if demo_mode():
        yield from _demo_votes(age=age, max_rows=max_rows)
        return

    cli = client or AssemblyClient()
    params = {"AGE": str(age)} if age else None

    yielded = 0
    for row in cli.iter_all_pages(VOTE_ENDPOINT, p_size=100, params=params):
        yield _row_to_vote(row)
        yielded += 1
        if max_rows is not None and yielded >= max_rows:
            break


# ─── Demo mock fixture ──────────────────────────────────────────────────────

def _demo_votes(age: int, max_rows: Optional[int]) -> Iterator[Vote]:
    """결정적 mock 표결. bill 어댑터의 BILL_ID와 매핑.

    결과 분포: passed 7건, rejected 2건, withdrawn 1건 (균형).
    """
    samples = [
        {"BILL_ID": "PRC_J2Y0J0X4J0E0R1G6L4Y4Q3I2", "VOTE_DATE": "2026-04-15",
         "PROC_RESULT_CD": "가결", "ATTEND_NUM": "287"},
        {"BILL_ID": "PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3", "VOTE_DATE": "2026-04-22",
         "PROC_RESULT_CD": "원안가결", "ATTEND_NUM": "291"},
        {"BILL_ID": "PRC_M5B3M3A7M3H3U4J9O7B7T6L5", "VOTE_DATE": "2026-04-25",
         "PROC_RESULT_CD": "수정가결", "ATTEND_NUM": "285"},
        {"BILL_ID": "PRC_N6C4N4B8N4I4V5K0P8C8U7M6", "VOTE_DATE": "2026-05-02",
         "PROC_RESULT_CD": "가결", "ATTEND_NUM": "289"},
        {"BILL_ID": "PRC_O7D5O5C9O5J5W6L1Q9D9V8N7", "VOTE_DATE": "2026-05-08",
         "PROC_RESULT_CD": "원안가결", "ATTEND_NUM": "293"},
        {"BILL_ID": "PRC_P8E6P6D0P6K6X7M2R0E0W9O8", "VOTE_DATE": "2026-05-06",
         "PROC_RESULT_CD": "가결", "ATTEND_NUM": "286"},
        {"BILL_ID": "PRC_R0G8R8F2R8M8Z9O4T2G2Y1Q0", "VOTE_DATE": "2026-05-09",
         "PROC_RESULT_CD": "가결", "ATTEND_NUM": "290"},
        {"BILL_ID": "PRC_Q9F7Q7E1Q7L7Y8N3S1F1X0P9", "VOTE_DATE": "2026-04-30",
         "PROC_RESULT_CD": "철회", "ATTEND_NUM": "0"},
        {"BILL_ID": "PRC_S1H9S9G3S9N9A0P5U3H3Z2R1", "VOTE_DATE": "2026-05-10",
         "PROC_RESULT_CD": "부결", "ATTEND_NUM": "284"},
        {"BILL_ID": "PRC_L4A2L2Z6L2G2T3I8N6A6S5K4", "VOTE_DATE": "2026-05-11",
         "PROC_RESULT_CD": "부결", "ATTEND_NUM": "281"},
    ]
    count = 0
    for row in samples:
        yield _row_to_vote(row)
        count += 1
        if max_rows is not None and count >= max_rows:
            break
