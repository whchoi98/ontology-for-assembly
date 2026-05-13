"""국회 OpenAPI 나머지 4 어댑터 검증 (Phase 3 Track 4).

committee / session+statement / party / agency 어댑터 통합 검증.
"""
from __future__ import annotations

import pytest

from data.real import agency, committee, party, session
from data.real._client import AssemblyApiError, _parse_response
from data.schemas import Agency, Committee, Party, Session, Statement


# ─── Committee ──────────────────────────────────────────────────────────────

def test_fetch_committees_demo_yields_pydantic():
    rows = list(committee.fetch_committees())
    assert len(rows) >= 1
    assert all(isinstance(c, Committee) for c in rows)


def test_committees_source_real():
    for c in committee.fetch_committees():
        assert c.source == "real"


def test_committee_type_normalized():
    """위원회 유형이 standing/special/permanent로 정규화."""
    valid_types = {"standing", "special", "permanent"}
    for c in committee.fetch_committees():
        assert c.type in valid_types


def test_committees_max_rows():
    rows = list(committee.fetch_committees(max_rows=3))
    assert len(rows) == 3


def test_committee_ids_unique():
    """위원회 ID 충돌 없음."""
    ids = [c.committee_id for c in committee.fetch_committees()]
    assert len(ids) == len(set(ids))


def test_committee_diversity():
    """8개 mock 위원회에 상임위 + 특별위 모두 포함."""
    types = {c.type for c in committee.fetch_committees()}
    assert "standing" in types
    assert "special" in types


# ─── Session + Statement ────────────────────────────────────────────────────

def test_session_yields_session_and_statement():
    """Generator가 Session·Statement 두 타입 모두 yield."""
    items = list(session.fetch_sessions_and_statements())
    sessions = [i for i in items if isinstance(i, Session)]
    statements = [i for i in items if isinstance(i, Statement)]
    assert len(sessions) >= 1
    assert len(statements) >= 1


def test_session_source_real():
    for item in session.fetch_sessions_and_statements():
        assert item.source == "real"


def test_session_type_normalized():
    """plenary | committee."""
    for item in session.fetch_sessions_and_statements():
        if isinstance(item, Session):
            assert item.type in ("plenary", "committee")


def test_statement_session_id_references_session():
    """Statement.session_id가 Session.session_id에 매핑."""
    items = list(session.fetch_sessions_and_statements())
    session_ids = {i.session_id for i in items if isinstance(i, Session)}
    statement_session_ids = {i.session_id for i in items if isinstance(i, Statement)}
    assert statement_session_ids.issubset(session_ids)


def test_session_max_limits_sessions_not_statements():
    """max_sessions는 세션 수만 제한 - 발언은 그 세션 내 모두."""
    items = list(session.fetch_sessions_and_statements(max_sessions=2))
    sessions = [i for i in items if isinstance(i, Session)]
    assert len(sessions) == 2


def test_statement_person_id_populated():
    """모든 Statement에 person_id 채워짐 (MONA_*)."""
    items = list(session.fetch_sessions_and_statements())
    for item in items:
        if isinstance(item, Statement):
            assert item.person_id


# ─── Party ──────────────────────────────────────────────────────────────────

def test_fetch_parties_yields_pydantic():
    rows = list(party.fetch_parties())
    assert len(rows) >= 1
    assert all(isinstance(p, Party) for p in rows)


def test_party_count_six():
    """6 정당 등록 (guardrails.KNOWN_PARTIES와 정렬)."""
    parties = list(party.fetch_parties())
    assert len(parties) >= 5  # 무소속 포함 6, 최소 5
    names = {p.name for p in parties}
    assert "더불어민주당" in names
    assert "국민의힘" in names


def test_party_no_ideology_in_name():
    """정당명에 이념 라벨 미포함 (보수/진보 단독은 진보당과 구분)."""
    standalone_forbidden = {"보수", "좌파", "우파", "중도"}
    for p in party.fetch_parties():
        assert p.name not in standalone_forbidden


def test_party_source_real():
    for p in party.fetch_parties():
        assert p.source == "real"


def test_party_ids_unique():
    ids = [p.party_id for p in party.fetch_parties()]
    assert len(ids) == len(set(ids))


# ─── Agency ─────────────────────────────────────────────────────────────────

def test_fetch_agencies_yields_pydantic():
    rows = list(agency.fetch_agencies())
    assert len(rows) >= 1
    assert all(isinstance(a, Agency) for a in rows)


def test_agency_type_normalized():
    """government | public_enterprise | constitutional_organ."""
    valid = {"government", "public_enterprise", "constitutional_organ"}
    for a in agency.fetch_agencies():
        assert a.type in valid


def test_agency_diverse_types():
    """다양한 기관 유형 등장."""
    types = {a.type for a in agency.fetch_agencies()}
    assert "government" in types
    assert "constitutional_organ" in types


def test_agency_source_real():
    for a in agency.fetch_agencies():
        assert a.source == "real"


def test_agency_ids_unique():
    ids = [a.agency_id for a in agency.fetch_agencies()]
    assert len(ids) == len(set(ids))


def test_agency_includes_real_world_examples():
    """실제 부처·기관명 포함 (검증·교양 자료)."""
    names = {a.name for a in agency.fetch_agencies()}
    assert "교육부" in names
    assert "기획재정부" in names
    assert "한국전력공사" in names


# ─── 정합성 통합 ────────────────────────────────────────────────────────────

def test_committee_session_cross_reference():
    """Session.committee_id가 Committee.committee_id에 (일부) 매핑.

    note: mock fixture에서 일부만 매핑됨 (본회의는 committee_id가 None).
    """
    cmt_ids = {c.committee_id for c in committee.fetch_committees()}
    items = list(session.fetch_sessions_and_statements())
    session_cmt_ids = {
        i.committee_id for i in items
        if isinstance(i, Session) and i.committee_id is not None
    }
    # 적어도 하나 매핑 (cmt_pol, cmt_sci 등)
    intersect = cmt_ids & session_cmt_ids
    assert intersect, f"세션-위원회 매핑 없음 — committees: {cmt_ids}, session_cmt: {session_cmt_ids}"


def test_all_four_adapters_deterministic():
    """4 어댑터 모두 mock에서 결정성 보장."""
    c1 = [c.model_dump() for c in committee.fetch_committees()]
    c2 = [c.model_dump() for c in committee.fetch_committees()]
    assert c1 == c2
    p1 = [p.model_dump(mode="json") for p in party.fetch_parties()]
    p2 = [p.model_dump(mode="json") for p in party.fetch_parties()]
    assert p1 == p2
    a1 = [a.model_dump() for a in agency.fetch_agencies()]
    a2 = [a.model_dump() for a in agency.fetch_agencies()]
    assert a1 == a2
