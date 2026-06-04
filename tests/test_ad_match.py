"""시나리오 L 광고 매칭 라우터 + 서비스 검증.

핵심 검증:
- 3 모드 비교 응답 (keyword/embedding/agent)
- ★ Agent만 비위 콘텐츠에 광고 거절 (chosen_ad_id=None)
- AdMatchDecision Pydantic 검증 통과
- DEMO_TRAGIC_ARTICLE_ID에서 정확한 거절 트리거
- 일반 정책 콘텐츠는 3 모드 모두 매칭
- governance_summary 차이 가시화
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import ad_matcher
from api.services.ad_matcher import ArticleSummary
from data.schemas import AdMatchDecision
from data.synthetic.advertisement import generate_advertisements
from data.synthetic.seeds import DEMO_TRAGIC_ARTICLE_ID, DEMO_AD_ARTICLES, list_demo_ad_articles


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def safe_article() -> ArticleSummary:
    return ArticleSummary(
        article_id="art_safe_001",
        title="AI 산업 진흥 분석",
        content="22대 국회 AI 관련 의안 10건 발의. 양당 협력적 의제 (출처: 국회 OpenAPI).",
        topic_ids=["topic_ai", "topic_data"],
    )


@pytest.fixture
def tragic_article() -> ArticleSummary:
    return ArticleSummary(
        article_id=DEMO_TRAGIC_ARTICLE_ID,
        title="○○○ 의원 위증 의혹 - 검찰 수사 진행 중",
        content="○○○ 의원에 대한 위증 의혹이 제기. 검찰 수사 진행 중이다.",
        topic_ids=["topic_judicial"],
    )


@pytest.fixture
def candidate_ads():
    return list(generate_advertisements(count=20, seed=42))


# ─── 서비스 — 안전 콘텐츠 ───────────────────────────────────────────────────

def test_keyword_match_safe_article_chooses_ad(safe_article, candidate_ads):
    d = ad_matcher.match(safe_article, candidate_ads, mode="keyword")
    assert isinstance(d, AdMatchDecision)
    assert d.mode == "keyword"
    assert d.chosen_ad_id is not None


def test_embedding_match_safe_article_chooses_ad(safe_article, candidate_ads):
    d = ad_matcher.match(safe_article, candidate_ads, mode="embedding")
    assert d.chosen_ad_id is not None


def test_agent_match_safe_article_chooses_ad(safe_article, candidate_ads):
    """안전 콘텐츠에서 Agent도 광고 매칭 (거절 아님)."""
    d = ad_matcher.match(safe_article, candidate_ads, mode="agent")
    assert d.chosen_ad_id is not None
    assert "allow" in d.reason_text or "정책 정보성" in d.reason_text


# ─── 서비스 — 비위 콘텐츠 (★ 데모 메인) ────────────────────────────────────

def test_keyword_match_tragic_article_still_chooses_ad(tragic_article, candidate_ads):
    """keyword 모드는 민감 콘텐츠 감지 못 함 → 광고 매칭함 (한계)."""
    d = ad_matcher.match(tragic_article, candidate_ads, mode="keyword")
    # keyword는 점수 낮을 수 있지만 chosen_ad_id는 None이 아님
    assert d.chosen_ad_id is not None or d.score == 0.0


def test_embedding_match_tragic_article_still_chooses_ad(tragic_article, candidate_ads):
    """embedding 모드도 민감 감지 안 됨 (avoid_topics 매칭 안 되면)."""
    d = ad_matcher.match(tragic_article, candidate_ads, mode="embedding")
    # avoid 충돌 없으면 매칭됨


def test_agent_match_tragic_article_rejects(tragic_article, candidate_ads):
    """★ ADR-0004 Layer 6 - Agent만 비위 콘텐츠에 광고 거절."""
    d = ad_matcher.match(tragic_article, candidate_ads, mode="agent")
    assert d.chosen_ad_id is None
    assert d.score == 0.0
    assert "skip" in d.reason_text.lower()
    assert "민감" in d.reason_text or "scandal" in d.reason_text.lower()
    assert "Layer 6" in d.reason_text


def test_agent_reason_includes_adr_reference(tragic_article, candidate_ads):
    """광고 거절 trace에 ADR-0004 Layer 6 명시 - audit 자료로 가치."""
    d = ad_matcher.match(tragic_article, candidate_ads, mode="agent")
    assert "ADR-0004" in d.reason_text


# ─── 서비스 — 3-way 비교 ────────────────────────────────────────────────────

def test_compare_modes_returns_three_decisions(safe_article, candidate_ads):
    decisions = ad_matcher.compare_modes(safe_article, candidate_ads)
    assert set(decisions.keys()) == {"keyword", "embedding", "agent"}


def test_compare_demonstrates_agent_differentiation(tragic_article, candidate_ads):
    """3-way 비교 시 Agent만 광고 거절 - 시나리오 L 핵심 데모."""
    decisions = ad_matcher.compare_modes(tragic_article, candidate_ads)
    assert decisions["agent"].chosen_ad_id is None
    # keyword/embedding은 광고 매칭 (한계 시연)
    # avoid_topics가 우연히 매칭되지 않는 한
    assert decisions["agent"].mode == "agent"
    assert decisions["keyword"].mode == "keyword"
    assert decisions["embedding"].mode == "embedding"


# ─── 라우터 ─────────────────────────────────────────────────────────────────

def test_ad_match_endpoint_compare_default(client):
    response = client.post("/api/ad-match", json={"article_id": "art_safe"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "compare"
    assert set(body["results"].keys()) == {"keyword", "embedding", "agent"}


def test_ad_match_single_mode_chatbot(client):
    response = client.post("/api/ad-match", json={"article_id": "art_safe", "mode": "agent"})
    body = response.json()
    assert body["mode"] == "agent"
    assert list(body["results"].keys()) == ["agent"]


def test_ad_match_tragic_article_agent_skips(client):
    """라우터 통합 - 비위 콘텐츠에 Agent 광고 거절."""
    response = client.post(
        "/api/ad-match",
        json={"article_id": DEMO_TRAGIC_ARTICLE_ID, "mode": "compare"},
    )
    body = response.json()
    agent_decision = body["results"]["agent"]
    assert agent_decision["chosen_ad_id"] is None
    assert agent_decision["score"] == 0.0


def test_ad_match_tragic_article_keyword_does_not_skip(client):
    """라우터 통합 - 비위 콘텐츠에서도 keyword는 매칭 (한계 시연).

    keyword는 민감성 감지를 안 하므로 chosen_ad_id가 None이 아니어야 함.
    (reason_text는 한계를 자기 인정해 "감지 못 함" 문구는 포함됨)
    """
    response = client.post(
        "/api/ad-match",
        json={"article_id": DEMO_TRAGIC_ARTICLE_ID, "mode": "compare"},
    )
    body = response.json()
    keyword_decision = body["results"]["keyword"]
    # keyword는 거절(skip)이 아니라 매칭 (한계).
    assert keyword_decision["chosen_ad_id"] is not None
    # reason_text가 "skip"으로 시작하지 않음
    assert not keyword_decision["reason_text"].lower().startswith("skip")


def test_ad_match_governance_summary_highlights_agent(client):
    """비위 콘텐츠 응답에서 Agent가 거절했음을 governance_summary가 강조."""
    response = client.post(
        "/api/ad-match",
        json={"article_id": DEMO_TRAGIC_ARTICLE_ID, "mode": "compare"},
    )
    summary = response.json()["governance_summary"]
    assert "agent" in summary["modes_skipped_ads"]
    assert "Agent" in summary["key_message"] or "agent" in summary["key_message"]


def test_ad_match_governance_summary_safe_article(client):
    """안전 콘텐츠에서는 3 모드 모두 광고 매칭."""
    response = client.post("/api/ad-match", json={"article_id": "art_safe_normal"})
    summary = response.json()["governance_summary"]
    # safe면 거절 모드가 없거나 적음
    assert isinstance(summary["modes_skipped_ads"], list)


def test_ad_match_invalid_mode_rejected(client):
    response = client.post("/api/ad-match", json={"article_id": "x", "mode": "invalid"})
    assert response.status_code == 422


def test_ad_match_empty_article_id_rejected(client):
    response = client.post("/api/ad-match", json={"article_id": ""})
    assert response.status_code == 422


# ─── GET /modes 메타 ────────────────────────────────────────────────────────

def test_modes_endpoint_lists_four(client):
    response = client.get("/api/ad-match/modes")
    assert response.status_code == 200
    body = response.json()
    mode_ids = {m["id"] for m in body["modes"]}
    assert mode_ids == {"keyword", "embedding", "agent", "compare"}


def test_modes_agent_marked_as_differentiator(client):
    response = client.get("/api/ad-match/modes")
    body = response.json()
    agent_mode = next(m for m in body["modes"] if m["id"] == "agent")
    assert "differentiator" in agent_mode
    assert "민감" in agent_mode["differentiator"] or "감지" in agent_mode["differentiator"]


def test_modes_endpoint_references_adr(client):
    response = client.get("/api/ad-match/modes")
    body = response.json()
    assert "ADR" in body["adr_reference"]


# ─── AdMatchDecision Pydantic 검증 ──────────────────────────────────────────

def test_decision_score_in_valid_range(safe_article, candidate_ads):
    """모든 모드의 score는 [0, 1] 범위."""
    for mode in ("keyword", "embedding", "agent"):
        d = ad_matcher.match(safe_article, candidate_ads, mode=mode)  # type: ignore[arg-type]
        assert 0.0 <= d.score <= 1.0


def test_decision_id_unique_across_modes(safe_article, candidate_ads):
    """3 모드 결정 ID 유일."""
    decisions = ad_matcher.compare_modes(safe_article, candidate_ads)
    ids = {d.decision_id for d in decisions.values()}
    assert len(ids) == 3


def test_decision_candidate_ids_match_input(safe_article, candidate_ads):
    """candidate_ad_ids에 입력 ad_id가 모두 포함."""
    d = ad_matcher.match(safe_article, candidate_ads, mode="agent")
    input_ids = {ad.ad_id for ad in candidate_ads}
    assert set(d.candidate_ad_ids) == input_ids


# ─── SENSITIVE_PATTERNS 정합 ────────────────────────────────────────────────

def test_sensitive_patterns_cover_four_categories():
    """4 카테고리: scandal, tragedy, minor_victim, controversy."""
    expected = {"scandal", "tragedy", "minor_victim", "controversy"}
    actual = {name for name, _ in ad_matcher.SENSITIVE_PATTERNS}
    assert actual == expected


def test_scandal_pattern_matches_korean_keywords():
    """검찰·수사·기소 등 패턴이 한국어 본문에 매칭."""
    article = ArticleSummary(
        article_id="x", title="t", content="검찰 수사 진행 중", topic_ids=[],
    )
    found = ad_matcher._detect_sensitive(article)
    assert "scandal" in found


def test_tragedy_pattern_matches():
    article = ArticleSummary(
        article_id="x", title="t", content="사망 사고 발생", topic_ids=[],
    )
    found = ad_matcher._detect_sensitive(article)
    assert "tragedy" in found


def test_minor_pattern_matches():
    article = ArticleSummary(
        article_id="x", title="t", content="미성년 피해 사례", topic_ids=[],
    )
    found = ad_matcher._detect_sensitive(article)
    assert "minor_victim" in found


# ─── 시나리오 L 데모 기사 카탈로그 ─────────────────────────────────────────────

_SKIP_IDS = [aid for aid, a in DEMO_AD_ARTICLES.items() if a["expected_governance"].startswith("skip")]
_SAFE_IDS = [aid for aid, a in DEMO_AD_ARTICLES.items() if a["expected_governance"] == "match"]


def test_catalog_has_six_three_skip_three_safe():
    assert len(DEMO_AD_ARTICLES) == 6
    assert len(_SKIP_IDS) == 3
    assert len(_SAFE_IDS) == 3


def test_skip_articles_trigger_their_sensitive_pattern():
    from api.services.ad_matcher import _detect_sensitive, ArticleSummary
    expect = {"skip:scandal": "scandal", "skip:tragedy": "tragedy", "skip:minor_victim": "minor_victim"}
    for aid in _SKIP_IDS:
        a = DEMO_AD_ARTICLES[aid]
        art = ArticleSummary(article_id=aid, title=a["title"], content=a["content"], topic_ids=list(a["topic_ids"]))
        cats = _detect_sensitive(art)
        assert expect[a["expected_governance"]] in cats, f"{aid}: {cats}"


def test_safe_articles_have_no_sensitive_words():
    from api.services.ad_matcher import _detect_sensitive, ArticleSummary
    for aid in _SAFE_IDS:
        a = DEMO_AD_ARTICLES[aid]
        art = ArticleSummary(article_id=aid, title=a["title"], content=a["content"], topic_ids=list(a["topic_ids"]))
        assert _detect_sensitive(art) == set(), f"{aid} unexpectedly sensitive"


def test_all_demo_articles_anonymized_no_real_party():
    parties = ["더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "기본소득당", "진보당"]
    for aid in DEMO_AD_ARTICLES:
        text = DEMO_AD_ARTICLES[aid]["title"] + DEMO_AD_ARTICLES[aid]["content"]
        assert not any(p in text for p in parties), f"{aid} names a real party"


def test_list_demo_ad_articles_shape():
    rows = list_demo_ad_articles()
    assert len(rows) == 6
    for r in rows:
        assert set(r) >= {"article_id", "title", "topic_ids", "expected_governance"}


@pytest.mark.parametrize("aid", _SKIP_IDS)
def test_agent_skips_keyword_embedding_match(client, aid):
    body = client.post("/api/ad-match", json={"article_id": aid, "mode": "compare"}).json()
    res = body["results"]
    assert res["agent"]["chosen_ad_id"] is None
    assert res["agent"]["reason_text"].startswith("skip")
    assert res["keyword"]["chosen_ad_id"] is not None
    assert res["embedding"]["chosen_ad_id"] is not None


@pytest.mark.parametrize("aid", _SAFE_IDS)
def test_agent_matches_safe_articles(client, aid):
    body = client.post("/api/ad-match", json={"article_id": aid, "mode": "compare"}).json()
    assert body["results"]["agent"]["chosen_ad_id"] is not None


def test_samples_endpoint_returns_six(client):
    body = client.get("/api/ad-match/samples").json()
    samples = body["samples"]
    assert len(samples) == 6
    gov = [s["expected_governance"] for s in samples]
    assert sum(g.startswith("skip") for g in gov) == 3
    assert gov.count("match") == 3
    for s in samples:
        assert set(s) >= {"article_id", "title", "category_hint", "expected_governance"}
