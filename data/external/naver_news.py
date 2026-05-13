"""네이버 뉴스 검색 어댑터 → SocialSignal.

API: https://openapi.naver.com/v1/search/news.json
인증: X-Naver-Client-Id / X-Naver-Client-Secret 헤더
Rate limit: 25,000 req/day

Demo mode (DEMO_PUBLIC_MODE=true): 결정적 mock fixture. 정당 균형 응답.

References:
- 네이버 검색 API https://developers.naver.com/docs/serviceapi/search/news/news.md
- spec §5 데이터 파이프라인
- data/schemas.py SocialSignal
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Iterator, Optional

from data.schemas import SocialSignal

__all__ = ["fetch_news", "NAVER_NEWS_URL", "NaverNewsError"]


NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


class NaverNewsError(RuntimeError):
    """네이버 뉴스 API 호출 실패."""


def _demo_mode() -> bool:
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"


def _strip_html(text: str) -> str:
    """네이버 응답 description은 <b></b> 등 HTML 포함."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _signal_id(url: str) -> str:
    """URL 해시로 결정적 ID 생성."""
    return f"naver_{hashlib.md5(url.encode('utf-8')).hexdigest()[:16]}"


def _parse_pub_date(value: str) -> datetime:
    """네이버 형식 'Sat, 10 May 2026 09:00:00 +0900' → datetime."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def fetch_news(
    query: str,
    *,
    display: int = 10,
    start: int = 1,
    sort: str = "date",  # "sim" 정확도순 | "date" 날짜순
) -> Iterator[SocialSignal]:
    """네이버 뉴스 검색 → SocialSignal generator.

    Args:
        query: 검색어 (한국어 가능).
        display: 한 번에 가져올 결과 수 (10~100).
        start: 페이징 시작 (1~1000).
        sort: 정렬.

    Yields:
        SocialSignal nodes (source="external", source_type="news").

    Raises:
        NaverNewsError: API key 미설정 또는 HTTP error.
    """
    if _demo_mode():
        yield from _demo_news(query, display)
        return

    client_id = os.environ.get("NAVER_NEWS_API_CLIENT_ID")
    client_secret = os.environ.get("NAVER_NEWS_API_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise NaverNewsError(
            "NAVER_NEWS_API_CLIENT_ID/CLIENT_SECRET 미설정. "
            "https://developers.naver.com 에서 발급. 테스트는 DEMO_PUBLIC_MODE=true."
        )

    import requests  # lazy
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": query, "display": display, "start": start, "sort": sort}

    try:
        response = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        raise NaverNewsError(f"naver news HTTP error: {e}") from e

    for item in payload.get("items", []):
        url = item.get("link", "")
        yield SocialSignal(
            signal_id=_signal_id(url),
            source_url=url,
            source_type="news",
            date=_parse_pub_date(item.get("pubDate", "")),
            sentiment=None,            # 실 API 미제공 - LLM 후처리
            topic_ids=[],              # LLM 후처리로 채움
            source="external",
        )


# ─── Demo mode mock fixture ──────────────────────────────────────────────────

# 균형 잡힌 mock 뉴스 - 검색어 무관 안정 fixture.
_MOCK_NEWS_ITEMS: tuple[dict, ...] = (
    {"link": "https://news.example.com/ai-bill-2026-04",
     "pubDate": "Wed, 15 Apr 2026 09:00:00 +0900",
     "title": "AI 산업 진흥법, 더불어민주당·국민의힘 공동발의"},
    {"link": "https://news.example.com/data-protection",
     "pubDate": "Fri, 22 Apr 2026 14:30:00 +0900",
     "title": "개인정보 보호법 개정안 본회의 통과"},
    {"link": "https://news.example.com/cosponsor-network",
     "pubDate": "Mon, 25 Apr 2026 11:00:00 +0900",
     "title": "AI 입법 공동발의 네트워크 분석"},
    {"link": "https://news.example.com/energy-policy",
     "pubDate": "Wed, 30 Apr 2026 16:15:00 +0900",
     "title": "재생에너지 보급 확대 특별법안 상정"},
    {"link": "https://news.example.com/digital-content",
     "pubDate": "Sat, 03 May 2026 10:45:00 +0900",
     "title": "디지털 콘텐츠 진흥법 - 위원회 회부"},
    {"link": "https://news.example.com/healthcare-data",
     "pubDate": "Mon, 05 May 2026 13:20:00 +0900",
     "title": "보건의료 데이터 활용 법안 - 양당 협력"},
    {"link": "https://news.example.com/youth-housing",
     "pubDate": "Wed, 08 May 2026 08:50:00 +0900",
     "title": "청년 주거지원 확대법 가결"},
    {"link": "https://news.example.com/cybersecurity",
     "pubDate": "Fri, 10 May 2026 17:00:00 +0900",
     "title": "사이버보안 강화법안 본회의 상정"},
    {"link": "https://news.example.com/local-balance",
     "pubDate": "Sun, 12 May 2026 09:30:00 +0900",
     "title": "지방자치 균형발전 특별법안 심사"},
    {"link": "https://news.example.com/data-industry",
     "pubDate": "Mon, 13 May 2026 15:00:00 +0900",
     "title": "데이터 산업 진흥법 개정안 가결"},
)


def _demo_news(query: str, display: int) -> Iterator[SocialSignal]:
    """결정적 mock - query는 무시 (안정 fixture). 정치 균형 콘텐츠."""
    for item in _MOCK_NEWS_ITEMS[:display]:
        url = item["link"]
        yield SocialSignal(
            signal_id=_signal_id(url),
            source_url=url,
            source_type="news",
            date=_parse_pub_date(item["pubDate"]),
            sentiment=None,
            topic_ids=[],
            source="external",
        )
