"""페르소나 매칭 builder - 시나리오 D.

기사(또는 임의 콘텐츠) → 6 페르소나 적합도 점수 매트릭스. 결과는 각 페르소나의
점수 + 매칭 reason + 권장 시나리오 (PERSONA_REGISTRY.scenario_priority의 첫 번째).

매칭 로직 (가중 합):
1. 토픽 카테고리 affinity (페르소나별 사전 정의)
2. KPI keyword 본문/제목 매칭
3. tone fit (기사 정치 균형 점수 vs 페르소나 정치 노출 적합도)

PoC: 결정적 점수. Production: Cohere embed-v4 + 페르소나 임베딩 cosine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from api.services import guardrails, insights_builder
from api.services.persona import PERSONA_REGISTRY

__all__ = [
    "PersonaScore",
    "MatchResult",
    "match_article",
    "match_text",
    "PERSONA_AFFINITY_MATRIX",
]


# ─── 페르소나 × 토픽 카테고리 affinity (0-5) ────────────────────────────────
# 카테고리: 산업·경제·사회·환경·법무·문화 (data/synthetic/topics.py 카테고리와 정합).
# 0 = 무관심, 5 = 가장 중요.

PERSONA_AFFINITY_MATRIX: dict[str, dict[str, int]] = {
    "editorial": {
        "산업": 4, "경제": 4, "사회": 4, "환경": 4, "법무": 4, "문화": 3,
    },
    "data_ai": {
        "산업": 5, "경제": 4, "사회": 3, "환경": 3, "법무": 3, "문화": 2,
    },
    "ad_sales": {
        "산업": 3, "경제": 5, "사회": 3, "환경": 2, "법무": 2, "문화": 4,
    },
    "general_reader": {
        "산업": 3, "경제": 3, "사회": 5, "환경": 4, "법무": 3, "문화": 4,
    },
    "paid_subscriber": {
        "산업": 4, "경제": 4, "사회": 4, "환경": 4, "법무": 4, "문화": 3,
    },
    "b2b": {
        "산업": 5, "경제": 5, "사회": 3, "환경": 3, "법무": 4, "문화": 2,
    },
}


# 가중치 (합 = 1.0).
WEIGHT_TOPIC_AFFINITY = 0.6
WEIGHT_KPI_KEYWORD = 0.25
WEIGHT_TONE_FIT = 0.15


@dataclass(frozen=True)
class PersonaScore:
    """1 페르소나의 매칭 점수 + 이유."""
    persona_id: str
    name_kr: str
    score: float                # 0-1
    topic_affinity: float       # 컴포넌트 1
    kpi_keyword_match: float    # 컴포넌트 2
    tone_fit: float             # 컴포넌트 3
    reasons: list[str]


@dataclass(frozen=True)
class MatchResult:
    """매칭 전체 결과."""
    source_kind: str            # "article" or "text"
    source_id: Optional[str]    # article_id (text면 None)
    title: str
    content_excerpt: str
    topic_categories: list[str]
    balance_score: float
    scores: list[PersonaScore]  # score 내림차순
    top_persona_id: str
    rationale: str              # 1-2문장 추천 사유


# ─── 매칭 로직 ──────────────────────────────────────────────────────────────


def _topic_affinity_score(topic_categories: list[str], persona_id: str) -> float:
    """카테고리 affinity 평균 / 5 (0-1)."""
    if not topic_categories:
        return 0.5  # neutral
    matrix = PERSONA_AFFINITY_MATRIX.get(persona_id, {})
    scores = [matrix.get(c, 2) for c in topic_categories]  # 미정의 = 2 (중립)
    return sum(scores) / (len(scores) * 5)


def _kpi_keyword_score(text: str, persona_id: str) -> tuple[float, list[str]]:
    """페르소나 kpi_focus 키워드가 본문에 등장하는지."""
    persona = PERSONA_REGISTRY.get(persona_id, {})
    kpi = persona.get("kpi_focus", [])
    if not kpi:
        return 0.5, []
    matched: list[str] = []
    for kw in kpi:
        # 키워드 자체 또는 첫 2글자(어근)가 본문에 있는지
        if kw in text or (len(kw) >= 3 and kw[:2] in text):
            matched.append(kw)
    score = min(1.0, len(matched) / max(1, len(kpi)))
    return score, matched


def _tone_fit_score(balance_score: float, persona_id: str) -> float:
    """페르소나별 정치 콘텐츠 노출 적합도.

    - editorial / data_ai / paid_subscriber / b2b: balance≥0.8이면 풀 점수, 미만은 비례 감점
    - general_reader: balance≥0.85일수록 좋음 (소비자 보호)
    - ad_sales: balance≥0.95일수록 좋음 (광고 안전성 최우선)
    """
    if persona_id == "ad_sales":
        return max(0.0, (balance_score - 0.7) / 0.3)  # 0.7~1.0 normalize
    if persona_id == "general_reader":
        return max(0.0, (balance_score - 0.6) / 0.4)
    # 내부·paid·b2b
    if balance_score >= 0.8:
        return 1.0
    return max(0.0, balance_score / 0.8)


def _build_reasons(
    persona_id: str,
    topic_aff: float,
    kpi_score: float,
    tone_fit: float,
    matched_kpi: list[str],
    topic_categories: list[str],
) -> list[str]:
    """매칭 reason 자연어 문장."""
    persona = PERSONA_REGISTRY.get(persona_id, {})
    name_kr = persona.get("name_kr", persona_id)
    reasons: list[str] = []
    if topic_aff >= 0.7:
        reasons.append(
            f"{name_kr} 관심 카테고리({', '.join(set(topic_categories))})와 affinity 높음 "
            f"({topic_aff:.2f})"
        )
    elif topic_aff <= 0.4:
        reasons.append(
            f"{name_kr} 관심 카테고리와 affinity 낮음 ({topic_aff:.2f})"
        )
    if matched_kpi:
        reasons.append(f"KPI keyword 매칭: {', '.join(matched_kpi[:3])}")
    if tone_fit >= 0.9:
        reasons.append(f"{name_kr} 톤 적합도 우수 ({tone_fit:.2f})")
    elif tone_fit < 0.6:
        reasons.append(f"{name_kr} 톤 적합도 미흡 ({tone_fit:.2f}) - 정치 균형 부족 가능")
    if not reasons:
        reasons.append("중립적 매칭 - 특별한 시그널 없음")
    return reasons


def _score_one_persona(
    persona_id: str, topic_categories: list[str], text: str, balance_score: float,
) -> PersonaScore:
    """단일 페르소나 점수 계산."""
    persona = PERSONA_REGISTRY.get(persona_id, {})
    topic_aff = _topic_affinity_score(topic_categories, persona_id)
    kpi_score, matched_kpi = _kpi_keyword_score(text, persona_id)
    tone_fit = _tone_fit_score(balance_score, persona_id)

    total = (
        WEIGHT_TOPIC_AFFINITY * topic_aff
        + WEIGHT_KPI_KEYWORD * kpi_score
        + WEIGHT_TONE_FIT * tone_fit
    )

    reasons = _build_reasons(persona_id, topic_aff, kpi_score, tone_fit, matched_kpi, topic_categories)

    return PersonaScore(
        persona_id=persona_id,
        name_kr=persona.get("name_kr", persona_id),
        score=round(total, 3),
        topic_affinity=round(topic_aff, 3),
        kpi_keyword_match=round(kpi_score, 3),
        tone_fit=round(tone_fit, 3),
        reasons=reasons,
    )


def _rationale_for_top(top: PersonaScore, all_scores: list[PersonaScore]) -> str:
    """1-2문장 권장 사유 - top vs runner-up."""
    if len(all_scores) < 2:
        return f"{top.name_kr} 페르소나가 단독 후보로 가장 적합."
    runner_up = all_scores[1]
    margin = top.score - runner_up.score
    if margin < 0.05:
        return (
            f"{top.name_kr} 페르소나가 미세 우위 (점수 차 {margin:.3f}). "
            f"차순위 {runner_up.name_kr}와 함께 dual-track 고려 가능."
        )
    return (
        f"{top.name_kr} 페르소나가 우세 (점수 {top.score:.2f}, "
        f"차순위 {runner_up.name_kr} 대비 +{margin:.2f})."
    )


# ─── 공개 API ───────────────────────────────────────────────────────────────


def match_article(article_id: str) -> Optional[MatchResult]:
    """기사 ID → MatchResult."""
    detail = insights_builder.build_insight(article_id)
    if detail is None:
        return None

    topic_categories = [t.category for t in detail.topics]
    text = f"{detail.title}\n\n{detail.content}"
    scores = [
        _score_one_persona(pid, topic_categories, text, detail.political_balance_score)
        for pid in PERSONA_REGISTRY.keys()
    ]
    scores.sort(key=lambda s: -s.score)

    return MatchResult(
        source_kind="article",
        source_id=detail.article_id,
        title=detail.title,
        content_excerpt=detail.content[:200] + ("…" if len(detail.content) > 200 else ""),
        topic_categories=list(set(topic_categories)),
        balance_score=detail.political_balance_score,
        scores=scores,
        top_persona_id=scores[0].persona_id,
        rationale=_rationale_for_top(scores[0], scores),
    )


def match_text(text: str, topic_category_hints: Optional[list[str]] = None) -> MatchResult:
    """임의 텍스트 → MatchResult.

    topic_category_hints가 없으면 본문에서 키워드로 카테고리 추론 (PoC 단순 매칭).
    """
    balance_score, _ = guardrails.political_balance_score(text)
    categories = topic_category_hints or _infer_categories(text)

    scores = [
        _score_one_persona(pid, categories, text, balance_score)
        for pid in PERSONA_REGISTRY.keys()
    ]
    scores.sort(key=lambda s: -s.score)

    return MatchResult(
        source_kind="text",
        source_id=None,
        title="(직접 입력 텍스트)",
        content_excerpt=text[:200] + ("…" if len(text) > 200 else ""),
        topic_categories=categories,
        balance_score=round(balance_score, 3),
        scores=scores,
        top_persona_id=scores[0].persona_id,
        rationale=_rationale_for_top(scores[0], scores),
    )


# 카테고리 키워드 - PoC 간단 매칭. Production은 LLM classification.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "산업": ("AI", "인공지능", "산업", "에너지", "통신", "디지털", "기술"),
    "경제": ("금융", "세금", "재정", "예산", "공정거래", "창업", "중소"),
    "사회": ("복지", "의료", "청년", "주거", "노동", "교육", "인구"),
    "환경": ("환경", "기후", "탄소", "재생에너지"),
    "법무": ("개인정보", "프라이버시", "사법", "법무"),
    "문화": ("문화", "예술", "체육", "콘텐츠", "방송"),
}


def _infer_categories(text: str) -> list[str]:
    """텍스트에서 카테고리 후보 추출."""
    matched: list[str] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                matched.append(category)
                break
    return matched or ["사회"]  # 기본값
