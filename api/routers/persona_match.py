"""시나리오 D - 페르소나 매칭 라우터.

엔드포인트:
- GET  /api/persona-match/article/{article_id}   기사 → 6 페르소나 매칭
- POST /api/persona-match/text                    임의 텍스트 → 6 페르소나 매칭
- GET  /api/persona-match/matrix                  카테고리 affinity 매트릭스 (메타)

원리:
- 토픽 카테고리 affinity (가중치 0.6)
- KPI keyword 매칭 (0.25)
- tone fit (정치 균형 score 기반, 0.15)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.services import persona_match_builder

router = APIRouter(prefix="/api/persona-match", tags=["persona-match"])


class PersonaScoreModel(BaseModel):
    persona_id: str
    name_kr: str
    score: float
    topic_affinity: float
    kpi_keyword_match: float
    tone_fit: float
    reasons: list[str]


class MatchResultModel(BaseModel):
    persona_id: str                # 호출한 페르소나 (echo)
    source_kind: str
    source_id: Optional[str] = None
    title: str
    content_excerpt: str
    topic_categories: list[str]
    balance_score: float
    scores: list[PersonaScoreModel]
    top_persona_id: str
    rationale: str


class MatrixResponse(BaseModel):
    persona_id: str
    matrix: dict[str, dict[str, int]]
    weights: dict[str, float]
    note: str


class TextRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=4000)
    topic_category_hints: Optional[list[str]] = None


def _to_score_model(s: persona_match_builder.PersonaScore) -> PersonaScoreModel:
    return PersonaScoreModel(
        persona_id=s.persona_id,
        name_kr=s.name_kr,
        score=s.score,
        topic_affinity=s.topic_affinity,
        kpi_keyword_match=s.kpi_keyword_match,
        tone_fit=s.tone_fit,
        reasons=list(s.reasons),
    )


def _to_match_result_model(
    r: persona_match_builder.MatchResult, persona_id: str,
) -> MatchResultModel:
    return MatchResultModel(
        persona_id=persona_id,
        source_kind=r.source_kind,
        source_id=r.source_id,
        title=r.title,
        content_excerpt=r.content_excerpt,
        topic_categories=list(r.topic_categories),
        balance_score=r.balance_score,
        scores=[_to_score_model(s) for s in r.scores],
        top_persona_id=r.top_persona_id,
        rationale=r.rationale,
    )


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("/matrix", response_model=MatrixResponse)
def get_matrix(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> MatrixResponse:
    """페르소나 × 카테고리 affinity 매트릭스 (메타)."""
    pid = x_persona_id or "editorial"
    return MatrixResponse(
        persona_id=pid,
        matrix=persona_match_builder.PERSONA_AFFINITY_MATRIX,
        weights={
            "topic_affinity": persona_match_builder.WEIGHT_TOPIC_AFFINITY,
            "kpi_keyword": persona_match_builder.WEIGHT_KPI_KEYWORD,
            "tone_fit": persona_match_builder.WEIGHT_TONE_FIT,
        },
        note=(
            "0=무관심, 5=가장 중요. PoC 결정적 affinity. "
            "Production: Cohere embed-v4 + persona profile cosine."
        ),
    )


@router.get("/article/{article_id}", response_model=MatchResultModel)
def match_article(
    article_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> MatchResultModel:
    """기사 ID → 6 페르소나 매칭."""
    pid = x_persona_id or "editorial"
    result = persona_match_builder.match_article(article_id)
    if result is None:
        raise HTTPException(404, f"기사 '{article_id}' 없음")
    return _to_match_result_model(result, pid)


@router.post("/text", response_model=MatchResultModel)
def match_text(
    request: TextRequest,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> MatchResultModel:
    """임의 텍스트 → 6 페르소나 매칭. category_hints로 카테고리 강제 가능."""
    pid = x_persona_id or "editorial"
    result = persona_match_builder.match_text(
        request.text, topic_category_hints=request.topic_category_hints,
    )
    return _to_match_result_model(result, pid)
