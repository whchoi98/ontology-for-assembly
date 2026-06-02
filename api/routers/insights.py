"""시나리오 C - 기사 인사이트 라우터.

엔드포인트:
- GET /api/insights/topics                토픽 카탈로그 (25 시드)
- GET /api/insights/articles              기사 페이징 리스트 (토픽 필터)
- GET /api/insights/articles/{article_id} 단일 기사 + 인사이트

페르소나 차별:
- editorial: 후속 취재 hint
- data_ai: 코호트 매칭 hint
- ad_sales: 인접 광고 인벤토리 hint
- general_reader: 친절한 안내
- paid_subscriber: PDF 인사이트 export
- b2b: API 응답 자동화 hint
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.services import insights_builder
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/insights", tags=["insights"])


class TopicLinkModel(BaseModel):
    topic_id: str
    name: str
    category: str


class ArticleListEntryModel(BaseModel):
    article_id: str
    title: str
    published_at: str
    author: str
    topic_count: int
    referenced_persons: int
    referenced_bills: int
    primary_topic: Optional[TopicLinkModel] = None


class ArticleListResponse(BaseModel):
    persona_id: str
    total: int
    offset: int
    limit: int
    topic_filter: Optional[str] = None
    articles: list[ArticleListEntryModel]


class TopicsResponse(BaseModel):
    persona_id: str
    total: int
    topics: list[TopicLinkModel]


class InsightDetailResponse(BaseModel):
    persona_id: str
    article_id: str
    title: str
    content: str
    published_at: str
    author: str
    topics: list[TopicLinkModel]
    referenced_person_ids: list[str]
    referenced_bill_ids: list[str]
    political_balance_score: float
    balance_alarm: bool
    summary: str
    insights: list[str]
    extras: dict = Field(default_factory=dict)


def _to_topic_model(t: insights_builder.TopicLink) -> TopicLinkModel:
    return TopicLinkModel(topic_id=t.topic_id, name=t.name, category=t.category)


def _to_list_entry_model(e: insights_builder.ArticleListEntry) -> ArticleListEntryModel:
    return ArticleListEntryModel(
        article_id=e.article_id,
        title=e.title,
        published_at=e.published_at,
        author=e.author,
        topic_count=e.topic_count,
        referenced_persons=e.referenced_persons,
        referenced_bills=e.referenced_bills,
        primary_topic=_to_topic_model(e.primary_topic) if e.primary_topic else None,
    )


def _persona_extras(pid: str, persona: dict, detail: insights_builder.InsightDetail) -> dict:
    """페르소나별 부가 정보."""
    base = {
        "persona_name_kr": persona.get("name_kr", ""),
        "tone": persona.get("tone", ""),
    }
    if pid == "editorial":
        topic_name = detail.topics[0].name if detail.topics else "관련 토픽"
        base["follow_up_hint"] = (
            f"후속 취재: {topic_name} 분야 추가 의안 발의 추이 + "
            f"참조 의원 {len(detail.referenced_person_ids)}명 추적 권장."
        )
    elif pid == "data_ai":
        base["cohort_hint"] = (
            f"이 기사 reader cohort + 동일 토픽 기사 reader 비교 → 페르소나 매칭(시나리오 D) 입력."
        )
    elif pid == "ad_sales":
        base["ad_hint"] = (
            "이 기사는 toned-down 정치 콘텐츠. 광고 매칭(시나리오 L) 정상 흐름 적용 가능."
        )
    elif pid == "general_reader":
        base["guide_hint"] = (
            f"이 기사는 {detail.topics[0].name if detail.topics else '정책'} 주제로 "
            f"본문 안에 양당 정보가 균형 있게 포함되어 있어요."
        )
    elif pid == "paid_subscriber":
        base["premium_cta"] = "PDF 인사이트 리포트 + 관련 의원 timeline 동시 export (premium)"
    elif pid == "b2b":
        base["api_response_hint"] = (
            "응답 JSON의 referenced_bill_ids·person_ids로 객체 그래프 자동 확장 가능."
        )
    return base


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("/topics", response_model=TopicsResponse)
def get_topics(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> TopicsResponse:
    """토픽 카탈로그 (필터 옵션용)."""
    pid = x_persona_id or "editorial"
    topics = insights_builder.list_topics()
    return TopicsResponse(
        persona_id=pid,
        total=len(topics),
        topics=[_to_topic_model(t) for t in topics],
    )


@router.get("/articles", response_model=ArticleListResponse)
def list_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    topic_id: Optional[str] = Query(None),
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ArticleListResponse:
    """기사 페이징 리스트."""
    pid = x_persona_id or "editorial"
    total, entries = insights_builder.list_articles(
        offset=offset, limit=limit, topic_id=topic_id,
    )
    return ArticleListResponse(
        persona_id=pid,
        total=total,
        offset=offset,
        limit=limit,
        topic_filter=topic_id,
        articles=[_to_list_entry_model(e) for e in entries],
    )


@router.get("/articles/{article_id}", response_model=InsightDetailResponse)
def get_insight(
    article_id: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> InsightDetailResponse:
    """단일 기사 + 인사이트 + 페르소나 extras."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    detail = insights_builder.build_insight(article_id)
    if detail is None:
        raise HTTPException(404, f"기사 '{article_id}' 없음")

    return InsightDetailResponse(
        persona_id=pid,
        article_id=detail.article_id,
        title=detail.title,
        content=detail.content,
        published_at=detail.published_at,
        author=detail.author,
        topics=[_to_topic_model(t) for t in detail.topics],
        referenced_person_ids=detail.referenced_person_ids,
        referenced_bill_ids=detail.referenced_bill_ids,
        political_balance_score=detail.political_balance_score,
        balance_alarm=detail.balance_alarm,
        summary=detail.summary,
        insights=detail.insights,
        extras=_persona_extras(pid, persona, detail),
    )
