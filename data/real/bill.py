"""국회 OpenAPI 의안 어댑터 - data/real/bill.py.

엔드포인트: `nzmimeepazxkubdpn` (의안처리상황). 환경별 override 가능.

실 API → Pydantic Bill 모델 매핑:
- BILL_ID         → bill_id
- BILL_NM         → title
- PROPOSE_DT      → proposed_date
- PROC_RESULT     → status (정규화)
- COMMITTEE       → category (소관위원회로 카테고리 추론)
- DETAIL_LINK     → full_text_url
- PROPOSER_KIND   → 메타

Demo mode (DEMO_PUBLIC_MODE=true): 합성 generator와 호환되는 mock fixture.

References:
- 국회 OpenAPI nzmimeepazxkubdpn https://open.assembly.go.kr
- data/schemas.py Bill, BillStatus
- ADR-0001 (gcc data/real 어댑터 패턴 차용)
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Iterator, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Bill, BillStatus

__all__ = ["fetch_bills", "BILL_ENDPOINT"]


# 엔드포인트 코드 (환경 변수 override 가능).
BILL_ENDPOINT = os.environ.get("ASSEMBLY_API_BILL_ENDPOINT", "nzmimeepazxkubdpn")


# 처리 결과 → BillStatus 정규화 매핑.
STATUS_MAP: dict[str, BillStatus] = {
    "": "proposed",
    "접수": "proposed",
    "회부": "in_committee",
    "심사중": "in_committee",
    "상정": "in_plenary",
    "의결": "in_plenary",
    "가결": "passed",
    "원안가결": "passed",
    "수정가결": "passed",
    "대안반영폐기": "rejected",
    "부결": "rejected",
    "철회": "withdrawn",
    "폐기": "withdrawn",
}


def _normalize_status(proc_result: str) -> BillStatus:
    """국회 처리결과 문자열 → BillStatus enum."""
    result = (proc_result or "").strip()
    return STATUS_MAP.get(result, "proposed")


def _parse_date(value: str) -> date:
    """YYYY-MM-DD 또는 YYYYMMDD → date."""
    if not value:
        return date.today()
    value = value.strip().replace(".", "-").replace("/", "-")
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return date.today()


def _row_to_bill(row: dict) -> Bill:
    """국회 API row → Pydantic Bill."""
    return Bill(
        bill_id=str(row.get("BILL_ID", "")).strip(),
        title=str(row.get("BILL_NM", "")).strip(),
        proposed_date=_parse_date(str(row.get("PROPOSE_DT", ""))),
        status=_normalize_status(str(row.get("PROC_RESULT", ""))),
        category=str(row.get("COMMITTEE", "") or "").strip() or None,
        proposer_id=None,  # PROPOSER는 이름이라 별도 lookup 필요 - member 어댑터 연동
        summary_text=str(row.get("SUMMARY", "") or "").strip() or None,
        full_text_url=str(row.get("DETAIL_LINK", "") or "").strip() or None,
        source="real",
    )


def fetch_bills(
    *,
    age: int = 22,
    max_rows: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Bill]:
    """22대 회기 의안 처리 상황 페이징 조회.

    Args:
        age: 국회 회기 (기본 22).
        max_rows: 가져올 최대 row 수 (None = 전체).
        client: 사용자 지정 클라이언트 (테스트용).

    Yields:
        Bill — Pydantic 검증된 의안 노드 (source="real").

    Demo mode에서는 합성 fixture 반환 (실 API 호출 없음).
    """
    if demo_mode():
        yield from _demo_bills(age=age, max_rows=max_rows)
        return

    cli = client or AssemblyClient()
    params = {"AGE": str(age)} if age else None

    yielded = 0
    for row in cli.iter_all_pages(BILL_ENDPOINT, p_size=100, params=params):
        yield _row_to_bill(row)
        yielded += 1
        if max_rows is not None and yielded >= max_rows:
            break


# ─── Demo mode mock fixture ─────────────────────────────────────────────────

def _demo_bills(age: int, max_rows: Optional[int]) -> Iterator[Bill]:
    """결정적 mock 의안 - 합성 generator의 BILL_ID_POOL과 형식 일치.

    실 API JSON 구조는 자유롭지만 Pydantic Bill에 매핑한 결과는 항상 동일.
    """
    samples = [
        {
            "BILL_ID": "PRC_J2Y0J0X4J0E0R1G6L4Y4Q3I2",
            "BILL_NM": "인공지능 산업 진흥 및 활용 촉진에 관한 법률안",
            "PROPOSE_DT": "2026-03-15",
            "PROC_RESULT": "회부",
            "COMMITTEE": "과학기술정보방송통신위원회",
            "DETAIL_LINK": "https://likms.assembly.go.kr/bill/billDetail.do?billId=PRC_J2Y0J0X4J0E0R1G6L4Y4Q3I2",
        },
        {
            "BILL_ID": "PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3",
            "BILL_NM": "개인정보 보호법 일부개정법률안",
            "PROPOSE_DT": "2026-04-02",
            "PROC_RESULT": "상정",
            "COMMITTEE": "정무위원회",
            "DETAIL_LINK": "https://likms.assembly.go.kr/bill/billDetail.do?billId=PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3",
        },
        {
            "BILL_ID": "PRC_L4A2L2Z6L2G2T3I8N6A6S5K4",
            "BILL_NM": "디지털 콘텐츠 진흥에 관한 법률안",
            "PROPOSE_DT": "2026-04-10",
            "PROC_RESULT": "접수",
            "COMMITTEE": "문화체육관광위원회",
        },
        {
            "BILL_ID": "PRC_M5B3M3A7M3H3U4J9O7B7T6L5",
            "BILL_NM": "재생에너지 보급 확대 특별법안",
            "PROPOSE_DT": "2026-04-22",
            "PROC_RESULT": "심사중",
            "COMMITTEE": "산업통상자원중소벤처기업위원회",
        },
        {
            "BILL_ID": "PRC_N6C4N4B8N4I4V5K0P8C8U7M6",
            "BILL_NM": "청년 주거지원 확대법안",
            "PROPOSE_DT": "2026-05-01",
            "PROC_RESULT": "가결",
            "COMMITTEE": "국토교통위원회",
        },
        {
            "BILL_ID": "PRC_O7D5O5C9O5J5W6L1Q9D9V8N7",
            "BILL_NM": "데이터 산업 진흥법 일부개정법률안",
            "PROPOSE_DT": "2026-05-08",
            "PROC_RESULT": "원안가결",
            "COMMITTEE": "정무위원회",
        },
        {
            "BILL_ID": "PRC_P8E6P6D0P6K6X7M2R0E0W9O8",
            "BILL_NM": "사이버보안 강화법안",
            "PROPOSE_DT": "2026-04-28",
            "PROC_RESULT": "회부",
            "COMMITTEE": "과학기술정보방송통신위원회",
        },
        {
            "BILL_ID": "PRC_Q9F7Q7E1Q7L7Y8N3S1F1X0P9",
            "BILL_NM": "노동시간 단축 특례법안",
            "PROPOSE_DT": "2026-04-15",
            "PROC_RESULT": "철회",
            "COMMITTEE": "환경노동위원회",
        },
        {
            "BILL_ID": "PRC_R0G8R8F2R8M8Z9O4T2G2Y1Q0",
            "BILL_NM": "보건의료 데이터 활용 촉진법안",
            "PROPOSE_DT": "2026-04-05",
            "PROC_RESULT": "상정",
            "COMMITTEE": "보건복지위원회",
        },
        {
            "BILL_ID": "PRC_S1H9S9G3S9N9A0P5U3H3Z2R1",
            "BILL_NM": "지방자치단체 균형발전 지원 특별법안",
            "PROPOSE_DT": "2026-05-03",
            "PROC_RESULT": "심사중",
            "COMMITTEE": "행정안전위원회",
        },
    ]
    count = 0
    for row in samples:
        yield _row_to_bill(row)
        count += 1
        if max_rows is not None and count >= max_rows:
            break
