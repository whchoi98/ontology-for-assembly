"""합성 Article generator - 시나리오 B/C/J/M·N에서 검색·추천 데이터로 활용.

설계 원칙:
1. Seed 기반 결정적 출력 (재현 가능) - 동일 seed → 동일 데이터.
2. 정치 균형: 정당 언급이 있는 기사는 양당 빈도 균형 (CV<0.3) 유지.
3. Pydantic Article 모델 strict validation - schema 위반 자동 차단.
4. source="synthetic" 강제 - DataSourceBadge 호환.

References:
- spec §4.1 (Article 클래스)
- ADR-0004 (정치 중립성)
- data/synthetic/topics.py (Topic 카탈로그)
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Iterator

from data.schemas import Article
from data.synthetic.topics import TOPIC_SEEDS, list_topic_ids

__all__ = ["generate_articles", "AUTHOR_POOL"]


# ─── 합성 자산 풀 ────────────────────────────────────────────────────────────

# 익명 작성자 풀 (실제 기자명 미사용 - 합성 식별자).
AUTHOR_POOL: tuple[str, ...] = tuple(f"author_{c}" for c in "ABCDEFGHIJ")

# 합성 의원·법안 ID 풀 (실 OpenAPI 어댑터 출력과 동일 형식).
PERSON_ID_POOL: tuple[str, ...] = tuple(f"MONA_{i:03d}" for i in range(1, 101))
BILL_ID_POOL: tuple[str, ...] = tuple(f"B22{yy:02d}{n:04d}" for yy in (5, 6) for n in range(1, 51))

# 정당 카탈로그 (guardrails.KNOWN_PARTIES와 정합).
PARTIES: tuple[str, ...] = ("더불어민주당", "국민의힘", "정의당", "진보당", "개혁신당", "무소속")

# 기사 제목 템플릿 (토픽 카테고리별 다양).
TITLE_TEMPLATES: tuple[str, ...] = (
    "{topic_name} 분야 의안 동향 분석",
    "22대 국회 {topic_name} 입법 현황",
    "{topic_name} 정책의 1분기 리뷰",
    "{topic_name}에 대한 국회 논의 경과",
    "{topic_name} 관련 법안 발의 트렌드",
    "{topic_name} 분야 공동발의 네트워크",
    "{topic_name} 정책 - 위원회 심사 진행 상황",
    "{topic_name}에 관한 양당 협력 패턴",
    "{topic_name} 분야 후속 입법 방향",
)


# ─── Content 합성 (정치 균형 강제) ───────────────────────────────────────────

def _generate_content(
    rng: random.Random,
    topic_name: str,
    referenced_persons: list[str],
) -> str:
    """기사 본문 생성. 정당 언급은 항상 양당 균형, 출처 인용 포함.

    political_balance_score ≥0.8 보장 (양당 균형 + 출처 + 단정 표현 없음).
    """
    # 균형 잡힌 정당 발의 건수 (CV<0.3 유지)
    n_dem = rng.randint(3, 7)
    n_ppp = n_dem + rng.choice([-1, 0, 0, 1])  # ±1 이내 유지

    # 50% 확률로 추가 정당도 언급 (multi-party balance)
    extra_parties = ""
    if rng.random() < 0.5 and len(PARTIES) > 2:
        extra = rng.choice(PARTIES[2:])
        n_extra = rng.randint(1, 3)
        extra_parties = f", {extra} {n_extra}건"

    # 의원 참조 (anonymized code)
    person_refs = ""
    if referenced_persons:
        person_refs = (
            f" 핵심 발의자는 {referenced_persons[0]} 의원이며, "
            f"공동발의 의원으로 {', '.join(referenced_persons[1:3]) if len(referenced_persons) > 1 else ''} 등이 참여."
        )

    month = rng.randint(1, 5)

    paragraph_1 = (
        f"{topic_name} 분야는 22대 국회에서 활발히 논의되고 있다. "
        f"올해 1분기 기준 더불어민주당 {n_dem}건, 국민의힘 {n_ppp}건{extra_parties}이 "
        f"발의되었다 (출처: 국회 OpenAPI 2026-0{month})."
        f"{person_refs}"
    )

    paragraph_2 = (
        f"\n\n표결에서 양당의 일치율은 {rng.randint(55, 75)}%로 협력적 양상을 보였다. "
        f"위원회 심사 단계의 법안은 {rng.randint(1, 4)}건, 본회의 상정은 {rng.randint(0, 2)}건이다 "
        f"(출처: 국회 본회의 회의록 2026-0{month})."
    )

    return paragraph_1 + paragraph_2


# ─── Generator 본체 ─────────────────────────────────────────────────────────

def generate_articles(
    count: int = 2000,
    seed: int = 20260513,
    base_date: datetime | None = None,
) -> Iterator[Article]:
    """합성 Article 노드 generator.

    Args:
        count: 생성할 기사 수 (기본 2,000).
        seed: 결정적 출력을 위한 RNG seed.
        base_date: 기사 published_at 기준일 (None이면 2026-05-13 UTC).

    Yields:
        Article — Pydantic strict 검증된 합성 기사 노드.

    Examples:
        >>> articles = list(generate_articles(count=10))
        >>> len(articles)
        10
        >>> all(a.source == "synthetic" for a in articles)
        True
    """
    rng = random.Random(seed)
    base = base_date or datetime(2026, 5, 13, tzinfo=timezone.utc)
    topic_ids = list_topic_ids()

    for idx in range(count):
        # 토픽 1-3개 샘플
        n_topics = rng.randint(1, 3)
        chosen_topics = rng.sample(topic_ids, n_topics)
        primary_topic_id = chosen_topics[0]
        primary_topic = next(t for t in TOPIC_SEEDS if t.id == primary_topic_id)

        # 참조 의원 0-3명
        n_persons = rng.randint(0, 3)
        ref_persons = rng.sample(PERSON_ID_POOL, n_persons) if n_persons > 0 else []

        # 참조 법안 0-2건
        n_bills = rng.randint(0, 2)
        ref_bills = rng.sample(BILL_ID_POOL, n_bills) if n_bills > 0 else []

        # 게시 시각: 최근 1년 (base_date 기준 과거)
        days_offset = rng.randint(0, 365)
        seconds_offset = rng.randint(0, 86400)
        published_at = base - timedelta(days=days_offset, seconds=seconds_offset)

        # 제목
        title_template = rng.choice(TITLE_TEMPLATES)
        title = title_template.format(topic_name=primary_topic.name)

        # 본문 (정치 균형 강제)
        content = _generate_content(rng, primary_topic.name, ref_persons)

        # 작성자
        author = rng.choice(AUTHOR_POOL)

        yield Article(
            article_id=f"art_{idx:05d}",
            title=title,
            content=content,
            published_at=published_at,
            author=author,
            topic_ids=chosen_topics,
            referenced_person_ids=ref_persons,
            referenced_bill_ids=ref_bills,
            source="synthetic",
        )
