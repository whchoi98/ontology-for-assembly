"""시나리오 D 페르소나 매칭 검증 (Phase 4 Track 4-7)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import persona_match_builder, insights_builder


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 서비스 ─────────────────────────────────────────────────────────────────


def test_affinity_matrix_has_6_personas():
    """6 페르소나 모두 매트릭스에 등록."""
    matrix = persona_match_builder.PERSONA_AFFINITY_MATRIX
    assert set(matrix.keys()) == {
        "editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b",
    }


def test_affinity_values_in_range():
    """모든 affinity 값 0-5."""
    for persona_scores in persona_match_builder.PERSONA_AFFINITY_MATRIX.values():
        for v in persona_scores.values():
            assert 0 <= v <= 5


def test_weights_sum_to_one():
    """가중치 3 합 = 1.0."""
    w = (
        persona_match_builder.WEIGHT_TOPIC_AFFINITY
        + persona_match_builder.WEIGHT_KPI_KEYWORD
        + persona_match_builder.WEIGHT_TONE_FIT
    )
    assert abs(w - 1.0) < 1e-6


def test_match_article_returns_6_scores():
    """기사 매칭 결과는 6 페르소나 점수 모두 포함."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    result = persona_match_builder.match_article(art_id)
    assert result is not None
    assert len(result.scores) == 6
    pids = {s.persona_id for s in result.scores}
    assert pids == {
        "editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b",
    }


def test_match_article_scores_sorted_desc():
    """결과 scores는 score 내림차순."""
    pool = insights_builder._article_pool()
    result = persona_match_builder.match_article(pool[0].article_id)
    assert result is not None
    scores = [s.score for s in result.scores]
    assert scores == sorted(scores, reverse=True)


def test_match_article_top_persona_consistent():
    """top_persona_id == scores[0].persona_id."""
    pool = insights_builder._article_pool()
    result = persona_match_builder.match_article(pool[0].article_id)
    assert result is not None
    assert result.top_persona_id == result.scores[0].persona_id


def test_match_article_unknown_returns_none():
    """미존재 → None."""
    assert persona_match_builder.match_article("art_99999") is None


def test_match_text_with_hints():
    """text + category_hints로 매칭 강제."""
    text = "AI 산업 진흥 정책에 대한 입법 분석."
    result = persona_match_builder.match_text(text, topic_category_hints=["산업"])
    assert "산업" in result.topic_categories
    # 산업 affinity 5인 페르소나(data_ai 또는 b2b)가 top일 가능성 높음
    assert result.top_persona_id in {"data_ai", "b2b", "editorial", "paid_subscriber"}


def test_match_text_auto_category_inference():
    """카테고리 hint 없으면 키워드 추론."""
    text = "AI 산업 진흥 + 인공지능 정책 분석."
    result = persona_match_builder.match_text(text)
    assert "산업" in result.topic_categories


def test_match_text_unrelated_text_defaults_social():
    """매칭 키워드 없으면 '사회' 기본."""
    result = persona_match_builder.match_text("이것은 매우 일반적인 텍스트입니다. 매우 일반적입니다.")
    assert result.topic_categories == ["사회"]


def test_low_balance_text_reduces_ad_sales_fit():
    """ad_sales는 balance가 낮을수록 tone_fit 큰 감점."""
    low_balance = "더불어민주당이 잘못했다. 옳다고 보기 어렵고 실패했다 무능했다."
    result = persona_match_builder.match_text(low_balance)
    ad_score = next(s for s in result.scores if s.persona_id == "ad_sales")
    assert ad_score.tone_fit <= 0.5, f"ad_sales tone_fit={ad_score.tone_fit}"


# ─── 라우터 ────────────────────────────────────────────────────────────────


def test_matrix_endpoint(client: TestClient):
    """GET /matrix - 메타 데이터."""
    response = client.get("/api/persona-match/matrix")
    assert response.status_code == 200
    body = response.json()
    assert "matrix" in body
    assert "weights" in body
    assert len(body["matrix"]) == 6


def test_match_article_endpoint(client: TestClient):
    """GET /article/{id}."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    response = client.get(f"/api/persona-match/article/{art_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["source_kind"] == "article"
    assert body["source_id"] == art_id
    assert len(body["scores"]) == 6


def test_match_article_404(client: TestClient):
    """미존재 404."""
    response = client.get("/api/persona-match/article/art_99999")
    assert response.status_code == 404


def test_match_text_endpoint(client: TestClient):
    """POST /text."""
    response = client.post(
        "/api/persona-match/text",
        json={"text": "AI 산업 진흥 종합 대책 (출처: 국회 OpenAPI)"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_kind"] == "text"
    assert body["source_id"] is None
    assert len(body["scores"]) == 6


def test_match_text_empty_rejected(client: TestClient):
    """텍스트 너무 짧으면 422."""
    response = client.post("/api/persona-match/text", json={"text": "X"})
    assert response.status_code == 422


def test_match_text_with_hints_endpoint(client: TestClient):
    """category_hints 전달."""
    body = client.post(
        "/api/persona-match/text",
        json={
            "text": "이런 텍스트에는 카테고리 자동 추론이 안 되어야 함.",
            "topic_category_hints": ["환경", "법무"],
        },
    ).json()
    assert set(body["topic_categories"]) == {"환경", "법무"}


# ─── 페르소나 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id",
    ["editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b"],
)
def test_persona_header_echo(client: TestClient, persona_id: str):
    """X-Persona-Id가 응답에 echo (호출자 정보 보존)."""
    pool = insights_builder._article_pool()
    art_id = pool[0].article_id
    body = client.get(
        f"/api/persona-match/article/{art_id}",
        headers={"X-Persona-Id": persona_id},
    ).json()
    assert body["persona_id"] == persona_id
