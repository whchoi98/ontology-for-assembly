"""Generic AI 인사이트 라우터 — gcc 패턴 차용.

14 시나리오 모두에 동일한 `/api/insight?scenario={code}` 엔드포인트로
Sonnet 4.6 기반 페르소나별 해석을 제공.

각 시나리오는 다른 user_message 템플릿을 사용 (SCENARIO_PROMPTS).
backend의 bedrock.invoke 단일 진입점 → political_balance_score + Guardrails 자동.

References:
- ADR-0001 (Sonnet 4.6 고정, Haiku silent downgrade 금지)
- ADR-0004 (정치 중립성 다층 가드레일)
- 차용: ontology-for-gcc의 insights_pipeline 패턴
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/insight", tags=["insight"])


# 시나리오별 emoji + 시나리오별 핵심 분석 포인트 (gcc 5-섹션 패턴 차용)
SCENARIO_PROMPTS: dict[str, dict] = {
    "A": {"label": "의미 검색",       "emoji": "🔍",
          "focus": "검색 결과의 정당·시기·카테고리 분포, 의도-결과 정합성, 검색 정확도 메트릭"},
    "B": {"label": "3-stage 챗봇",    "emoji": "💬",
          "focus": "Chatbot/Agent/Agentic 3 모드 응답 비교, 각 모드 한계·강점, Agentic 추가 발견"},
    "C": {"label": "기사 인사이트",   "emoji": "📰",
          "focus": "기사 분석 결과, 편집 우선순위, 후속 취재 방향, 인용 가능 통계"},
    "D": {"label": "페르소나 매칭",   "emoji": "🎯",
          "focus": "affinity 매트릭스의 강·약 페어, 페르소나별 KPI fit, 콘텐츠 gap"},
    "E": {"label": "의원 클러스터링", "emoji": "🧩",
          "focus": "클러스터 특징(위원회·지역구·발의 패턴), 협력 그룹 구조, 이상치, 정파 표현 회피"},
    "F": {"label": "룩어라이크",       "emoji": "🪞",
          "focus": "유사도 근거, 정책 영향력, 후보군의 차별 포인트"},
    "G": {"label": "기사 ROI",        "emoji": "📊",
          "focus": "Bayesian 시뮬레이션 분포·신뢰구간, 캠페인 전략 권고"},
    "H": {"label": "지역구 지도",     "emoji": "🗺️",
          "focus": "17 시도 의원 분포, 지역별 의제 특성, 외부 신호 결합 가능성"},
    "I": {"label": "편향·중립성",     "emoji": "⚖️",
          "focus": "political_balance_score 분포 + 시계열·페르소나·시나리오별 패턴"},
    "J": {"label": "외부 신호 융합",  "emoji": "🌐",
          "focus": "네이버 뉴스 + SNS + 여론조사 cross-source 일치/불일치, 신호 가중치"},
    "K": {"label": "표결 이상치",     "emoji": "🚨",
          "focus": "이상치 패턴(정파 무관 표현), 시기·이슈 상관, 검증 데이터 포인트"},
    "L": {"label": "광고 매칭",       "emoji": "🤖",
          "focus": "키워드/임베딩/Agent 3-way 결정 비교, governance trace 해석"},
    "M": {"label": "의원 정치 여정",  "emoji": "🗓️",
          "focus": "timeline 전환점(위원회 이동·발의 burst·발언 증가), 시기별 활동 패턴"},
    "N": {"label": "이슈 × 입법",     "emoji": "📈",
          "focus": "토픽 트렌드 ↔ 법안 발의 산점도 상관, 시차 패턴, 통과율"},
    # ─── 확장 시나리오 (O–S) ────────────────────────────────────────────
    "O": {"label": "인물 관계 분석",  "emoji": "🤝",
          "focus": "두 의원 5 차원 (공동발의·표결·토픽·timeline·cluster) cross-tab + cross-party 협력 정량"},
    "P": {"label": "시민 청원 입법 매핑",  "emoji": "📮",
          "focus": "청원 카테고리 → 발의 의안 매칭률 + 이행 lifecycle (발의·심사·통과·시행)"},
    "Q": {"label": "위원회 영향력",   "emoji": "🏛️",
          "focus": "17 상임위 × 5 메트릭 heatmap + cross-committee 협력 + 시행령 단계 추적"},
    "R": {"label": "공약 이행 추적",  "emoji": "📋",
          "focus": "당선 공약 vs 실제 발의 이행률 + 미이행 분야 + 사회 신뢰 narrative"},
    "S": {"label": "토픽 burst 시계열", "emoji": "📊",
          "focus": "8 매크로 이슈 × 13 주차 line chart + Granger causality lag prediction"},
    # ─── Phase 4f 고급 인사이트 (T-W) — 74K real edges Cypher 분석 ──────────
    "T": {"label": "정당 응집도",     "emoji": "⚖️",
          "focus": "정당별 majority 일치율 ranking + active 표결만 분석 + 정당 분열 시그널 정량"},
    "U": {"label": "의원 영향력",     "emoji": "👑",
          "focus": "CO_PROPOSED_WITH cohort 가중치 + 발의 활동 합산 influence score + 네트워크 hub detection"},
    "V": {"label": "표결 cluster",    "emoji": "🎯",
          "focus": "yes_rate × 정당 5 cluster (보수/진보 × 신중/높은 찬성 + 중도) 자동 분류 + cluster narrative"},
    "W": {"label": "Swing voter",     "emoji": "🔀",
          "focus": "정당 majority 이탈 의원 ranking + 개별 신념·정책 차이 narrative + 후속 인터뷰 hook"},
}


# 페르소나별 권고 섹션 라벨 (시점·CTA 차별화)
PERSONA_CTA_LABEL: dict[str, str] = {
    "editorial":       "후속 취재 포인트 (3건)",
    "data_ai":         "추가 분석 가설 (3건)",
    "ad_sales":        "광고 매칭 전략 (3건)",
    "general_reader":  "관련해서 더 알고 싶다면 (2-3건)",
    "paid_subscriber": "심층 분석 + 알림 설정 권고 (3건)",
    "b2b":             "정책 모니터링 액션 (3건)",
}


def _build_user_message(
    scenario_code: str, persona_id: str, context_text: str, user_query: str,
) -> str:
    """gcc Cally 5섹션 패턴 + 이모지 + 페르소나 시점."""
    spec = SCENARIO_PROMPTS[scenario_code]
    emoji = spec["emoji"]
    label = spec["label"]
    focus = spec["focus"]
    cta_label = PERSONA_CTA_LABEL.get(persona_id, "권고 (3건)")

    return (
        f"# {emoji} {label} 시나리오 분석\n\n"
        + (f"사용자 원본 질문: {user_query}\n\n" if user_query else "")
        + f"## 분석 초점\n{focus}\n\n"
        + f"## 응답 데이터 (시나리오 응답 페이로드)\n```\n{context_text}\n```\n\n"
        + "---\n\n"
        + "**응답 형식 (반드시 다음 5섹션 markdown으로 한국어 작성)**:\n\n"
        + "## 📌 헤드라인\n"
        + "  핵심 발견 1-2문장. 정량 수치 포함.\n\n"
        + "## 🔍 핵심 발견\n"
        + "  bullet 3-5개. 각 bullet은 정량 메트릭 + 출처(real/synthetic/external) 명시.\n\n"
        + "## 👤 페르소나 시점 해석\n"
        + "  사용자 페르소나의 KPI 우선순위에 맞춰 어조·관심사 적용.\n"
        + "  2-3 문단. 페르소나 KPI 어휘 사용.\n\n"
        + "## 💡 비즈니스/취재 함의\n"
        + "  이 데이터가 의미하는 것 + 잠재적 임팩트. 2-3 문장.\n\n"
        + f"## 🎯 {cta_label}\n"
        + "  bullet 3개. 각 bullet은 구체적·실행 가능한 다음 단계 + 해당 의원/의안/토픽 ID 또는 시나리오 코드 참조.\n\n"
        + "**제약**:\n"
        + "- 모든 정량 수치에 출처 명시 (예: \"22대 임기 (2024-05 ~ 2026-05) · 국회 OpenAPI\")\n"
        + "- 정당명·이름은 공개 사실만 인용 (평가성 단정 금지)\n"
        + "- 정치인 사적 영역(가족·신념) 추론 금지\n"
        + "- ADR-0004 정치 중립성 가드 자동 적용 (응답 출력 후 balance_score 평가)\n"
    )


class InsightRequest(BaseModel):
    scenario_code: str = Field(pattern=r"^[A-W]$",
                               description="14 시나리오 A-N 중 하나")
    context: dict = Field(default_factory=dict,
                          description="시나리오 응답 데이터 (LLM에 컨텍스트로 전달)")
    user_query: Optional[str] = Field(
        default=None,
        description="사용자 원본 질문 (없으면 시나리오 default 사용)",
    )


class InsightResponse(BaseModel):
    scenario_code: str
    scenario_label: str
    persona_id: str
    tier_group_kr: str
    text: str
    political_balance_score: float
    alarm: bool
    model_id: str


@router.post("", response_model=InsightResponse)
def generate_insight(
    req: InsightRequest,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> InsightResponse:
    """시나리오·페르소나별 Sonnet 4.6 인사이트 생성.

    backend의 bedrock.invoke 단일 진입점 사용 → political_balance_score +
    Guardrails 자동. 시나리오에 따라 user_message 템플릿이 다름.
    """
    from api.services import bedrock
    from api.services.persona import PERSONA_REGISTRY, TIER_GROUP_KR

    pid = x_persona_id if x_persona_id in PERSONA_REGISTRY else "editorial"
    p = PERSONA_REGISTRY[pid]  # type: ignore[index]
    tg = TIER_GROUP_KR.get(p["tier"], p["tier"])

    spec = SCENARIO_PROMPTS.get(req.scenario_code)
    if spec is None:
        raise HTTPException(400, f"unknown scenario {req.scenario_code}")

    # 컨텍스트를 간결한 텍스트로 직렬화 (크기 제한)
    import json
    context_text = json.dumps(req.context, ensure_ascii=False, indent=2)
    if len(context_text) > 4000:
        context_text = context_text[:4000] + "\n... (truncated)"

    # gcc 5섹션 패턴 + 이모지 + 페르소나 CTA (Sonnet 4.6 + Guardrails 자동)
    user_message = _build_user_message(
        scenario_code=req.scenario_code,
        persona_id=pid,
        context_text=context_text,
        user_query=req.user_query or "",
    )

    result = bedrock.invoke(
        user_message=user_message,
        persona_id=pid,
        scenario_code=req.scenario_code,
    )

    return InsightResponse(
        scenario_code=req.scenario_code,
        scenario_label=spec["label"],
        persona_id=pid,
        tier_group_kr=tg,
        text=result.text,
        political_balance_score=result.political_balance_score,
        alarm=result.alarm,
        model_id=result.model_id,
    )
