"""api.services.guardrails 검증 - ADR-0004 Layer 1·3.

테스트 범위:
- political_balance_score 핵심 케이스 (균형 / 한쪽 편향 / 출처 있음·없음 / 단정 표현)
- check_prompt / check_output 휴리스틱 (정당 비방 패턴 차단)
- annotate_response 메타데이터 모양
- 임계 ALARM_THRESHOLD 동작
- NEUTRALITY_GUARD_SUFFIX re-export
"""
from __future__ import annotations
import pytest

from api.services import guardrails as g


# ─── political_balance_score ─────────────────────────────────────────────────

def test_balance_score_returns_float_and_components():
    score, comp = g.political_balance_score("샘플 텍스트")
    assert 0.0 <= score <= 1.0
    assert isinstance(comp, g.BalanceComponents)


def test_neutral_text_with_no_party_mentions_scores_well():
    """정당 언급 없고 단정 표현도 없으면 균형 점수 자체는 만점."""
    text = "이번 회기의 의안 처리 현황을 정리합니다. 핵심 통계는 다음과 같습니다."
    score, comp = g.political_balance_score(text)
    assert comp.party_mention_balance == 1.0  # 정당 0개 = 균형 무관
    assert comp.assertion_count == 0
    # citation_score는 낮지만 (0건이므로 0.0) 전체적으로 0.5+ 보장
    assert score >= 0.5


def test_balanced_party_mentions_score_high():
    """두 정당 언급 빈도가 같으면 균형 점수 높음."""
    text = "더불어민주당 의원 5명과 국민의힘 의원 5명이 공동발의했다. (출처: 국회 공공 데이터)"
    score, comp = g.political_balance_score(text)
    assert comp.party_mention_balance >= 0.9
    assert "더불어민주당" in comp.parties_mentioned
    assert "국민의힘" in comp.parties_mentioned
    assert score >= g.ALARM_THRESHOLD


def test_skewed_party_mentions_score_low():
    """한 정당만 압도적이면 균형 점수 ↓."""
    text = "더불어민주당 더불어민주당 더불어민주당 더불어민주당 국민의힘"
    _score, comp = g.political_balance_score(text)
    assert comp.party_mention_balance < 0.5


def test_citation_present_boosts_score():
    """출처 인용이 있으면 citation_score ↑."""
    with_citation = "통계 분석 결과 (출처: 국회 OpenAPI) https://open.assembly.go.kr"
    _, comp = g.political_balance_score(with_citation)
    assert comp.citation_count >= 2
    assert comp.citation_score == 1.0


def test_no_citation_lowers_score():
    """출처 없으면 citation_score = 0."""
    _, comp = g.political_balance_score("정당 분석 결과만 나열")
    assert comp.citation_count == 0
    assert comp.citation_score == 0.0


def test_assertion_expressions_lower_score():
    """단정 가치 판단 표현이 많으면 assertion_penalty ↓ → score ↓."""
    text = "○○○ 의원은 무능했다. 정책이 잘못했다. 결국 실패했다. 부패가 만연한다. 옳다고 볼 수 없다."
    score, comp = g.political_balance_score(text)
    assert comp.assertion_count >= 5
    assert comp.assertion_penalty <= 0.1
    assert score < g.ALARM_THRESHOLD


# ─── check_prompt / check_output 휴리스틱 ─────────────────────────────────────

def test_check_prompt_passes_neutral_input():
    """중립 프롬프트는 통과."""
    result = g.check_prompt("최근 의안 발의 동향을 분석해주세요.", persona_id="editorial")
    assert result.passed
    assert result.blocked_topics == []


def test_check_prompt_blocks_party_attack():
    """정당 비방 결합 패턴은 차단."""
    result = g.check_prompt("국민의힘은 무능하다. 모든 정책이 부패")
    assert not result.passed
    assert "party_attack" in result.blocked_topics


def test_check_output_alarm_for_low_balance():
    """balance < 0.8이면 passed=True지만 blocked_topics에 알람 포함."""
    text = "더불어민주당 더불어민주당 더불어민주당 더불어민주당 (출처 없음, 단정 다수: 잘못했다 실패했다 무능했다 부패한다 옳다)"
    result = g.check_output(text)
    assert result.passed  # 차단은 아님
    has_alarm = any(t.startswith("low_balance_score:") for t in result.blocked_topics)
    assert has_alarm


def test_check_output_no_alarm_for_balanced():
    """균형 + 출처 있음 → 알람 없음."""
    text = "민주당 3건, 국민의힘 3건 (출처: 국회 OpenAPI, 자료: 국회사무처)"
    result = g.check_output(text)
    assert result.passed
    assert not any(t.startswith("low_balance_score:") for t in result.blocked_topics)


# ─── annotate_response ───────────────────────────────────────────────────────

def test_annotate_response_returns_required_keys():
    """SSE final event용 메타데이터 모양."""
    meta = g.annotate_response("간단한 분석 결과")
    expected_keys = {
        "political_balance_score",
        "balance_components",
        "guardrail_passed",
        "alarm",
        "alarm_reason",
    }
    assert expected_keys <= set(meta.keys())


def test_annotate_response_balance_components_subkeys():
    """balance_components 7개 sub-key 모두 존재."""
    meta = g.annotate_response("Topic 분석")
    comp = meta["balance_components"]
    expected_subkeys = {
        "party_mention_balance", "citation_score", "assertion_penalty",
        "parties_mentioned", "total_party_mentions", "citation_count", "assertion_count",
    }
    assert expected_subkeys <= set(comp.keys())


def test_annotate_response_alarm_field():
    """score < ALARM_THRESHOLD이면 alarm=True."""
    biased_text = "더불어민주당 더불어민주당 더불어민주당 더불어민주당 국민의힘. 잘못했다 무능 부패 실패 옳다"
    meta = g.annotate_response(biased_text)
    assert meta["alarm"] is True
    assert meta["alarm_reason"] == "low_balance_score"


def test_annotate_response_no_alarm_when_balanced():
    """균형 텍스트는 alarm=False."""
    balanced = "민주당과 국민의힘 양당 모두 (출처: 국회 OpenAPI 2026)"
    meta = g.annotate_response(balanced)
    assert meta["alarm"] is False
    assert meta["alarm_reason"] is None


# ─── 상수 무결성 ─────────────────────────────────────────────────────────────

def test_weights_sum_to_one():
    """3 컴포넌트 가중치 합 = 1.0."""
    total = g.WEIGHT_PARTY_BALANCE + g.WEIGHT_CITATION + g.WEIGHT_ASSERTION
    assert abs(total - 1.0) < 1e-9


def test_alarm_threshold_matches_spec():
    """spec §6.3의 0.8 임계값 일관성."""
    assert g.ALARM_THRESHOLD == 0.8


def test_neutrality_guard_suffix_reexported():
    """persona 모듈의 NEUTRALITY_GUARD_SUFFIX가 guardrails에서도 import 가능."""
    assert g.NEUTRALITY_GUARD_SUFFIX
    assert "단정적 가치 판단" in g.NEUTRALITY_GUARD_SUFFIX


def test_known_parties_no_standalone_ideology_labels():
    """KNOWN_PARTIES에 순수 이념 라벨이 단독 entry로 등록되지 않아야 한다.

    Note: '진보당'은 한국에 등록된 실제 정당이므로 허용 (정당명 ≠ 이념 라벨).
    이 테스트는 '보수', '진보' 등이 **단독** 정당명·별칭으로 잘못 등록된 경우만 차단.
    """
    forbidden_standalone = {"보수", "진보", "좌파", "우파", "중도", "보수파", "진보파"}
    for canonical, aliases in g.KNOWN_PARTIES:
        all_names = {canonical, *aliases}
        intersection = all_names & forbidden_standalone
        assert not intersection, f"순수 이념 라벨이 정당명으로 등록됨: {intersection}"


# ─── 시나리오 통합 (smoke) ───────────────────────────────────────────────────

def test_typical_editorial_response_passes():
    """편집국 페르소나의 전형적 응답이 알람 없이 통과."""
    text = (
        "22대 국회 첫 분기 동안 의안 발의 동향을 분석합니다. "
        "더불어민주당 142건, 국민의힘 138건이 접수되었으며, "
        "주요 카테고리는 사회복지·경제·환경 순입니다 (출처: 국회 OpenAPI 2026-05). "
        "후속 취재 포인트: ① 환경 카테고리 증가 배경 ② 공동발의 네트워크 변화."
    )
    meta = g.annotate_response(text, persona_id="editorial")
    assert meta["alarm"] is False
    assert meta["political_balance_score"] >= g.ALARM_THRESHOLD


def test_typical_general_reader_response_passes():
    """일반 독자 페르소나의 친절한 응답도 통과."""
    text = (
        "내 지역구 의원의 활동을 살펴보겠습니다. "
        "이번 회기에 발의하신 법안은 3건입니다 (출처: 국회 공공 데이터). "
        "관련해서 더 알고 싶다면 '의원 정치 여정 timeline'을 확인해보세요."
    )
    meta = g.annotate_response(text, persona_id="general_reader")
    assert meta["alarm"] is False
