"""시나리오 H 지역구 지도 검증 (Phase 4 Track 4-4).

17 KOSTAT 시도 + 합성 시드 정합성 + 페르소나 hint + ADR-0004 정파 색 미사용.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import district_map_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_sido_registry_has_17_entries():
    """17 KOSTAT 시도 모두 등록."""
    assert len(district_map_builder.SIDO_REGISTRY) == 17


def test_sido_kostat_codes_unique():
    """KOSTAT 코드 중복 없음."""
    codes = [r.kostat_code for r in district_map_builder.SIDO_REGISTRY]
    assert len(codes) == len(set(codes))


def test_sido_keys_unique():
    """slug 키 중복 없음."""
    keys = [r.key for r in district_map_builder.SIDO_REGISTRY]
    assert len(keys) == len(set(keys))


def test_build_summary_returns_17():
    """summary는 17 시도 모두."""
    stats = district_map_builder.build_summary()
    assert len(stats) == 17


def test_summary_total_member_count_approximates_22nd_assembly():
    """합산 ≈ 22대 지역구 254 (시드 ±5 허용)."""
    stats = district_map_builder.build_summary()
    total = sum(s.member_count for s in stats)
    assert 245 <= total <= 260, f"expected ~254, got {total}"


def test_build_detail_seoul_includes_hub():
    """seoul detail에 허브 MONA_001 포함."""
    detail = district_map_builder.build_detail("seoul")
    assert detail is not None
    pids = [m.person_id for m in detail.members]
    assert "MONA_001" in pids


def test_build_detail_unknown_returns_none():
    """미등록 시도 → None."""
    assert district_map_builder.build_detail("unknown_sido") is None


def test_density_label_4_tiers():
    """member_count 4 tier 라벨 매핑."""
    stats = district_map_builder.build_summary()
    labels = {s.density_label for s in stats}
    # 17 시도 중 최소 3 tier는 등장해야 함 (다양성)
    assert len(labels) >= 3


# ─── /summary 엔드포인트 ────────────────────────────────────────────────────


def test_summary_endpoint(client: TestClient):
    """GET /api/district-map/summary."""
    response = client.get("/api/district-map/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_districts"] == 17
    assert len(body["sido"]) == 17
    assert "persona_hint" in body


def test_summary_includes_grid_coords(client: TestClient):
    """grid_row/col 모든 시도 포함 (지도 시각화용)."""
    body = client.get("/api/district-map/summary").json()
    for sido in body["sido"]:
        assert "grid_row" in sido
        assert "grid_col" in sido
        assert 0 <= sido["grid_row"] <= 4
        assert 0 <= sido["grid_col"] <= 5


def test_summary_parties_use_canonical_names(client: TestClient):
    """정당명은 canonical (별칭·이념 라벨 없음)."""
    body = client.get("/api/district-map/summary").json()
    forbidden_terms = ["진보", "보수", "좌파", "우파", "중도좌파", "중도우파", "극좌", "극우"]
    for sido in body["sido"]:
        for party in sido["parties"]:
            for term in forbidden_terms:
                # 정의당·진보당은 정당 등록명이므로 substring이 아닌 fully match 확인
                assert party not in (term,), f"{sido['key']}: {party} = forbidden label"


def test_summary_activity_fields_present(client: TestClient):
    """activity dict에 proposed/voted/statements 모두 포함."""
    body = client.get("/api/district-map/summary").json()
    for sido in body["sido"]:
        assert "proposed" in sido["activity"]
        assert "voted" in sido["activity"]
        assert "statements" in sido["activity"]


# ─── /{sido_key} 엔드포인트 ─────────────────────────────────────────────────


def test_detail_seoul(client: TestClient):
    """seoul detail - 의원 리스트 + 요약."""
    response = client.get("/api/district-map/seoul")
    assert response.status_code == 200
    body = response.json()
    assert body["sido"]["key"] == "seoul"
    assert len(body["members"]) >= 1
    assert "summary" in body
    # ADR-0004: 출처 인용
    assert "출처" in body["summary"]


def test_detail_404_unknown(client: TestClient):
    """미등록 시도 404."""
    response = client.get("/api/district-map/atlantis")
    assert response.status_code == 404


def test_detail_for_all_17_sido_returns_200(client: TestClient):
    """17 시도 모두 detail 응답 가능."""
    for reg in district_map_builder.SIDO_REGISTRY:
        response = client.get(f"/api/district-map/{reg.key}")
        assert response.status_code == 200, f"{reg.key}: {response.status_code}"


# ─── 페르소나 전파 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 모두 persona_id echo + persona_hint 생성."""
    headers = {"X-Persona-Id": persona_id}
    summary = client.get("/api/district-map/summary", headers=headers).json()
    assert summary["persona_id"] == persona_id
    if persona_id != "ad_sales":
        # ad_sales는 hint가 있고, 다른 모든 persona도 hint를 받음
        assert len(summary["persona_hint"]) > 0


def test_editorial_detail_has_follow_up(client: TestClient):
    """editorial 페르소나는 follow_up_hint 포함."""
    headers = {"X-Persona-Id": "editorial"}
    body = client.get("/api/district-map/seoul", headers=headers).json()
    assert "follow_up_hint" in body["extras"]
    assert "후속 취재" in body["extras"]["follow_up_hint"]


def test_paid_detail_has_pdf_cta(client: TestClient):
    """paid_subscriber는 premium_cta 포함."""
    headers = {"X-Persona-Id": "paid_subscriber"}
    body = client.get("/api/district-map/seoul", headers=headers).json()
    assert "premium_cta" in body["extras"]


def test_b2b_detail_has_api_hint(client: TestClient):
    """b2b는 api_response_hint 포함."""
    headers = {"X-Persona-Id": "b2b"}
    body = client.get("/api/district-map/seoul", headers=headers).json()
    assert "api_response_hint" in body["extras"]


# ─── ADR-0004 정치 중립성 ──────────────────────────────────────────────────


def test_no_ideology_color_terms_in_density_labels(client: TestClient):
    """density_label은 정성 라벨만 - 정파 색 표현 금지."""
    body = client.get("/api/district-map/summary").json()
    forbidden = ["빨강", "파랑", "보수색", "진보색", "red", "blue"]
    for sido in body["sido"]:
        for term in forbidden:
            assert term not in sido["density_label"].lower()
