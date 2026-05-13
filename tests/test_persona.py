"""api.services.persona SSOT smoke 테스트.

검증 대상:
- 6 페르소나 등록 완료 (ADR-0002)
- 모든 페르소나에 필수 필드 채워짐 (특히 tone·system_prompt_suffix)
- get() lookup이 unknown id에 editorial fallback
- system_prompt() 항상 NEUTRALITY_GUARD_SUFFIX 첨부 (ADR-0004 Layer 2)
- ad_policy_for() 페르소나별 정책 분기 정확
- scenario_priority 14개 모두 포함

ADR-0004 Layer 4 (정치 성향 추론 필드 금지)는 CI의 별도 grep job에서 검증.
"""
from __future__ import annotations
import pytest

from api.services import persona


PERSONA_IDS_EXPECTED = {
    "editorial",
    "data_ai",
    "ad_sales",
    "general_reader",
    "paid_subscriber",
    "b2b",
}

SCENARIO_CODES_ALL = set("ABCDEFGHIJKLMN")  # 14개


def test_six_personas_registered():
    """6 페르소나가 모두 PERSONA_REGISTRY에 등록되어야 한다 (ADR-0002)."""
    assert set(persona.PERSONA_REGISTRY.keys()) == PERSONA_IDS_EXPECTED


@pytest.mark.parametrize("pid", sorted(PERSONA_IDS_EXPECTED))
def test_persona_required_fields_populated(pid):
    """모든 페르소나에 8개 필수 필드가 비어있지 않게 채워져야 한다."""
    p = persona.PERSONA_REGISTRY[pid]
    assert p["name_kr"], f"{pid}: name_kr empty"
    assert p["tier"] in ("staff", "b2c_free", "b2c_paid", "b2b"), f"{pid}: invalid tier"
    assert p["kpi_focus"], f"{pid}: kpi_focus empty"
    assert p["tone"].strip(), f"{pid}: tone empty — TODO USER INPUT 미완료"
    assert p["scenario_priority"], f"{pid}: scenario_priority empty"
    assert p["default_cohort"], f"{pid}: default_cohort empty"
    assert p["ad_policy"] in ("no_ads", "full_ads_agent", "no_ads_subscriber", "api_only"), f"{pid}: invalid ad_policy"
    assert p["system_prompt_suffix"].strip(), f"{pid}: system_prompt_suffix empty — TODO USER INPUT 미완료"


@pytest.mark.parametrize("pid", sorted(PERSONA_IDS_EXPECTED))
def test_scenario_priority_covers_all_14(pid):
    """각 페르소나의 scenario_priority가 14개 시나리오를 빠짐없이 포함."""
    priority = persona.PERSONA_REGISTRY[pid]["scenario_priority"]
    assert set(priority) == SCENARIO_CODES_ALL, (
        f"{pid}: scenario_priority covers {set(priority)}, "
        f"missing {SCENARIO_CODES_ALL - set(priority)}, "
        f"extra {set(priority) - SCENARIO_CODES_ALL}"
    )
    assert len(priority) == 14, f"{pid}: duplicates in scenario_priority"


def test_get_unknown_falls_back_to_editorial():
    """unknown persona_id는 editorial로 안전 fallback."""
    p = persona.get("nonexistent_persona")
    assert p["persona_id"] == "editorial"
    assert p["name_kr"] == "편집국"


def test_get_none_falls_back_to_editorial():
    """None도 editorial fallback."""
    p = persona.get(None)
    assert p["persona_id"] == "editorial"


@pytest.mark.parametrize("pid", sorted(PERSONA_IDS_EXPECTED))
def test_system_prompt_always_includes_neutrality_guard(pid):
    """ADR-0004 Layer 2: 모든 페르소나·시나리오에 NEUTRALITY_GUARD_SUFFIX 자동 첨부."""
    prompt = persona.system_prompt(pid, scenario_code="A")
    assert "[정치 중립성 가드" in prompt
    assert "단정적 가치 판단을 하지 마세요" in prompt
    assert "출처와 통계 근거" in prompt
    # ad_sales 페르소나도 예외 없음 (광고 매칭 판단도 같은 가드)
    if pid == "ad_sales":
        assert "[정치 중립성 가드" in prompt, "ad_sales도 정치 중립성 가드 예외 없음"


def test_system_prompt_includes_persona_tone_and_kpi():
    """system_prompt에 페르소나 tone과 KPI focus가 포함되어야 한다."""
    prompt = persona.system_prompt("editorial", scenario_code="C")
    assert "편집국" in prompt
    assert "시니어 정치부 기자" in prompt  # tone 일부
    assert "취재 신선도" in prompt  # KPI 일부
    assert "C" in prompt  # 시나리오 코드


def test_ad_policy_for_each_persona():
    """페르소나별 광고 정책 분기."""
    assert persona.ad_policy_for("editorial") == "no_ads"
    assert persona.ad_policy_for("data_ai") == "no_ads"
    assert persona.ad_policy_for("ad_sales") == "no_ads"
    assert persona.ad_policy_for("general_reader") == "full_ads_agent"
    assert persona.ad_policy_for("paid_subscriber") == "no_ads_subscriber"
    assert persona.ad_policy_for("b2b") == "api_only"


def test_all_persona_ids_returns_six():
    """GET /api/personas 엔드포인트가 6개 ID를 반환."""
    ids = persona.all_persona_ids()
    assert len(ids) == 6
    assert set(ids) == PERSONA_IDS_EXPECTED


def test_scenario_order_for_each_persona():
    """페르소나별 scenario_order가 14개 반환되고 첫 시나리오가 페르소나 특성과 매치."""
    # 편집국 1순위는 C (기사 인사이트)
    assert persona.scenario_order("editorial")[0] == "C"
    # 데이터·AI 1순위는 E (클러스터링)
    assert persona.scenario_order("data_ai")[0] == "E"
    # 광고/세일즈 1순위는 L (광고 매칭)
    assert persona.scenario_order("ad_sales")[0] == "L"
    # 일반 독자 1순위는 A (검색)
    assert persona.scenario_order("general_reader")[0] == "A"
    # 유료 구독자 1순위는 C (인사이트 - 심층)
    assert persona.scenario_order("paid_subscriber")[0] == "C"
    # B2B 1순위는 A (정책 검색)
    assert persona.scenario_order("b2b")[0] == "A"


def test_customer_facing_personas_have_distinct_tones():
    """대고객 3개 페르소나(general/paid/b2b)는 서로 구별되는 tone."""
    tones = {
        pid: persona.PERSONA_REGISTRY[pid]["tone"]
        for pid in ("general_reader", "paid_subscriber", "b2b")
    }
    assert len(set(tones.values())) == 3, f"중복 tone 발견: {tones}"


def test_neutrality_guard_suffix_constant_intact():
    """NEUTRALITY_GUARD_SUFFIX 상수가 4가지 원칙을 모두 포함해야 한다 (ADR-0004 Layer 2)."""
    guard = persona.NEUTRALITY_GUARD_SUFFIX
    assert "단정적 가치 판단을 하지 마세요" in guard
    assert "데이터 출처와 통계 근거" in guard
    assert "비판적 의견과 옹호 의견" in guard
    assert "사적 영역" in guard
    assert "political_balance_score" in guard
