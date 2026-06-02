"""시나리오 N 이슈×입법 상관 검증 (Phase 4 Track 4-10)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import issue_legislation_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_macro_issues_count():
    """8 macro 이슈."""
    assert len(issue_legislation_builder.MACRO_ISSUES) == 8


def test_activity_types_count():
    """4 활동 유형."""
    assert len(issue_legislation_builder.ACTIVITY_TYPES) == 4


def test_build_matrix_returns_8_rows():
    """매트릭스 행 = 8."""
    m = issue_legislation_builder.build_matrix()
    assert len(m.rows) == 8


def test_each_row_has_4_activities():
    """각 row는 4 activities."""
    m = issue_legislation_builder.build_matrix()
    for row in m.rows:
        assert len(row.activities) == 4


def test_top_correlations_5():
    """top 5 correlations."""
    m = issue_legislation_builder.build_matrix()
    assert len(m.top_correlations) == 5


def test_top_correlations_sorted_desc():
    """top correlations는 intensity 내림차순."""
    m = issue_legislation_builder.build_matrix()
    intensities = [c.intensity for c in m.top_correlations]
    assert intensities == sorted(intensities, reverse=True)


def test_intensity_values_in_range():
    """모든 intensity 0-100."""
    m = issue_legislation_builder.build_matrix()
    for row in m.rows:
        for a in row.activities:
            assert 0 <= a.value <= 100


def test_intensity_label_4_tiers():
    """label 4 tier 매핑 (매우 높음/높음/보통/낮음)."""
    m = issue_legislation_builder.build_matrix()
    labels = {a.intensity_label for row in m.rows for a in row.activities}
    assert labels.issubset({"매우 높음", "높음", "보통", "낮음"})


def test_dominant_activity_is_max():
    """dominant_activity는 activities 중 max value."""
    m = issue_legislation_builder.build_matrix()
    for row in m.rows:
        max_act = max(row.activities, key=lambda a: a.value)
        assert row.dominant_activity == max_act.activity


def test_sources_present():
    """sources 1+ 항목."""
    m = issue_legislation_builder.build_matrix()
    assert len(m.sources) >= 1


# ─── 라우터 ────────────────────────────────────────────────────────────────


def test_endpoint(client: TestClient):
    """GET /api/issue-legislation."""
    response = client.get("/api/issue-legislation")
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 8
    assert len(body["top_correlations"]) == 5
    assert body["activity_types"] == [
        "proposed", "voted", "statements", "committee_activity",
    ]


def test_response_includes_persona_note(client: TestClient):
    """persona_note 자동 생성."""
    body = client.get("/api/issue-legislation").json()
    assert len(body["persona_note"]) > 0


# ─── 페르소나 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 propagation."""
    headers = {"X-Persona-Id": persona_id}
    body = client.get("/api/issue-legislation", headers=headers).json()
    assert body["persona_id"] == persona_id
    assert len(body["persona_note"]) > 0


# ─── ADR-0004 ────────────────────────────────────────────────────────────


def test_no_party_count_in_matrix():
    """매트릭스 셀에 정당 카운트 없음 (ADR-0004 정당 기반 분류 금지)."""
    m = issue_legislation_builder.build_matrix()
    for row in m.rows:
        # ActivityIntensity에 정당 필드가 없는지 확인
        for a in row.activities:
            assert not hasattr(a, "party"), "정당 별 분류는 금지"


def test_insights_avoid_strong_causal_claims():
    """insight에 단정적 인과 표현 금지."""
    forbidden = ["때문이다", "원인이다", "확실히", "반드시", "절대로"]
    m = issue_legislation_builder.build_matrix()
    for c in m.top_correlations:
        for term in forbidden:
            assert term not in c.insight, f"{c.issue_id}: '{term}'"
