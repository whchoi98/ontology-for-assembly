"""광고 매칭 서비스 - 시나리오 L 핵심.

3 모드 비교:
- keyword: 토픽·카테고리 단순 매칭 (전통적)
- embedding: 임베딩 유사도 (Cohere embed-v4, mock에서는 deterministic hash 기반)
- agent: Bedrock 판단 - 윤리·평판·콘텐츠 적합성 종합 분석

핵심 차별점 (ADR-0004 Layer 6): Agent 모드만 비위 의혹·비극·미성년 피해 콘텐츠를
감지하여 광고 노출 생략 (`chosen_ad_id=None`). 다른 모드는 항상 광고 매칭.

References:
- spec §3.4 시나리오 L 광고 매칭 매트릭스
- ADR-0004 Layer 6 (광고 매칭 거버넌스)
- data/schemas.py AdMatchDecision
- data/synthetic/seeds.py DEMO_TRAGIC_ARTICLE_ID
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from data.schemas import AdMatchDecision, AdMatchMode, Advertisement

__all__ = [
    "match",
    "compare_modes",
    "SENSITIVE_PATTERNS",
    "ArticleSummary",
]


# ─── 민감 콘텐츠 감지 패턴 (ADR-0004 Layer 6) ───────────────────────────────
# Agent 모드만 이 패턴을 인식해 광고 노출 거절. keyword/embedding은 인식 못 함.
SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("scandal",       re.compile(r"(비위|위증|뇌물|수사\s*진행|기소|구속|혐의)")),
    ("tragedy",       re.compile(r"(사망|참사|재난|희생|피해자)")),
    ("minor_victim",  re.compile(r"(미성년|아동\s*피해|청소년\s*피해)")),
    ("controversy",   re.compile(r"(폭로|의혹|논란|충돌\s*보도)")),
)


@dataclass(frozen=True)
class ArticleSummary:
    """광고 매칭 입력 - article 핵심 필드만."""
    article_id: str
    title: str
    content: str
    topic_ids: list[str]


# ─── 진입점 ─────────────────────────────────────────────────────────────────

def match(
    article: ArticleSummary,
    candidate_ads: list[Advertisement],
    mode: AdMatchMode = "agent",
) -> AdMatchDecision:
    """단일 모드 광고 매칭.

    Args:
        article: 매칭 대상 콘텐츠.
        candidate_ads: 후보 광고 풀.
        mode: keyword | embedding | agent.

    Returns:
        AdMatchDecision. `chosen_ad_id=None`이면 광고 노출 생략.
    """
    if mode == "keyword":
        return _match_keyword(article, candidate_ads)
    if mode == "embedding":
        return _match_embedding(article, candidate_ads)
    if mode == "agent":
        return _match_agent(article, candidate_ads)
    raise ValueError(f"unsupported mode: {mode}")


def compare_modes(
    article: ArticleSummary,
    candidate_ads: list[Advertisement],
) -> dict[str, AdMatchDecision]:
    """3 모드 모두 실행 → 비교용 dict.

    데모 메인 - 같은 콘텐츠·후보에 대해 3 모드가 어떻게 다르게 결정하는지 시연.
    """
    return {
        "keyword": _match_keyword(article, candidate_ads),
        "embedding": _match_embedding(article, candidate_ads),
        "agent": _match_agent(article, candidate_ads),
    }


# ─── Mode 1: keyword ────────────────────────────────────────────────────────

# 토픽 ID → 광고 카테고리 간단 매핑 (현실적 키워드 매칭의 한계 시연).
TOPIC_TO_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "topic_ai": ("data_solutions", "cloud", "security"),
    "topic_data": ("data_solutions", "compliance", "security"),
    "topic_finance": ("fintech",),
    "topic_health": ("healthcare",),
    "topic_environment": ("sustainability",),
    "topic_energy": ("sustainability", "automotive"),
    "topic_education": ("education",),
    "topic_telecom": ("telecom",),
}


def _match_keyword(article: ArticleSummary, ads: list[Advertisement]) -> AdMatchDecision:
    """토픽-카테고리 단순 매칭. 평균 점수 0.4~0.6 (낮은 정확도).

    한계: 민감 콘텐츠 감지 불가 - 정치인 비위 의혹에도 광고 매칭함.
    """
    # 후보 카테고리 추출
    hinted_cats: set[str] = set()
    for tid in article.topic_ids:
        for cat in TOPIC_TO_CATEGORY_HINTS.get(tid, ()):
            hinted_cats.add(cat)

    scored: list[tuple[Advertisement, float]] = []
    for ad in ads:
        score = 0.5 if ad.category in hinted_cats else 0.3
        scored.append((ad, score))

    scored.sort(key=lambda x: -x[1])
    chosen = scored[0] if scored else None
    chosen_id = chosen[0].ad_id if chosen else None
    chosen_score = chosen[1] if chosen else 0.0

    reason = (
        f"keyword match: 토픽 카테고리 hint {sorted(hinted_cats) or 'none'} → "
        f"chosen={chosen_id} score={chosen_score:.2f}. "
        "한계: 콘텐츠 민감성 감지 못 함."
    )

    return _build_decision(
        article=article,
        candidate_ids=[ad.ad_id for ad in ads],
        chosen_ad_id=chosen_id,
        mode="keyword",
        score=chosen_score,
        reason=reason,
    )


# ─── Mode 2: embedding ──────────────────────────────────────────────────────

def _match_embedding(article: ArticleSummary, ads: list[Advertisement]) -> AdMatchDecision:
    """임베딩 유사도 (PoC mock은 deterministic hash 기반).

    실 환경에서는 Cohere embed-v4 호출. mock은 article·ad 텍스트의 해시로 결정적
    score 산출 → 같은 입력 = 같은 score.

    한계: 의미적 유사성은 잡지만 윤리·평판 판단 불가.
    """
    article_vector = _hash_vector(article.title + " " + article.content)
    scored: list[tuple[Advertisement, float]] = []
    for ad in ads:
        ad_vector = _hash_vector(ad.advertiser + " " + ad.content_summary + " " + ad.category)
        sim = _cosine_lite(article_vector, ad_vector)
        # 회피 토픽 매칭 시 점수 감점
        for at in ad.avoid_topics:
            if at in article.topic_ids:
                sim *= 0.3
        scored.append((ad, sim))

    scored.sort(key=lambda x: -x[1])
    chosen = scored[0] if scored else None
    chosen_id = chosen[0].ad_id if chosen else None
    chosen_score = chosen[1] if chosen else 0.0

    reason = (
        f"embedding similarity: cosine top={chosen_id} score={chosen_score:.2f}. "
        "avoid_topics 감점 적용. 한계: 윤리·평판 판단 불가."
    )

    return _build_decision(
        article=article,
        candidate_ids=[ad.ad_id for ad in ads],
        chosen_ad_id=chosen_id,
        mode="embedding",
        score=chosen_score,
        reason=reason,
    )


def _hash_vector(text: str, dims: int = 8) -> list[float]:
    """텍스트 → 결정적 float 벡터 (mock 임베딩)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [(b - 128) / 128.0 for b in digest[:dims]]


def _cosine_lite(a: list[float], b: list[float]) -> float:
    """0~1 사이로 정규화한 코사인 유사도."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, (dot / (na * nb) + 1) / 2))


# ─── Mode 3: agent (★ 데모 메인) ────────────────────────────────────────────

def _match_agent(article: ArticleSummary, ads: list[Advertisement]) -> AdMatchDecision:
    """Bedrock 판단 모드 - 윤리·평판·맥락 종합.

    ★ ADR-0004 Layer 6 trigger:
       민감 콘텐츠 감지 시 chosen_ad_id=None (광고 노출 생략).
       reason_text에 거절 근거 명시 → 운영 콘솔 트레이스.

    PoC mock에서는 SENSITIVE_PATTERNS로 감지. production은 Bedrock invoke.
    """
    # 1) 민감 콘텐츠 감지
    sensitive_hits = _detect_sensitive(article)
    if sensitive_hits:
        category_names = ", ".join(sorted(sensitive_hits))
        reason = (
            f"skip — 민감 콘텐츠 감지 ({category_names}). "
            f"근거: '{article.title[:40]}...' 본문에서 {len(sensitive_hits)}개 sensitive 패턴 일치. "
            "회피: 모든 광고주 평판 보호 (ADR-0004 Layer 6 trigger)."
        )
        return _build_decision(
            article=article,
            candidate_ids=[ad.ad_id for ad in ads],
            chosen_ad_id=None,
            mode="agent",
            score=0.0,
            reason=reason,
        )

    # 2) 광고주 avoid_topics 체크 (Agent는 keyword보다 더 엄격)
    safe_ads: list[Advertisement] = []
    rejected_by_avoid: list[str] = []
    for ad in ads:
        conflict = set(ad.avoid_topics) & set(article.topic_ids)
        if conflict:
            rejected_by_avoid.append(f"{ad.ad_id} (avoid: {sorted(conflict)})")
        else:
            safe_ads.append(ad)

    # 3) 안전 광고 중 keyword 점수 산출 (간단 카테고리 매칭)
    if not safe_ads:
        reason = (
            "skip — 모든 후보 광고가 avoid_topics 충돌. "
            f"거절: {len(rejected_by_avoid)}개. 회피 광고주: {rejected_by_avoid[:3]}"
        )
        return _build_decision(
            article=article,
            candidate_ids=[ad.ad_id for ad in ads],
            chosen_ad_id=None,
            mode="agent",
            score=0.0,
            reason=reason,
        )

    # 4) 안전한 후보 중 점수 산출 (간단 룰 + 신뢰도 가중)
    scored: list[tuple[Advertisement, float]] = []
    for ad in safe_ads:
        hint_match = any(
            ad.category in TOPIC_TO_CATEGORY_HINTS.get(tid, ())
            for tid in article.topic_ids
        )
        base = 0.75 if hint_match else 0.55
        scored.append((ad, base))

    scored.sort(key=lambda x: -x[1])
    chosen, chosen_score = scored[0]

    reason = (
        f"allow — 정책 정보성 콘텐츠. chosen={chosen.ad_id} score={chosen_score:.2f}. "
        f"안전 후보 {len(safe_ads)}건 (rejected by avoid_topics: {len(rejected_by_avoid)}건). "
        f"광고주 평판 보호 통과."
    )

    return _build_decision(
        article=article,
        candidate_ids=[ad.ad_id for ad in ads],
        chosen_ad_id=chosen.ad_id,
        mode="agent",
        score=chosen_score,
        reason=reason,
    )


def _detect_sensitive(article: ArticleSummary) -> set[str]:
    """본문·제목에서 민감 카테고리 감지."""
    text = (article.title + " " + article.content).lower()
    text_raw = article.title + " " + article.content  # 한국어 정규식은 대소문자 무관
    found: set[str] = set()
    for category, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text_raw):
            found.add(category)
    return found


# ─── 공통 빌더 ──────────────────────────────────────────────────────────────

def _build_decision(
    article: ArticleSummary,
    candidate_ids: list[str],
    chosen_ad_id: Optional[str],
    mode: AdMatchMode,
    score: float,
    reason: str,
) -> AdMatchDecision:
    """결정 ID는 article + mode + 현재 시각 해시로 deterministic."""
    raw = f"{article.article_id}:{mode}:{datetime.now(timezone.utc).isoformat()[:13]}"
    decision_id = "dec_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return AdMatchDecision(
        decision_id=decision_id,
        mode=mode,
        article_id=article.article_id,
        candidate_ad_ids=list(candidate_ids),
        chosen_ad_id=chosen_ad_id,
        score=max(0.0, min(1.0, score)),
        reason_text=reason,
        timestamp=datetime.now(timezone.utc),
        source="synthetic",
    )
