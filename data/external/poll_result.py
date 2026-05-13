"""여론조사 결과 generator → PollResult.

실 API 미존재 (한국갤럽·리얼미터는 paid + 비공개 endpoint). PoC에서는 100% 합성.
실 데이터 연동은 후속 (Phase 5).

설계 원칙 (ADR-0004):
- 정당별 지지율 합 = 100% 보장
- 한 정당이 60% 초과 금지 (현실적 분포)
- 토픽별 의견은 "찬성·반대·잘 모름" 3분류
- 정치 성향 추론·예측 절대 미포함

References:
- spec §4.1 PollResult 클래스
- ADR-0004 (정치 중립성)
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Iterator

from data.schemas import PollResult
from data.synthetic.topics import list_topic_ids

__all__ = ["generate_polls", "POLLSTERS"]


# 합성 여론조사 기관 (실명 미사용).
POLLSTERS: tuple[str, ...] = (
    "Synth-Poll-A",
    "Synth-Poll-B",
    "Synth-Poll-C",
    "Synth-Survey-D",
)


# 합성 정당 지지율 - 한 정당 60% 초과 금지.
PARTY_NAMES: tuple[str, ...] = (
    "더불어민주당", "국민의힘", "정의당", "진보당", "개혁신당", "무소속·기타",
)


def _generate_party_breakdown(rng: random.Random) -> dict[str, float]:
    """정당 지지율 - 가중 디리클레 비슷한 분포, 균형 보장."""
    # 2개 메이저 정당 합 60-70%, 나머지 30-40% 분산
    major_sum = rng.uniform(0.55, 0.70)
    # major 1, 2 분배 - 비율 0.4~0.6
    a_ratio = rng.uniform(0.40, 0.60)
    major_a = round(major_sum * a_ratio * 100, 1)
    major_b = round(major_sum * (1 - a_ratio) * 100, 1)

    # 나머지 4개 = 100 - major_sum*100 분배
    remaining = 100 - major_a - major_b
    minor_a = round(remaining * 0.25, 1)
    minor_b = round(remaining * 0.20, 1)
    minor_c = round(remaining * 0.20, 1)
    minor_d = round(100 - major_a - major_b - minor_a - minor_b - minor_c, 1)

    return {
        "더불어민주당": major_a,
        "국민의힘": major_b,
        "정의당": minor_a,
        "진보당": minor_b,
        "개혁신당": minor_c,
        "무소속·기타": max(0.0, minor_d),
    }


def _generate_topic_opinion(rng: random.Random) -> dict[str, float]:
    """토픽 의견 - 찬성/반대/잘 모름."""
    pro = round(rng.uniform(0.35, 0.55) * 100, 1)
    con = round(rng.uniform(0.25, 0.45) * 100, 1)
    unknown = round(100 - pro - con, 1)
    return {"찬성": pro, "반대": con, "잘 모름": max(0.0, unknown)}


def generate_polls(
    count: int = 50,
    seed: int = 20260513,
    base_date: date | None = None,
) -> Iterator[PollResult]:
    """합성 여론조사 generator.

    Args:
        count: 생성할 조사 수.
        seed: RNG seed.
        base_date: 조사 시점 기준일.

    Yields:
        PollResult — 정당 지지율 또는 토픽 의견 균형 분포.
    """
    rng = random.Random(seed)
    base = base_date or date(2026, 5, 13)
    topic_ids = list_topic_ids()

    for idx in range(count):
        # 50% 정당 지지율, 50% 토픽 의견
        is_party_support = rng.random() < 0.5

        if is_party_support:
            breakdown = _generate_party_breakdown(rng)
            topic = "정당 지지율"
        else:
            topic_id = rng.choice(topic_ids)
            from data.synthetic.topics import get as topic_get
            topic_seed = topic_get(topic_id)
            topic = topic_seed.name if topic_seed else topic_id
            breakdown = _generate_topic_opinion(rng)

        # 조사 일자: 최근 1년 내
        days_offset = rng.randint(0, 365)
        poll_date = base - timedelta(days=days_offset)

        # 표본 크기: 500-2000
        sample_size = rng.choice([500, 700, 800, 1000, 1500, 2000])

        yield PollResult(
            poll_id=f"poll_{idx:04d}",
            pollster=rng.choice(POLLSTERS),
            date=poll_date,
            topic=topic,
            sample_size=sample_size,
            breakdown=breakdown,
            source="synthetic",
        )
