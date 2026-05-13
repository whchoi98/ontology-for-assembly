"""페르소나 × 시나리오 data source cohort 결정 - single point.

기본 정책: 페르소나의 `default_cohort` 사용.
override: 특정 시나리오는 의미상 특정 source만 사용해야 함 (예: 광고 매칭 L은
항상 synthetic 광고 인벤토리, 표결 이상치 K는 real OpenAPI만).

모든 라우터·Cypher 쿼리가 이 함수를 통과해야 데이터 출처 일관성 + DataSourceBadge
정합성이 보장된다.
"""
from __future__ import annotations

from api.services.persona import get

# 시나리오별 override. 페르소나 default_cohort보다 우선.
# 형식: scenario_code -> {persona_id -> override_cohort}.
# persona_id가 없으면 default_cohort fallback.
SCENARIO_OVERRIDES: dict[str, dict[str, list[str]]] = {
    # G 기사 ROI 시뮬레이션: 합성 독자 행동 필수
    "G": {
        "editorial": ["synthetic"],
        "data_ai": ["synthetic", "real"],
        "ad_sales": ["synthetic", "real"],
        "general_reader": ["synthetic"],
        "paid_subscriber": ["synthetic"],
        "b2b": ["synthetic", "real"],
    },
    # J 외부 신호 융합: external 필수
    "J": {
        "editorial": ["real", "external"],
        "data_ai": ["real", "external"],
        "ad_sales": ["real", "external", "synthetic"],
        "general_reader": ["external", "real"],
        "paid_subscriber": ["real", "external"],
        "b2b": ["real", "external"],
    },
    # K 표결 이상치: real 입법 데이터만 (합성 위험)
    "K": {
        "editorial": ["real"],
        "data_ai": ["real"],
        "ad_sales": ["real"],
        "general_reader": ["real"],
        "paid_subscriber": ["real"],
        "b2b": ["real"],
    },
    # L 광고 매칭: 합성 광고 인벤토리 필수 (real 광고 보유 없음)
    "L": {
        "editorial": ["synthetic"],
        "data_ai": ["synthetic", "real"],
        "ad_sales": ["synthetic", "real"],
        "general_reader": ["synthetic", "real"],
        "paid_subscriber": ["synthetic", "real"],
        "b2b": ["synthetic", "real"],
    },
    # N 이슈 × 입법 상관: real 입법 + external 사회 시그널 필수
    "N": {
        "editorial": ["real", "external"],
        "data_ai": ["real", "external"],
        "ad_sales": ["real", "external"],
        "general_reader": ["real", "external"],
        "paid_subscriber": ["real", "external", "synthetic"],
        "b2b": ["real", "external"],
    },
}


def select(persona_id: str | None, scenario_code: str) -> list[str]:
    """페르소나 × 시나리오 → data source list 결정.

    Returns:
        list of Source values to filter by.
        ["*"] 또는 빈 리스트 = no filter (all sources allowed).

    Examples:
        select("editorial", "A") → ["real"]                # 편집국 default
        select("paid_subscriber", "C") → ["real", "external", "synthetic"]
        select("editorial", "L") → ["synthetic"]           # L scenario override
        select("ad_sales", "K") → ["real"]                 # K scenario override
    """
    persona = get(persona_id)  # editorial fallback 내장
    pid = persona["persona_id"]

    override_table = SCENARIO_OVERRIDES.get(scenario_code)
    if override_table is not None and pid in override_table:
        return list(override_table[pid])

    return list(persona["default_cohort"])


def to_cypher_filter(sources: list[str], var: str = "n") -> str:
    """source 리스트를 Cypher WHERE 절 fragment로 변환.

    Args:
        sources: ["real"] | ["real", "external"] | ["*"] | []
        var: Cypher 변수명 (예: "p" for Person, "b" for Bill)

    Returns:
        "TRUE" (no filter) or "p.source IN ['real', 'external']"

    `*` 포함 또는 빈 리스트 = no filter (모든 source 통과).
    """
    if not sources or "*" in sources:
        return "TRUE"
    # 따옴표 안전 - source 값은 Literal로 제한된 enum이므로 injection 위험 없음
    quoted = ", ".join(f"'{s}'" for s in sources)
    return f"{var}.source IN [{quoted}]"


def explain(persona_id: str | None, scenario_code: str) -> dict:
    """select() 결정 이유를 audit 형식으로 반환. 운영 콘솔 트레이스 panel용."""
    persona = get(persona_id)
    pid = persona["persona_id"]
    default = list(persona["default_cohort"])

    override_table = SCENARIO_OVERRIDES.get(scenario_code)
    override = override_table.get(pid) if override_table else None

    return {
        "persona_id": pid,
        "scenario_code": scenario_code,
        "default_cohort": default,
        "override_applied": override is not None,
        "override_cohort": list(override) if override is not None else None,
        "final_cohort": list(override) if override is not None else default,
    }
