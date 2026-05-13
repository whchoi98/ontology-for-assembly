"""합성 Reader generator - B2C 시나리오 (D 페르소나 매칭, F 룩어라이크, L 광고)의 데이터 소스.

설계 원칙 (ADR-0003 + ADR-0004 Layer 4):
1. 익명성 절대 강제 - reader_id는 솔티드 SHA-256 해시만 (64자 lowercase hex).
2. region은 시도 단위만 (KOSTAT 17 시도). sgg 이상 정밀도 절대 금지.
3. PII 금지 - IP/UA/GPS/광고ID 필드 신설 금지. Pydantic extra="forbid"가 차단.
4. political_leaning 등 정치 성향 추론 필드 절대 생성 금지.
5. Tier 분포 anonymous 80% / free 15% / paid 5% - 현실적 B2C 미디어 비율.

References:
- spec §4.1 Group 5 (Reader 클래스)
- ADR-0003 (B2C 익명화)
- ADR-0004 Layer 4 (정치 성향 추론 금지)
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Iterator, Literal

from data.schemas import Reader, ReaderTier
from data.synthetic.topics import list_topic_ids

__all__ = ["generate_readers", "TIER_DISTRIBUTION", "SIDOS"]


# 17 시도 (KOSTAT 광역 단위만). sgg/dong 이상 정밀도 절대 추가 금지.
SIDOS: tuple[str, ...] = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)

# B2C 미디어 비즈니스의 현실적 tier 분포.
# (anonymous=무료 익명 / free=가입 무료 / paid=유료 구독).
TIER_DISTRIBUTION: dict[ReaderTier, float] = {
    "anonymous": 0.80,
    "free": 0.15,
    "paid": 0.05,
}


# ─── 솔티드 해시 ID ──────────────────────────────────────────────────────────

def _hash_reader_id(salt: str, idx: int) -> str:
    """솔티드 SHA-256 → 64자 lowercase hex.

    Schema의 HashedId 정규식 `^[a-f0-9]{64}$`를 통과해야 함.
    salt를 변경하면 모든 ID가 달라지므로 환경별 격리 가능.
    """
    raw = f"{salt}:reader:{idx}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ─── Tier 분포 추첨 ─────────────────────────────────────────────────────────

def _pick_tier(rng: random.Random) -> ReaderTier:
    """누적 확률 기반 tier 추첨."""
    r = rng.random()
    cum = 0.0
    for tier, pct in TIER_DISTRIBUTION.items():
        cum += pct
        if r <= cum:
            return tier
    return "anonymous"  # rounding 안전 fallback


# ─── Generator 본체 ─────────────────────────────────────────────────────────

def generate_readers(
    count: int = 50_000,
    seed: int = 20260513,
    salt: str = "ontology-assembly-poc",
    base_date: datetime | None = None,
) -> Iterator[Reader]:
    """합성 Reader generator - 50,000건 기본.

    Args:
        count: 생성 수.
        seed: RNG seed.
        salt: SHA-256 salt - 환경별 격리. Production은 별도 KMS 관리 비밀.
        base_date: since 기준일 (None이면 2026-05-13 UTC).

    Yields:
        Reader — 익명화 가드 통과한 Pydantic Reader 노드.

    Examples:
        >>> readers = list(generate_readers(count=100))
        >>> len(readers)
        100
        >>> all(len(r.reader_id) == 64 for r in readers)
        True
    """
    rng = random.Random(seed)
    base = base_date or datetime(2026, 5, 13, tzinfo=timezone.utc)
    topic_ids = list_topic_ids()

    for idx in range(count):
        tier = _pick_tier(rng)

        # 관심사 0-5개 (paid 구독자는 더 많은 관심사 보유 경향)
        if tier == "paid":
            n_interests = rng.randint(2, 5)
        elif tier == "free":
            n_interests = rng.randint(1, 4)
        else:
            n_interests = rng.randint(0, 3)

        interests = rng.sample(topic_ids, n_interests) if n_interests > 0 else []
        region = rng.choice(SIDOS)

        # since: 최근 1년 내 가입/첫 방문
        days_offset = rng.randint(0, 365)
        seconds_offset = rng.randint(0, 86400)
        since = base - timedelta(days=days_offset, seconds=seconds_offset)

        yield Reader(
            reader_id=_hash_reader_id(salt, idx),
            tier=tier,
            interests=interests,
            region=region,
            since=since,
            source="synthetic",
        )
