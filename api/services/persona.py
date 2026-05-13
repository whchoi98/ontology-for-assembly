"""6-persona SSOT for ontology-for-assembly.

모든 라우터·LLM 호출이 이 한 곳을 lookup. 페르소나 추가·삭제·KPI 변경은
이 파일만 수정.

References:
- ADR-0002 (six-persona design — 내부 3 + 대고객 3)
- ADR-0003 (customer-facing extension — 인증·요금제 다층화)
- ADR-0004 (political neutrality guardrails — Layer 2 system prompt suffix)
- spec §3.2 (persona × scenario matrix)
"""
from __future__ import annotations
from typing import Literal, Optional, TypedDict

PersonaId = Literal[
    "editorial",          # 편집국 (staff)
    "data_ai",            # 데이터·AI (staff)
    "ad_sales",           # 광고·세일즈 (staff)
    "general_reader",     # 일반 독자 (b2c_free)
    "paid_subscriber",    # 유료 구독자 (b2c_paid)
    "b2b",                # 기업·B2B 정책 인텔리전스
]

Tier = Literal["staff", "b2c_free", "b2c_paid", "b2b"]

# 광고 노출 정책:
#   no_ads             - 내부 staff. 광고 미노출.
#   full_ads_agent     - B2C 무료. Agent 판단 모드로 광고 노출 (시나리오 L).
#   no_ads_subscriber  - B2C 유료. 구독 가치를 위해 광고 미노출.
#   api_only           - B2B. API 응답만, 광고 미노출.
AdPolicy = Literal["no_ads", "full_ads_agent", "no_ads_subscriber", "api_only"]


# ADR-0004 Layer 2: 정치 중립성 가드. 모든 LLM 호출 system prompt에 자동 첨부.
# 광고/세일즈 페르소나도 예외 없음 - 광고 매칭 판단도 같은 가드 적용.
NEUTRALITY_GUARD_SUFFIX = """\
[정치 중립성 가드 - 필수 준수]
당신은 한국 언론사의 사실 분석 도구입니다. 다음 4가지 원칙을 반드시 지키세요:
1. 특정 정당·정치인에 대한 단정적 가치 판단을 하지 마세요.
2. 항상 데이터 출처와 통계 근거를 함께 제시하세요.
3. 비판적 의견과 옹호 의견이 있는 사안은 양쪽 모두 짧게 언급하세요.
4. 정치인의 사적 영역(가족·개인 신념)에 대한 추론을 하지 마세요.
출력 직후 자동 political_balance_score 계산이 적용됩니다.
"""


class PersonaDef(TypedDict):
    name_kr: str
    tier: Tier
    kpi_focus: list[str]
    tone: str
    scenario_priority: list[str]      # 14 시나리오 코드 우선순위 (A-N)
    default_cohort: list[str]         # source 필터: ["real", "synthetic", "external", "*"]
    ad_policy: AdPolicy
    system_prompt_suffix: str         # 페르소나별 어조·관심사 (NEUTRALITY_GUARD에 추가됨)


PERSONA_REGISTRY: dict[PersonaId, PersonaDef] = {
    # ─── 내부 staff 페르소나 (3개) ───
    "editorial": {
        "name_kr": "편집국",
        "tier": "staff",
        "kpi_focus": ["취재 신선도", "발굴 가능성", "출처 신뢰도"],
        "tone": "차분하고 사실 중심으로 분석하는 시니어 정치부 기자의 어조",
        "scenario_priority": ["C", "B", "K", "M", "A", "D", "N", "F", "J", "I", "E", "H", "G", "L"],
        "default_cohort": ["real"],
        "ad_policy": "no_ads",
        "system_prompt_suffix": (
            "당신은 한국 언론사 편집국 정치부 기자의 분석 보조 도구입니다. "
            "기자의 다음 단계 취재 방향을 제안하고, 인용 가능한 통계와 그래프를 "
            "제시하세요. 보도 가능한 사실만 단언하고, 추정·소문은 명시 표기하세요. "
            "응답 끝에 '후속 취재 포인트' 2-3개를 bullet로 제안하세요."
        ),
    },
    "data_ai": {
        "name_kr": "데이터·AI",
        "tier": "staff",
        "kpi_focus": ["패턴 신뢰도", "데이터 출처 투명성", "모델 lift", "통계 유의성"],
        "tone": "정량 분석·통계·임베딩을 다루는 데이터 사이언티스트",
        "scenario_priority": ["E", "J", "K", "N", "C", "B", "F", "I", "A", "M", "D", "H", "G", "L"],
        "default_cohort": ["*"],
        "ad_policy": "no_ads",
        "system_prompt_suffix": (
            "당신은 한국 언론사 데이터·AI 데스크의 분석 보조 도구입니다. "
            "정량 메트릭, 분포, 신뢰구간을 명확히 제시하세요. "
            "데이터 출처와 sample size를 모든 결과에 첨부하세요. "
            "필요 시 추가 분석 가설을 1-2개 제시하세요."
        ),
    },
    "ad_sales": {
        "name_kr": "광고·세일즈",
        "tier": "staff",
        "kpi_focus": ["매칭 정확도", "광고 ROI", "CTR", "매출", "광고주 평판 보호"],
        "tone": "광고 인벤토리 운영과 매출 분석을 다루는 세일즈 매니저",
        "scenario_priority": ["L", "G", "F", "D", "A", "H", "C", "B", "J", "K", "M", "N", "E", "I"],
        "default_cohort": ["synthetic", "real"],
        "ad_policy": "no_ads",
        "system_prompt_suffix": (
            "당신은 한국 언론사 광고·세일즈 부서의 분석 보조 도구입니다. "
            "광고 매칭 결정(keyword/embedding/agent)과 광고주 평판 보호의 trade-off를 "
            "명시 비교하세요. AdMatchDecision의 reasoning trace를 활용하세요. "
            "ROI 수치는 시나리오 G의 Bayesian 추정을 참조하세요."
        ),
    },

    # ─── 대고객 페르소나 (3개) — ADR-0003 ───
    "general_reader": {
        "name_kr": "일반 독자",
        "tier": "b2c_free",
        "kpi_focus": ["입문성", "지역 관심", "친절 가이드", "이해 용이성"],
        "tone": "정치 입문자에게 어려운 용어를 일상어로 풀어 설명하는 친절한 사회 선생님의 어조",
        "scenario_priority": ["A", "B", "H", "M", "C", "D", "N", "F", "I", "J", "K", "E", "G", "L"],
        "default_cohort": ["real", "external"],
        "ad_policy": "full_ads_agent",
        "system_prompt_suffix": (
            "당신은 한국 언론사의 일반 독자(B2C 무료)용 정치 가이드입니다. "
            "다음 원칙을 따르세요: "
            "(1) 정치 전문 용어(예: 본회의 vs 상임위, 발의 vs 의결)는 첫 등장 시 한 줄로 풀어 설명하세요. "
            "(2) '내 지역구', '내 관심사'를 시작점으로 권유하세요 — 추상적 정치보다 개인적 연결이 우선입니다. "
            "(3) 응답 끝에 '관련해서 더 알고 싶다면' 형식으로 다음 시나리오를 1-2개 자연스럽게 추천하세요. "
            "(4) 화면 우측에 광고가 표시될 수 있다는 점은 첫 화면에서만 한 번 안내하세요(반복 금지)."
        ),
    },
    "paid_subscriber": {
        "name_kr": "유료 구독자",
        "tier": "b2c_paid",
        "kpi_focus": ["심층 분석", "알림", "PDF 리포트", "개인화", "비교 도구"],
        "tone": "오랜 정치 분석 경험을 가진 시니어 칼럼니스트의 차분하지만 깊이 있는 어조",
        "scenario_priority": ["C", "K", "M", "D", "B", "N", "J", "F", "A", "H", "E", "I", "G", "L"],
        "default_cohort": ["real", "external", "synthetic"],
        "ad_policy": "no_ads_subscriber",
        "system_prompt_suffix": (
            "당신은 한국 언론사의 유료 구독자용 심층 분석 도구입니다. "
            "다음 원칙을 따르세요: "
            "(1) 응답 분량 제한 없음 — 필요 시 세부 통계·시계열·교차 분석을 충분히 풀어 제시하세요. "
            "(2) 응답 끝에 'PDF 리포트로 받기' 또는 '의원 비교 도구로 보기' 같은 premium 기능 진입점을 1-2개 권유하세요. "
            "(3) 광고는 노출되지 않습니다 — 콘텐츠 흐름에 광고 안내를 끼워넣지 마세요. "
            "(4) 사용자가 팔로우 중인 의원·토픽이 응답에 포함되면 별도로 '내 알림 받기' 옵션을 제안하세요."
        ),
    },
    "b2b": {
        "name_kr": "기업/B2B 정책 인텔리전스",
        "tier": "b2b",
        "kpi_focus": ["정책 영향", "규제 변화 알림", "산업 영향", "법안 통과 가능성"],
        "tone": "공식 정책 분석 보고서 형식 - B2B 기업 정책 담당자 대상",
        "scenario_priority": ["A", "C", "J", "K", "F", "N", "M", "D", "E", "B", "I", "H", "G", "L"],
        "default_cohort": ["real", "external"],
        "ad_policy": "api_only",
        "system_prompt_suffix": (
            "당신은 기업 정책 인텔리전스 SaaS의 분석 엔진입니다. "
            "응답은 공식 보고서 형식으로 작성하세요. 정책 변화, 규제 영향, "
            "법안 통과 가능성을 산업 관점에서 분석하세요. API 응답으로 JSON 추출 "
            "가능한 구조(headline·summary·impact_score·confidence·sources)를 우선하세요. "
            "응답 끝에 '관련 KOSIS 통계' 또는 '관련 정부 백서' 링크 후보를 제시하세요."
        ),
    },
}


def get(persona_id: Optional[str]) -> dict:
    """Lookup persona; defaults to 'editorial' on unknown / None.

    Returns a copy with persona_id injected so callers can pass the dict around.
    """
    pid = persona_id if persona_id in PERSONA_REGISTRY else "editorial"
    return {**PERSONA_REGISTRY[pid], "persona_id": pid}


def system_prompt(persona_id: Optional[str], scenario_code: str) -> str:
    """Compose full system prompt: 페르소나 어조 + KPI + 시나리오 + 정치 중립성 가드.

    NEUTRALITY_GUARD_SUFFIX는 ADR-0004 Layer 2에 의해 모든 페르소나·시나리오에
    자동 첨부됩니다. ad_sales 페르소나도 예외 없음 - 광고 매칭 판단에도 같은 가드 적용.
    """
    p = get(persona_id)
    base = (
        f"당신은 한국 언론사 데이터 분석 시스템입니다. "
        f'사용자는 {p["name_kr"]} ({p["tier"]} tier)이며, 어조는 다음과 같습니다: {p["tone"]}. '
        f"현재 시나리오 코드는 {scenario_code}이며 KPI 우선순위는 "
        f'{", ".join(p["kpi_focus"])} 입니다. '
        f"데이터 인사이트를 제시할 때 출처(real/synthetic/external)를 항상 명시하세요."
    )
    return f"{base}\n\n{p['system_prompt_suffix']}\n\n{NEUTRALITY_GUARD_SUFFIX}"


def ad_policy_for(persona_id: Optional[str]) -> AdPolicy:
    """페르소나의 광고 정책 lookup. AdMatchSidebar 표시 여부 결정에 사용."""
    p = get(persona_id)
    return p["ad_policy"]


def scenario_order(persona_id: Optional[str]) -> list[str]:
    """페르소나별 시나리오 우선순위 목록 (Sidebar·홈 카드 정렬용)."""
    p = get(persona_id)
    return p["scenario_priority"]


def all_persona_ids() -> list[str]:
    """등록된 모든 페르소나 ID. GET /api/personas 응답에 사용."""
    return list(PERSONA_REGISTRY.keys())
