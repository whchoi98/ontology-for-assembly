"""data.real 국회 OpenAPI 어댑터 통합 검증.

테스트 범위:
- _client AssemblyClient: API key 로딩, demo mode 분기, 응답 파싱
- bill: 의안 fetch + status 매핑 + 날짜 파싱
- member: 의원 fetch + 지역구/비례 분류
- vote: 표결 fetch + 결과 정규화

DEMO_PUBLIC_MODE=true (conftest 기본값) 하에서 mock fixture 사용 - 실 API 호출 없음.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

from data.real import bill, member, vote
from data.real._client import (
    AssemblyApiError,
    AssemblyClient,
    _parse_response,
    demo_mode,
)
from data.schemas import Bill, Person, Vote


# ─── _client (HTTP 클라이언트) ───────────────────────────────────────────────

def test_demo_mode_true_in_test_env():
    """conftest가 DEMO_PUBLIC_MODE=true 주입."""
    assert demo_mode() is True


def test_client_init_with_explicit_key():
    """API key 명시 시 정상 인스턴스화."""
    cli = AssemblyClient(api_key="test-key")
    assert cli.api_key == "test-key"


def test_client_default_base_url():
    cli = AssemblyClient(api_key="k")
    assert "open.assembly.go.kr" in cli.base_url


def test_parse_response_extracts_total_and_rows():
    """국회 API 표준 응답 → ApiResponse 변환."""
    payload = {
        "TEST_ENDPOINT": [
            {"head": [
                {"list_total_count": 42},
                {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}},
            ]},
            {"row": [{"a": 1}, {"a": 2}, {"a": 3}]},
        ]
    }
    result = _parse_response(payload, "TEST_ENDPOINT")
    assert result.total_count == 42
    assert result.result_code == "INFO-000"
    assert len(result.rows) == 3


def test_parse_response_no_data_code_info_200():
    """INFO-200 (해당 데이터 없음)도 정상 - 빈 rows로 반환."""
    payload = {
        "TEST_ENDPOINT": [
            {"head": [
                {"list_total_count": 0},
                {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당 데이터가 없습니다."}},
            ]},
        ]
    }
    result = _parse_response(payload, "TEST_ENDPOINT")
    assert result.result_code == "INFO-200"
    assert result.rows == []


def test_parse_response_error_code_raises():
    """비정상 CODE는 AssemblyApiError."""
    payload = {
        "TEST_ENDPOINT": [
            {"head": [{"RESULT": {"CODE": "ERROR-100", "MESSAGE": "key invalid"}}]},
        ]
    }
    with pytest.raises(AssemblyApiError, match="ERROR-100"):
        _parse_response(payload, "TEST_ENDPOINT")


def test_parse_response_unexpected_shape_raises():
    with pytest.raises(AssemblyApiError):
        _parse_response({}, "MISSING")


# ─── Bill 어댑터 ────────────────────────────────────────────────────────────

def test_fetch_bills_demo_mode_yields_pydantic():
    bills = list(bill.fetch_bills())
    assert len(bills) >= 1
    assert all(isinstance(b, Bill) for b in bills)


def test_fetch_bills_source_real():
    """real 어댑터 출력은 source='real' 강제."""
    for b in bill.fetch_bills():
        assert b.source == "real"


def test_fetch_bills_max_rows_limit():
    bills = list(bill.fetch_bills(max_rows=3))
    assert len(bills) == 3


def test_bill_status_normalization():
    """다양한 PROC_RESULT 문자열 → BillStatus enum."""
    cases = {
        "접수": "proposed",
        "회부": "in_committee",
        "심사중": "in_committee",
        "상정": "in_plenary",
        "가결": "passed",
        "원안가결": "passed",
        "수정가결": "passed",
        "부결": "rejected",
        "철회": "withdrawn",
        "폐기": "withdrawn",
        "알수없는상태": "proposed",  # fallback
        "": "proposed",
    }
    for raw, expected in cases.items():
        assert bill._normalize_status(raw) == expected, f"{raw!r} → {expected}"


def test_bill_date_parser_handles_formats():
    assert bill._parse_date("2026-04-15") == date(2026, 4, 15)
    assert bill._parse_date("20260415") == date(2026, 4, 15)
    assert bill._parse_date("2026.04.15") == date(2026, 4, 15)
    assert bill._parse_date("") == date.today()  # fallback


def test_bills_have_diverse_status():
    """mock 의안 10건에 다양한 상태 분포."""
    statuses = {b.status for b in bill.fetch_bills()}
    assert len(statuses) >= 3  # 최소 3 상태


def test_bills_categories_non_empty():
    bills = list(bill.fetch_bills())
    has_category = [b for b in bills if b.category]
    assert len(has_category) >= 5  # 대다수 카테고리 추출 성공


# ─── Member 어댑터 ──────────────────────────────────────────────────────────

def test_fetch_members_demo_mode_yields_pydantic():
    members = list(member.fetch_members())
    assert len(members) >= 1
    assert all(isinstance(m, Person) for m in members)


def test_fetch_members_source_real():
    for m in member.fetch_members():
        assert m.source == "real"


def test_fetch_members_term_propagated():
    for m in member.fetch_members(term=22):
        assert m.term == 22


def test_fetch_members_max_rows():
    members = list(member.fetch_members(max_rows=5))
    assert len(members) == 5


def test_members_have_assembly_id_pattern():
    """MONA_* 형식 - 합성 generator의 PERSON_ID_POOL과 호환."""
    for m in member.fetch_members():
        assert m.assembly_id.startswith("MONA_")


def test_members_election_district_type_distinguished():
    """지역구/비례대표 두 타입 모두 등장."""
    members = list(member.fetch_members())
    types = {m.election_district_type for m in members if m.election_district_type}
    assert "constituency" in types
    assert "proportional" in types


def test_members_party_distribution_balanced():
    """mock 의원 정당 분포가 한쪽으로 쏠리지 않음 - 최소 4개 정당."""
    members = list(member.fetch_members())
    parties = {m.party_id for m in members if m.party_id}
    assert len(parties) >= 4, f"정당 다양성 부족: {parties}"


# ─── Vote 어댑터 ────────────────────────────────────────────────────────────

def test_fetch_votes_demo_mode_yields_pydantic():
    votes = list(vote.fetch_votes())
    assert len(votes) >= 1
    assert all(isinstance(v, Vote) for v in votes)


def test_fetch_votes_source_real():
    for v in vote.fetch_votes():
        assert v.source == "real"


def test_fetch_votes_max_rows():
    votes = list(vote.fetch_votes(max_rows=3))
    assert len(votes) == 3


def test_vote_id_deterministic_pattern():
    """vote_id = V_<BILL_ID>_<DATE> 형식."""
    for v in vote.fetch_votes():
        assert v.vote_id.startswith("V_")
        # 같은 BILL_ID + DATE → 같은 vote_id
        v2 = next(vote.fetch_votes(max_rows=1))
        assert v2.vote_id == next(vote.fetch_votes(max_rows=1)).vote_id


def test_vote_result_normalization():
    cases = {
        "가결": "passed",
        "원안가결": "passed",
        "수정가결": "passed",
        "통과": "passed",
        "부결": "rejected",
        "폐기": "rejected",
        "철회": "withdrawn",
        "취소": "withdrawn",
        "unknown": "passed",  # fallback (보수적)
    }
    for raw, expected in cases.items():
        assert vote.RESULT_MAP.get(raw, "passed") == expected


def test_votes_have_balanced_result_distribution():
    """mock 표결 분포: passed 다수 + rejected/withdrawn 일부."""
    votes = list(vote.fetch_votes())
    results = [v.result for v in votes]
    n_passed = results.count("passed")
    n_other = len(results) - n_passed
    assert n_passed >= 5
    assert n_other >= 1  # 적어도 1개 비-가결


def test_vote_bill_id_references_bill_adapter():
    """vote의 bill_id가 bill 어댑터의 BILL_ID와 매칭 (cross-adapter consistency)."""
    bill_ids = {b.bill_id for b in bill.fetch_bills()}
    vote_bill_ids = {v.bill_id for v in vote.fetch_votes()}
    # vote가 bill을 참조하므로 vote_bill_ids ⊆ bill_ids
    assert vote_bill_ids.issubset(bill_ids), (
        f"vote가 bill에 없는 ID 참조: {vote_bill_ids - bill_ids}"
    )


# ─── 통합: 결정성 ────────────────────────────────────────────────────────────

def test_all_adapters_deterministic_in_demo_mode():
    """Demo mode는 fixture가 결정적이므로 두 번 호출 동일 결과."""
    bills_1 = [b.model_dump() for b in bill.fetch_bills()]
    bills_2 = [b.model_dump() for b in bill.fetch_bills()]
    assert bills_1 == bills_2

    members_1 = [m.model_dump() for m in member.fetch_members()]
    members_2 = [m.model_dump() for m in member.fetch_members()]
    assert members_1 == members_2

    votes_1 = [v.model_dump(mode="json") for v in vote.fetch_votes()]
    votes_2 = [v.model_dump(mode="json") for v in vote.fetch_votes()]
    assert votes_1 == votes_2


# ─── 통합: 정치 균형 (mock 데이터) ─────────────────────────────────────────

def test_member_party_balance_no_single_party_dominance():
    """mock 의원 정당 분포가 한 정당에 과도하게 쏠리지 않음."""
    members = list(member.fetch_members())
    party_counts: dict[str, int] = {}
    for m in members:
        if m.party_id:
            party_counts[m.party_id] = party_counts.get(m.party_id, 0) + 1
    # 한 정당이 전체의 60% 초과하지 않아야 함 (균형 fixture)
    if party_counts:
        max_pct = max(party_counts.values()) / len(members)
        assert max_pct <= 0.6, f"정당 편향: {party_counts}"
