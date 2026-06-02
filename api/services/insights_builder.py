"""기사 인사이트 builder - 시나리오 C.

기사 → 관련 토픽 · 의안 · 의원 · 정치 균형 점수 통합. 합성 article generator를
풀로 사용하고 토픽·정당 catalog 결합. 페르소나별 후속 행동 hint.

References:
- spec §3.1 시나리오 C
- data/synthetic/article.py (Article generator)
- data/synthetic/topics.py (Topic 카탈로그)
- api/services/guardrails.py (political_balance_score)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from data.synthetic.article import generate_articles
from data.synthetic.topics import TOPIC_SEEDS
from data.schemas import Article

from api.services import guardrails

__all__ = [
    "ArticleListEntry",
    "TopicLink",
    "InsightDetail",
    "list_articles",
    "build_insight",
    "list_topics",
]


# 합성 풀 크기 - 30-60분 데모에 충분 (페이징·필터 시연 가능).
_POOL_SIZE = 60


@lru_cache(maxsize=1)
def _article_pool() -> tuple[Article, ...]:
    """결정적 합성 풀. seed 고정 - 동일 article_id 반복 가능."""
    return tuple(generate_articles(count=_POOL_SIZE))


@dataclass(frozen=True)
class TopicLink:
    """기사가 참조하는 토픽."""
    topic_id: str
    name: str
    category: str


@dataclass(frozen=True)
class ArticleListEntry:
    """리스트 응답 - 가볍게."""
    article_id: str
    title: str
    published_at: str        # ISO 8601
    author: str
    topic_count: int
    referenced_persons: int
    referenced_bills: int
    primary_topic: Optional[TopicLink]


@dataclass(frozen=True)
class InsightDetail:
    """디테일 응답 - 전체 + 인사이트 집합."""
    article_id: str
    title: str
    content: str
    published_at: str
    author: str
    topics: list[TopicLink]
    referenced_person_ids: list[str]
    referenced_bill_ids: list[str]
    political_balance_score: float
    balance_alarm: bool
    summary: str             # AI 요약 (PoC mock)
    insights: list[str]      # 3-5 인사이트 bullet


def _topic_for(topic_id: str) -> Optional[TopicLink]:
    """topic_id → TopicLink 변환."""
    seed = next((t for t in TOPIC_SEEDS if t.id == topic_id), None)
    if seed is None:
        return None
    return TopicLink(topic_id=seed.id, name=seed.name, category=seed.category)


def _to_list_entry(art: Article) -> ArticleListEntry:
    """Article → 리스트 entry."""
    primary = _topic_for(art.topic_ids[0]) if art.topic_ids else None
    return ArticleListEntry(
        article_id=art.article_id,
        title=art.title,
        published_at=art.published_at.isoformat(),
        author=art.author,
        topic_count=len(art.topic_ids),
        referenced_persons=len(art.referenced_person_ids),
        referenced_bills=len(art.referenced_bill_ids),
        primary_topic=primary,
    )


def _generate_insights(art: Article, primary_topic: Optional[TopicLink]) -> list[str]:
    """기사 본문에서 추출 가능한 인사이트 3-5개 (PoC mock).

    Production: Sonnet 4.6 + retrieval로 동적 추출. PoC는 토픽·참조 entity·발의 패턴 기반.
    """
    insights: list[str] = []

    if primary_topic:
        insights.append(
            f"주제는 {primary_topic.name} ({primary_topic.category} 카테고리) - "
            "동일 카테고리 의안 trend 추적 권장."
        )

    if art.referenced_bill_ids:
        insights.append(
            f"관련 의안 {len(art.referenced_bill_ids)}건: {', '.join(art.referenced_bill_ids[:2])}"
            + (" 외" if len(art.referenced_bill_ids) > 2 else "")
            + " - 본회의 표결 진행 상황 후속 추적 권장."
        )

    if art.referenced_person_ids:
        insights.append(
            f"핵심 발의자/공동발의자 {len(art.referenced_person_ids)}명: "
            f"{', '.join(art.referenced_person_ids[:3])}"
            + (" 외" if len(art.referenced_person_ids) > 3 else "")
            + " - 의원 정치 여정 페이지에서 활동 timeline 확인 가능."
        )

    insights.append(
        "양당 표결 일치율이 본문에 인용됨 - 표결 이상치(시나리오 K)와 cross-reference 가능."
    )

    if len(art.topic_ids) > 1:
        other_topics = [_topic_for(t) for t in art.topic_ids[1:]]
        other_names = [t.name for t in other_topics if t]
        if other_names:
            insights.append(
                f"부수 토픽 {len(other_names)}개 ({', '.join(other_names[:2])}) - "
                "다중 카테고리 융합 의제로 분석 가치 ↑."
            )

    return insights[:5]


def _summary_for(art: Article, primary_topic: Optional[TopicLink]) -> str:
    """기사 핵심 요약 - PoC mock."""
    topic_name = primary_topic.name if primary_topic else "일반"
    return (
        f"본 기사는 {topic_name} 분야의 22대 국회 입법 동향을 분석. "
        f"발의 의원 {len(art.referenced_person_ids)}명 · 관련 의안 {len(art.referenced_bill_ids)}건 참조. "
        f"본문은 양당 균형 인용을 포함하며 출처(국회 OpenAPI) 명시. "
        f"(원문 작성자: {art.author})"
    )


# ─── 공개 API ───────────────────────────────────────────────────────────────


def list_articles(
    *,
    offset: int = 0,
    limit: int = 20,
    topic_id: Optional[str] = None,
) -> tuple[int, list[ArticleListEntry]]:
    """기사 리스트 - 페이징 + 토픽 필터.

    Returns: (total_after_filter, page_entries)
    """
    pool = _article_pool()
    if topic_id:
        filtered = [a for a in pool if topic_id in a.topic_ids]
    else:
        filtered = list(pool)
    # 발행일 내림차순 - 최신 우선
    filtered.sort(key=lambda a: a.published_at, reverse=True)
    page = filtered[offset:offset + limit]
    return len(filtered), [_to_list_entry(a) for a in page]


def build_insight(article_id: str) -> Optional[InsightDetail]:
    """단일 기사 인사이트 디테일."""
    pool = _article_pool()
    art = next((a for a in pool if a.article_id == article_id), None)
    if art is None:
        return None

    topics = [_topic_for(tid) for tid in art.topic_ids]
    topics_clean = [t for t in topics if t]
    primary = topics_clean[0] if topics_clean else None

    score, _components = guardrails.political_balance_score(art.content)
    return InsightDetail(
        article_id=art.article_id,
        title=art.title,
        content=art.content,
        published_at=art.published_at.isoformat(),
        author=art.author,
        topics=topics_clean,
        referenced_person_ids=list(art.referenced_person_ids),
        referenced_bill_ids=list(art.referenced_bill_ids),
        political_balance_score=round(score, 3),
        balance_alarm=score < guardrails.ALARM_THRESHOLD,
        summary=_summary_for(art, primary),
        insights=_generate_insights(art, primary),
    )


def list_topics() -> list[TopicLink]:
    """카탈로그 - 필터 옵션용."""
    return [
        TopicLink(topic_id=t.id, name=t.name, category=t.category)
        for t in TOPIC_SEEDS
    ]
