"""시나리오 I 편향·중립성 가드레일 검증 (Phase 4 Track 4-3).

ADR-0004 4-layer 가드레일 시연이 라우터로 노출되는지 + 점수 분포 시드의
의도된 등급(낮음/중간/양호/우수)이 임계 측면에서 일치하는지 확인.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import guardrails, ops_metrics


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _reset_metrics():
    """각 테스트마다 ops_metrics 버퍼·카운터 초기화 - trace 간섭 회피."""
    ops_metrics.reset()
    yield
    ops_metrics.reset()


# ─── /samples ───────────────────────────────────────────────────────────────


def test_samples_returns_4_entries(client: TestClient):
    """4 등급 시드가 모두 반환되어야 함."""
    response = client.get("/api/neutrality/samples")
    assert response.status_code == 200
    body = response.json()
    samples = body["samples"]
    assert len(samples) == 4
    labels = [s["label"] for s in samples]
    assert labels == ["낮음", "중간", "양호", "우수"]


def test_samples_score_ordering_intuitive(client: TestClient):
    """샘플 점수가 라벨(낮음 < 중간 < 양호 < 우수)에 따라 단조 증가해야 함."""
    body = client.get("/api/neutrality/samples").json()
    scores = [s["score"] for s in body["samples"]]
    assert scores == sorted(scores), f"점수가 단조 증가 아님: {scores}"


def test_samples_alarm_flag_aligns_with_threshold(client: TestClient):
    """알람 플래그가 score < threshold 와 일치해야 함."""
    body = client.get("/api/neutrality/samples").json()
    threshold = body["threshold"]
    for sample in body["samples"]:
        expected_alarm = sample["score"] < threshold
        assert sample["alarm"] == expected_alarm, (
            f"{sample['sample_id']}: score={sample['score']} vs alarm={sample['alarm']}"
        )


def test_samples_components_breakdown_present(client: TestClient):
    """모든 샘플에 3 컴포넌트 + parties_mentioned + 카운트 노출."""
    body = client.get("/api/neutrality/samples").json()
    for sample in body["samples"]:
        c = sample["components"]
        assert "party_mention_balance" in c
        assert "citation_score" in c
        assert "assertion_penalty" in c
        assert "parties_mentioned" in c
        assert "total_party_mentions" in c
        assert "citation_count" in c
        assert "assertion_count" in c


def test_excellent_sample_has_multiple_parties(client: TestClient):
    """우수 등급은 2개 이상 정당 균형 언급."""
    body = client.get("/api/neutrality/samples").json()
    excellent = next(s for s in body["samples"] if s["sample_id"] == "excellent_balance_004")
    assert len(excellent["components"]["parties_mentioned"]) >= 2
    assert excellent["score"] >= 0.9


# ─── /score ────────────────────────────────────────────────────────────────


def test_score_endpoint_basic(client: TestClient):
    """단순 텍스트 채점 - 응답 schema 확인."""
    response = client.post(
        "/api/neutrality/score",
        json={"text": "이번 회기에서 양당이 협력했다. (출처: 국회 OpenAPI)"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "score" in body
    assert 0.0 <= body["score"] <= 1.0
    assert "components" in body
    assert "interpretation" in body
    assert isinstance(body["alarm"], bool)


def test_score_low_balance_alarms(client: TestClient):
    """단정적 가치 판단·정당 비방 결합 = 낮은 점수."""
    text = "더불어민주당이 추진한 정책은 잘못했다. 옳다고 보기 어렵다. 실패했다."
    body = client.post("/api/neutrality/score", json={"text": text}).json()
    assert body["score"] < guardrails.ALARM_THRESHOLD
    assert body["alarm"] is True


def test_score_excellent_balance(client: TestClient):
    """양당 균형 + 출처 인용 = 임계 통과."""
    text = (
        "더불어민주당과 국민의힘이 각각 12건의 입법을 발의했다. "
        "(출처: 국회 OpenAPI 2026-04, https://open.assembly.go.kr)"
    )
    body = client.post("/api/neutrality/score", json={"text": text}).json()
    assert body["score"] >= guardrails.ALARM_THRESHOLD
    assert body["alarm"] is False


def test_score_validates_empty_text(client: TestClient):
    """min_length=1 강제."""
    response = client.post("/api/neutrality/score", json={"text": ""})
    assert response.status_code == 422


def test_score_validates_too_long(client: TestClient):
    """max_length=4000 강제."""
    response = client.post("/api/neutrality/score", json={"text": "x" * 4001})
    assert response.status_code == 422


def test_score_interpretation_4_tiers(client: TestClient):
    """점수 구간별 interpretation 문구 존재."""
    cases = [
        ("매우 낮은 텍스트, 무능, 실패했다, 잘못했다, 옳다고 보기 어렵다, 옳다.", "낮음"),
        ("더불어민주당, 더불어민주당, 더불어민주당의 입법.", "중간"),
        ("이번 회기에서 양당이 협력했다. (출처: 국회 OpenAPI)", "양호"),
        (
            "더불어민주당과 국민의힘이 각각 12, 11건 입법. "
            "(출처: 국회 OpenAPI 2026-04, https://open.assembly.go.kr)",
            "우수",
        ),
    ]
    for text, expected_tier in cases:
        body = client.post("/api/neutrality/score", json={"text": text}).json()
        assert expected_tier in body["interpretation"], (
            f"text='{text[:30]}...' → score={body['score']} interp='{body['interpretation']}'"
        )


# ─── /architecture ─────────────────────────────────────────────────────────


def test_architecture_returns_4_layers(client: TestClient):
    """ADR-0004 4 레이어 모두 반환."""
    body = client.get("/api/neutrality/architecture").json()
    assert len(body["layers"]) == 4
    layer_nums = [l["layer"] for l in body["layers"]]
    assert layer_nums == [1, 2, 3, 4]


def test_architecture_layer_names_match_adr(client: TestClient):
    """ADR-0004 정의된 레이어 이름이 노출되는지."""
    body = client.get("/api/neutrality/architecture").json()
    names = [l["name"] for l in body["layers"]]
    assert "Bedrock Guardrails" in names
    assert "political_balance_score" in names
    assert "FORBIDDEN_FIELDS" in names


def test_architecture_party_catalog_present(client: TestClient):
    """9 정당 카탈로그 - guardrails.KNOWN_PARTIES와 일치."""
    body = client.get("/api/neutrality/architecture").json()
    catalog = body["party_catalog"]
    expected = [c for c, _ in guardrails.KNOWN_PARTIES]
    assert catalog == expected


def test_architecture_weights_sum_to_one(client: TestClient):
    """3 컴포넌트 가중치 합 = 1.0 (alarm_threshold는 별도)."""
    body = client.get("/api/neutrality/architecture").json()
    w = body["weights"]
    total = w["party_balance"] + w["citation"] + w["assertion_penalty"]
    assert abs(total - 1.0) < 1e-6


# ─── /recent ────────────────────────────────────────────────────────────────


def test_recent_empty_initial(client: TestClient):
    """초기 상태 - traces 빈 리스트."""
    body = client.get("/api/neutrality/recent").json()
    assert body["traces"] == []
    assert body["counters"]["total_invocations"] == 0


def test_recent_reflects_trace_buffer(client: TestClient):
    """ops_metrics.record_trace 후 /recent 반영."""
    ops_metrics.record_trace(
        persona_id="editorial",
        scenario_code="I",
        model_id="claude-sonnet-4-6",
        political_balance_score=0.92,
        alarm=False,
    )
    ops_metrics.record_trace(
        persona_id="general_reader",
        scenario_code="B",
        model_id="claude-sonnet-4-6",
        political_balance_score=0.65,
        alarm=True,
        alarm_reason="low_balance_score",
    )
    body = client.get("/api/neutrality/recent?limit=10").json()
    assert len(body["traces"]) == 2
    assert body["counters"]["total_invocations"] == 2
    assert body["counters"]["total_alarms_low_balance"] == 1


def test_recent_traces_newest_first(client: TestClient):
    """최신 trace가 먼저 (LIFO)."""
    ops_metrics.record_trace(
        persona_id="editorial", scenario_code="I", model_id="m",
        political_balance_score=0.9, alarm=False,
    )
    ops_metrics.record_trace(
        persona_id="data_ai", scenario_code="A", model_id="m",
        political_balance_score=0.85, alarm=False,
    )
    body = client.get("/api/neutrality/recent").json()
    assert body["traces"][0]["persona_id"] == "data_ai"
    assert body["traces"][1]["persona_id"] == "editorial"


# ─── 페르소나 전파 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_header_propagation(client: TestClient, persona_id: str):
    """6 페르소나 모두 persona_id가 응답에 echo."""
    headers = {"X-Persona-Id": persona_id}
    for path in ["/api/neutrality/samples", "/api/neutrality/architecture", "/api/neutrality/recent"]:
        body = client.get(path, headers=headers).json()
        assert body["persona_id"] == persona_id, f"{path}: {body['persona_id']}"


# ─── ADR-0004 제약 ─────────────────────────────────────────────────────────


def test_no_party_attack_in_sample_seeds(client: TestClient):
    """모든 데모 시드가 PARTY_ATTACK_PATTERNS 미포함 - guardrail.passed=True 보장."""
    body = client.get("/api/neutrality/samples").json()
    for sample in body["samples"]:
        result = guardrails.check_output(sample["text"])
        assert result.passed, (
            f"{sample['sample_id']} 시드가 정당 비방 패턴 매칭됨: "
            f"blocked={result.blocked_topics}"
        )
