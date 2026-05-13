"""시나리오 L - 광고 매칭 라우터 (AI 거버넌스 데모 메인).

엔드포인트:
- POST /api/ad-match           단일 모드 또는 3-way 비교 결과
- GET  /api/ad-match/modes     사용 가능한 모드 메타

핵심 메시지: 같은 콘텐츠·후보 광고에 대해 keyword/embedding/agent 세 모드가
어떻게 다르게 결정하는지 시연. 특히 정치인 비위 의혹 콘텐츠에서 Agent만 광고
거절(`chosen_ad_id=None`)하는 차이가 핵심.

페르소나 매핑:
- ad_sales: 매칭 결과 분석 + 광고주 평판 보호 trace (메인 사용자)
- general_reader: 단일 모드(agent) - 노출 광고만 받음
- editorial: 매칭 결정 검토 (편집국이 광고와 콘텐츠 충돌 체크)
- 그 외: 정보용

References:
- spec §3.4 시나리오 L 상세
- ADR-0004 Layer 6
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.services import ad_matcher
from api.services.persona import get as get_persona
from data.schemas import AdMatchDecision, AdMatchMode, Advertisement
from data.synthetic.advertisement import generate_advertisements
from data.synthetic.seeds import DEMO_TRAGIC_ARTICLE_ID

router = APIRouter(prefix="/api/ad-match", tags=["ad-match"])


# ─── Request / Response ─────────────────────────────────────────────────────

class AdMatchRequest(BaseModel):
    article_id: str = Field(min_length=1, max_length=64)
    mode: Literal["keyword", "embedding", "agent", "compare"] = "compare"


class DecisionModel(BaseModel):
    decision_id: str
    mode: str
    article_id: str
    candidate_ad_ids: list[str]
    chosen_ad_id: Optional[str]
    score: float
    reason_text: str


class AdMatchResponse(BaseModel):
    article_id: str
    persona_id: str
    mode: str
    results: dict[str, DecisionModel]
    governance_summary: dict


# ─── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("", response_model=AdMatchResponse)
def ad_match(
    req: AdMatchRequest,
    x_persona_id: Optional[str] = Header(default="ad_sales", alias="X-Persona-Id"),
) -> AdMatchResponse:
    """광고 매칭 결정 - 1개 또는 3-way 비교."""
    pid = x_persona_id or "ad_sales"
    article = _load_article(req.article_id)
    candidate_ads = _load_candidate_ads()

    if req.mode == "compare":
        decisions = ad_matcher.compare_modes(article, candidate_ads)
    else:
        decisions = {req.mode: ad_matcher.match(article, candidate_ads, req.mode)}  # type: ignore[arg-type]

    summary = _governance_summary(decisions)

    return AdMatchResponse(
        article_id=req.article_id,
        persona_id=pid,
        mode=req.mode,
        results={k: DecisionModel(**_decision_to_model(v)) for k, v in decisions.items()},
        governance_summary=summary,
    )


@router.get("/modes")
def list_modes() -> dict:
    """3 모드 + compare 메타."""
    return {
        "modes": [
            {
                "id": "keyword",
                "name": "Keyword Matching",
                "approach": "토픽-카테고리 단순 매칭",
                "limitation": "콘텐츠 민감성 감지 못 함. 비위 의혹 콘텐츠에도 광고 매칭.",
            },
            {
                "id": "embedding",
                "name": "Embedding Similarity",
                "approach": "Cohere embed-v4 코사인 유사도",
                "limitation": "의미 유사성은 잡지만 윤리·평판 판단 불가.",
            },
            {
                "id": "agent",
                "name": "Agent Judgment (★)",
                "approach": "Bedrock 판단 - 윤리·평판·맥락 종합",
                "differentiator": "민감 콘텐츠(비위/비극/미성년) 감지 → 광고 노출 생략",
            },
            {
                "id": "compare",
                "name": "3-way 비교 (데모 메인)",
                "approach": "3 모드 동시 실행 → 차이 시연",
            },
        ],
        "adr_reference": "ADR-0004 Layer 6 (광고 매칭 거버넌스)",
    }


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────

def _load_article(article_id: str) -> ad_matcher.ArticleSummary:
    """article fetch - PoC는 mock fixtures, production은 Neptune lookup.

    DEMO_TRAGIC_ARTICLE_ID로 호출하면 비위 의혹 콘텐츠 시드 반환 (Agent가 거절해야 함).
    그 외는 무난한 정책 정보성 콘텐츠.
    """
    if article_id == DEMO_TRAGIC_ARTICLE_ID:
        return ad_matcher.ArticleSummary(
            article_id=DEMO_TRAGIC_ARTICLE_ID,
            title="○○○ 의원 위증 의혹 - 검찰 수사 진행 중",
            content=(
                "○○○ 의원에 대한 위증 의혹이 제기된 가운데 검찰 수사가 진행 중이다. "
                "관련 사실관계는 아직 확정되지 않았으며 의혹 단계임을 명시한다."
            ),
            topic_ids=["topic_judicial"],
        )

    # 일반 정책 정보성 콘텐츠 (Agent가 광고 허용)
    return ad_matcher.ArticleSummary(
        article_id=article_id,
        title="AI 산업 진흥 종합 대책 - 22대 국회 1분기 분석",
        content=(
            "22대 국회 첫 분기 AI 관련 의안 10건이 발의됐다. "
            "더불어민주당 5건, 국민의힘 3건 등 양당 협력적 의제로 정착."
        ),
        topic_ids=["topic_ai", "topic_data"],
    )


def _load_candidate_ads() -> list[Advertisement]:
    """후보 광고 풀 - PoC는 합성 generator 30건. production은 DynamoDB.

    데모용으로 다양한 카테고리·avoid_topics를 가진 광고가 등장하도록.
    """
    return list(generate_advertisements(count=30, seed=42))


def _governance_summary(decisions: dict[str, AdMatchDecision]) -> dict:
    """3 모드 결정의 윤리·거버넌스 차이 요약 (UI 강조용)."""
    skipped_modes = [m for m, d in decisions.items() if d.chosen_ad_id is None]
    chosen_modes = {m: d.chosen_ad_id for m, d in decisions.items() if d.chosen_ad_id is not None}

    return {
        "total_modes": len(decisions),
        "modes_skipped_ads": skipped_modes,
        "modes_chose_ads": chosen_modes,
        "key_message": (
            "Agent 모드만 광고를 거절 - 다른 모드는 매칭 진행." if "agent" in skipped_modes
            else "모든 모드가 광고 매칭 진행 (안전 콘텐츠)."
        ),
    }


def _decision_to_model(d: AdMatchDecision) -> dict:
    return {
        "decision_id": d.decision_id,
        "mode": d.mode,
        "article_id": d.article_id,
        "candidate_ad_ids": d.candidate_ad_ids,
        "chosen_ad_id": d.chosen_ad_id,
        "score": d.score,
        "reason_text": d.reason_text,
    }
