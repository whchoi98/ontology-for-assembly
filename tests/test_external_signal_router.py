"""시나리오 J 외부 신호 융합 검증 (Phase 4 Track 4-6)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import signal_fusion_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_list_fusions_returns_3():
    """3 패턴 시드 - signal_leads / legislation_leads / decoupled 각 1."""
    fusions = signal_fusion_builder.list_fusions()
    assert len(fusions) == 3
    patterns = {f.pattern for f in fusions}
    assert patterns == {"signal_leads", "legislation_leads", "decoupled"}


def test_list_fusions_filter_by_pattern():
    """패턴 필터 동작."""
    signal_leads = signal_fusion_builder.list_fusions(pattern="signal_leads")
    assert len(signal_leads) == 1
    assert signal_leads[0].pattern == "signal_leads"


def test_get_fusion_known():
    """기지 fusion_id lookup."""
    f = signal_fusion_builder.get_fusion("fusion_ai_signal_leads")
    assert f is not None
    assert f.topic_id == "topic_ai"


def test_get_fusion_unknown_returns_none():
    """미존재 → None."""
    assert signal_fusion_builder.get_fusion("nope") is None


def test_each_fusion_has_12_weeks():
    """시계열 12 데이터 포인트 (W04-W15)."""
    for f in signal_fusion_builder.list_fusions():
        assert len(f.weeks) == 12


def test_signal_leads_pattern_has_positive_lag():
    """signal_leads 패턴의 lag_weeks > 0 (bill peak가 signal peak 이후)."""
    f = signal_fusion_builder.get_fusion("fusion_ai_signal_leads")
    assert f is not None
    assert f.lag_weeks > 0, f"signal_leads여도 lag={f.lag_weeks}"


def test_legislation_leads_pattern_has_negative_lag():
    """legislation_leads 패턴의 lag_weeks < 0."""
    f = signal_fusion_builder.get_fusion("fusion_env_legislation_leads")
    assert f is not None
    assert f.lag_weeks < 0, f"legislation_leads여도 lag={f.lag_weeks}"


def test_decoupled_low_correlation_hint():
    """decoupled는 correlation_hint < 0.3."""
    f = signal_fusion_builder.get_fusion("fusion_culture_decoupled")
    assert f is not None
    assert f.correlation_hint < 0.3


def test_peak_weeks_consistent_with_series():
    """peak_signal_week·peak_legislation_week은 weeks 안의 ISO에 포함."""
    for f in signal_fusion_builder.list_fusions():
        weeks_iso = {p.week_iso for p in f.weeks}
        assert f.peak_signal_week in weeks_iso
        assert f.peak_legislation_week in weeks_iso


def test_narrative_includes_source_attribution():
    """모든 narrative에 (출처: ...) 포함."""
    for f in signal_fusion_builder.list_fusions():
        assert "(출처:" in f.narrative or "출처:" in f.narrative


# ─── 라우터 ────────────────────────────────────────────────────────────────


def test_list_endpoint(client: TestClient):
    """GET /api/external-signal."""
    response = client.get("/api/external-signal")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["fusions"]) == 3


def test_list_pattern_filter(client: TestClient):
    """pattern 쿼리 필터."""
    body = client.get("/api/external-signal?pattern=signal_leads").json()
    assert body["pattern_filter"] == "signal_leads"
    assert all(f["pattern"] == "signal_leads" for f in body["fusions"])


def test_list_invalid_pattern_422(client: TestClient):
    """패턴 enum 외 값 거부."""
    response = client.get("/api/external-signal?pattern=invalid")
    assert response.status_code == 422


def test_detail_endpoint(client: TestClient):
    """디테일 응답."""
    body = client.get("/api/external-signal/fusion_ai_signal_leads").json()
    assert body["fusion"]["topic_id"] == "topic_ai"
    assert body["fusion"]["pattern"] == "signal_leads"
    assert "narrative" in body["fusion"]


def test_detail_404(client: TestClient):
    """미존재 404."""
    response = client.get("/api/external-signal/nope")
    assert response.status_code == 404


# ─── 페르소나 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_propagation(client: TestClient, persona_id: str):
    """6 페르소나 모두 persona_id echo + persona_note 생성."""
    headers = {"X-Persona-Id": persona_id}
    body = client.get("/api/external-signal", headers=headers).json()
    assert body["persona_id"] == persona_id
    assert len(body["persona_note"]) > 0


def test_editorial_follow_up_hint(client: TestClient):
    """editorial - follow_up_hint."""
    body = client.get(
        "/api/external-signal/fusion_ai_signal_leads",
        headers={"X-Persona-Id": "editorial"},
    ).json()
    assert "follow_up_hint" in body["extras"]
    assert "후속 취재" in body["extras"]["follow_up_hint"]


def test_data_ai_analysis_hint(client: TestClient):
    """data_ai - analysis_hint."""
    body = client.get(
        "/api/external-signal/fusion_ai_signal_leads",
        headers={"X-Persona-Id": "data_ai"},
    ).json()
    assert "analysis_hint" in body["extras"]


def test_paid_premium_cta(client: TestClient):
    """paid_subscriber - premium_cta."""
    body = client.get(
        "/api/external-signal/fusion_ai_signal_leads",
        headers={"X-Persona-Id": "paid_subscriber"},
    ).json()
    assert "premium_cta" in body["extras"]


# ─── ADR-0004 인과 단정 금지 ──────────────────────────────────────────────


def test_narratives_avoid_strong_causal_claims(client: TestClient):
    """narrative에 단정적 인과 표현 금지 (ADR-0004)."""
    forbidden = ["때문이다", "원인이다", "인과", "확실히", "반드시"]
    body = client.get("/api/external-signal").json()
    for f in body["fusions"]:
        for term in forbidden:
            assert term not in f["narrative"], f"{f['fusion_id']}: 단정 표현 '{term}'"
