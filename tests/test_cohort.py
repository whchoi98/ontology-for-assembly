"""api.services.cohort - 페르소나 × 시나리오 source 결정 검증."""
from __future__ import annotations
import pytest

from api.services import cohort


PERSONAS = ("editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b")
SCENARIOS = list("ABCDEFGHIJKLMN")


@pytest.mark.parametrize("pid", PERSONAS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_select_returns_list_for_every_persona_scenario(pid, scenario):
    """6 페르소나 × 14 시나리오 모두 list 반환 (84 케이스)."""
    result = cohort.select(pid, scenario)
    assert isinstance(result, list)
    assert len(result) >= 1


@pytest.mark.parametrize("pid", PERSONAS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_select_values_are_valid_sources(pid, scenario):
    """반환 값은 real/synthetic/external/* 중 하나."""
    valid = {"real", "synthetic", "external", "*"}
    result = cohort.select(pid, scenario)
    assert all(s in valid for s in result), f"{pid}·{scenario} → {result}"


def test_default_cohort_used_when_no_override():
    """시나리오 override가 없으면 페르소나의 default_cohort 사용."""
    # 'A' 시나리오는 SCENARIO_OVERRIDES에 없음
    assert "A" not in cohort.SCENARIO_OVERRIDES
    # editorial.default_cohort = ['real']
    assert cohort.select("editorial", "A") == ["real"]
    # paid_subscriber.default_cohort = ['real', 'external', 'synthetic']
    assert cohort.select("paid_subscriber", "A") == ["real", "external", "synthetic"]


def test_scenario_l_ad_match_uses_synthetic():
    """광고 매칭(L)은 모든 페르소나에서 synthetic 광고 인벤토리 사용."""
    for pid in PERSONAS:
        result = cohort.select(pid, "L")
        assert "synthetic" in result, f"{pid} L에 synthetic 누락: {result}"


def test_scenario_k_outlier_uses_real_only():
    """표결 이상치(K)는 real 입법 데이터만 (합성 위험)."""
    for pid in PERSONAS:
        result = cohort.select(pid, "K")
        assert result == ["real"], f"{pid} K가 real 외 사용: {result}"


def test_scenario_j_external_signal_includes_external():
    """외부 신호 융합(J)는 external 필수."""
    for pid in PERSONAS:
        result = cohort.select(pid, "J")
        assert "external" in result, f"{pid} J에 external 누락: {result}"


def test_scenario_n_issue_legislation_needs_real_and_external():
    """이슈×입법(N)은 real + external 둘 다 필요."""
    for pid in PERSONAS:
        result = cohort.select(pid, "N")
        assert "real" in result and "external" in result, f"{pid} N: {result}"


def test_select_unknown_persona_falls_back_to_editorial():
    """unknown persona는 editorial로 fallback (persona.get() 동작 의존)."""
    result = cohort.select("nonexistent", "A")
    assert result == ["real"]  # editorial default


def test_select_none_persona_falls_back_to_editorial():
    result = cohort.select(None, "A")
    assert result == ["real"]


def test_select_returns_copy_not_reference():
    """반환된 list 변형이 SCENARIO_OVERRIDES를 망가뜨리지 않아야 한다."""
    result = cohort.select("editorial", "L")
    result.append("real")  # caller mutation
    fresh = cohort.select("editorial", "L")
    assert "real" not in fresh or fresh.count("real") == 0  # synthetic만 있어야


# ─── to_cypher_filter ─────────────────────────────────────────────────────────

def test_to_cypher_filter_empty_returns_true():
    """빈 리스트 → 'TRUE' (no filter)."""
    assert cohort.to_cypher_filter([]) == "TRUE"


def test_to_cypher_filter_wildcard_returns_true():
    """['*'] → 'TRUE'."""
    assert cohort.to_cypher_filter(["*"]) == "TRUE"


def test_to_cypher_filter_single_source():
    assert cohort.to_cypher_filter(["real"]) == "n.source IN ['real']"


def test_to_cypher_filter_multi_source():
    assert cohort.to_cypher_filter(["real", "external"]) == "n.source IN ['real', 'external']"


def test_to_cypher_filter_custom_var():
    assert cohort.to_cypher_filter(["synthetic"], var="b") == "b.source IN ['synthetic']"


# ─── explain (audit trace) ────────────────────────────────────────────────────

def test_explain_default_path():
    """override 없는 시나리오는 default_cohort 적용."""
    info = cohort.explain("editorial", "A")
    assert info["persona_id"] == "editorial"
    assert info["scenario_code"] == "A"
    assert info["default_cohort"] == ["real"]
    assert info["override_applied"] is False
    assert info["override_cohort"] is None
    assert info["final_cohort"] == ["real"]


def test_explain_override_path():
    """override 적용 시 audit에 반영."""
    info = cohort.explain("editorial", "L")
    assert info["override_applied"] is True
    assert info["override_cohort"] == ["synthetic"]
    assert info["final_cohort"] == ["synthetic"]
    # default는 그대로 노출 (어디서 결정이 바뀌었는지 추적)
    assert info["default_cohort"] == ["real"]


# ─── 통합 ─────────────────────────────────────────────────────────────────────

def test_cohort_consistent_with_persona_registry():
    """select() 결과가 persona.PERSONA_REGISTRY와 모순되지 않아야 한다."""
    from api.services.persona import PERSONA_REGISTRY
    for pid in PERSONAS:
        for scenario in SCENARIOS:
            result = cohort.select(pid, scenario)
            # override가 없으면 default_cohort와 일치
            if scenario not in cohort.SCENARIO_OVERRIDES or pid not in cohort.SCENARIO_OVERRIDES.get(scenario, {}):
                assert result == list(PERSONA_REGISTRY[pid]["default_cohort"]), \
                    f"{pid}·{scenario}: override 없는데 default와 다름 ({result} vs {PERSONA_REGISTRY[pid]['default_cohort']})"
