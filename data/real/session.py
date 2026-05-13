"""국회 OpenAPI 회의록 어댑터 - Session + Statement 두 노드 동시 생성.

엔드포인트: `nktulghyaivebdpnz` (회의록 통합).

실 API → 회의(Session) 1건 + 발언(Statement) N건.
Statement.content가 LLM 토픽 추출의 기본 입력이 됨 (시나리오 C·K·M·N).

References:
- 국회 OpenAPI nktulghyaivebdpnz
- data/schemas.py Session, Statement
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Iterator, Optional

from data.real._client import AssemblyClient, demo_mode
from data.schemas import Session, Statement

__all__ = ["fetch_sessions_and_statements", "SESSION_ENDPOINT"]


SESSION_ENDPOINT = os.environ.get("ASSEMBLY_API_SESSION_ENDPOINT", "nktulghyaivebdpnz")


# 회의 유형 정규화.
TYPE_MAP: dict[str, str] = {
    "본회의": "plenary",
    "상임위원회": "committee",
    "특별위원회": "committee",
}


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


def fetch_sessions_and_statements(
    *,
    age: int = 22,
    max_sessions: Optional[int] = None,
    client: Optional[AssemblyClient] = None,
) -> Iterator[Session | Statement]:
    """회의 + 발언 통합 generator.

    Yields:
        Session 1건당 Statement 1+건이 뒤따름. 라우터는 isinstance로 분기.
    """
    if demo_mode():
        yield from _demo_sessions_and_statements(max_sessions)
        return

    cli = client or AssemblyClient()
    params = {"AGE": str(age)} if age else None
    yielded_sessions = 0
    for row in cli.iter_all_pages(SESSION_ENDPOINT, p_size=50, params=params):
        session_id = str(row.get("CONFER_NUM", "") or row.get("SESSION_ID", "")).strip()
        if not session_id:
            continue
        raw_type = str(row.get("CONFER_KIND_NM", "") or "").strip()
        normalized = TYPE_MAP.get(raw_type, "committee")
        session = Session(
            session_id=session_id,
            type=normalized,  # type: ignore[arg-type]
            date=_parse_date(str(row.get("CONFER_DT", ""))),
            committee_id=(str(row.get("CMIT_CD", "") or "").strip() or None),
            source="real",
        )
        yield session

        # Statement는 별도 endpoint에서 가져와야 하지만, 일부 통합 API는 같이 반환.
        statements_blob = row.get("STATEMENTS", [])
        if isinstance(statements_blob, list):
            for s_row in statements_blob:
                yield _row_to_statement(s_row, session_id, session.date)

        yielded_sessions += 1
        if max_sessions is not None and yielded_sessions >= max_sessions:
            break


def _row_to_statement(row: dict, session_id: str, session_date: date) -> Statement:
    return Statement(
        statement_id=str(row.get("STMT_ID", "") or f"stmt_{session_id}_{abs(hash(row.get('CONTENT', ''))) % 10**8:08d}"),
        person_id=str(row.get("MONA_CD", "") or row.get("PERSON_ID", "")),
        session_id=session_id,
        date=session_date,
        content=str(row.get("CONTENT", "") or row.get("STMT_TXT", "")).strip(),
        sentiment=None,
        topics=[],
        source="real",
    )


def _demo_sessions_and_statements(max_sessions: Optional[int]) -> Iterator[Session | Statement]:
    """결정적 mock - 5 회의 × 발언 2-3건씩."""
    sessions = [
        ("sess_22_001", "plenary", "2026-04-15", None,
         [("MONA_001", "AI 산업 진흥을 위한 종합 대책 마련이 시급합니다."),
          ("MONA_002", "양당 협력을 통해 입법 절차를 신속히 진행하겠습니다.")]),
        ("sess_22_002", "committee", "2026-04-20", "cmt_pol",
         [("MONA_003", "개인정보 보호와 데이터 활용의 균형이 핵심입니다."),
          ("MONA_001", "보호 강화 조치를 우선 검토해야 합니다.")]),
        ("sess_22_003", "plenary", "2026-04-30", None,
         [("MONA_005", "표결 결과는 양당 일치율 62%로 협력적 의제로 정착했습니다.")]),
        ("sess_22_004", "committee", "2026-05-02", "cmt_sci",
         [("MONA_001", "디지털 콘텐츠 산업 진흥을 위해 추가 입법 검토 필요."),
          ("MONA_004", "재생에너지 의안과 연계해 종합 대책 마련을 권고합니다.")]),
        ("sess_22_005", "plenary", "2026-05-10", None,
         [("MONA_007", "청년 주거지원 확대법 통과를 환영합니다."),
          ("MONA_008", "후속 조치로 실행 예산 확보가 필요합니다.")]),
    ]
    count = 0
    for sid, stype, sdate, cmt_id, stmts in sessions:
        session_date = _parse_date(sdate)
        yield Session(
            session_id=sid,
            type=stype,  # type: ignore[arg-type]
            date=session_date,
            committee_id=cmt_id,
            source="real",
        )
        for stmt_idx, (person_id, content) in enumerate(stmts):
            yield Statement(
                statement_id=f"stmt_{sid}_{stmt_idx:02d}",
                person_id=person_id,
                session_id=sid,
                date=session_date,
                content=content,
                sentiment=None,
                topics=[],
                source="real",
            )
        count += 1
        if max_sessions is not None and count >= max_sessions:
            break
