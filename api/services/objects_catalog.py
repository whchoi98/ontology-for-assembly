"""31 클래스 객체 탐색기 카탈로그 (Phase 5 Track 5-6).

Object Explorer 라우터가 사용하는 dispatcher:
- 각 클래스 타입 → 인스턴스를 가져오는 callable
- DEMO_PUBLIC_MODE에서는 mock fixture, production은 Neptune 쿼리

구현 안 된 클래스(District, Term, ReaderProfile 등)는 빈 리스트 반환 -
explorer UI에서 "0 instances" 표시.
"""
from __future__ import annotations

from typing import Callable, Iterable

from data.schemas import GraphNode

__all__ = ["CLASS_GROUPS", "list_instances", "get_class_meta"]


# 클래스 그룹화 (spec §4.1).
CLASS_GROUPS: dict[str, list[str]] = {
    "인물·조직": ["Person", "Party", "Staff", "Committee", "District", "Term"],
    "입법": ["Bill", "Law", "Amendment", "Vote", "Statement", "Session", "Budget"],
    "주제·외부": ["Topic", "Policy", "Agency", "ElectionResult", "PollResult", "SocialSignal"],
    "미디어": ["Article", "Tag"],
    "독자 측": ["Reader", "ReaderProfile", "SubscriptionTier", "ReadingEvent", "Bookmark"],
    "광고": ["Advertisement", "AdInventory", "AdImpression", "AdMatchDecision"],
    "분석 메타": ["Cluster"],
}


# 클래스별 디스플레이용 필드 (instance list 표시).
CLASS_DISPLAY_FIELDS: dict[str, dict[str, str]] = {
    "Person": {"id": "assembly_id", "label": "name", "subtitle": "party_id"},
    "Party": {"id": "party_id", "label": "name", "subtitle": "party_id"},
    "Bill": {"id": "bill_id", "label": "title", "subtitle": "status"},
    "Vote": {"id": "vote_id", "label": "result", "subtitle": "date"},
    "Committee": {"id": "committee_id", "label": "name", "subtitle": "type"},
    "Session": {"id": "session_id", "label": "session_id", "subtitle": "type"},
    "Statement": {"id": "statement_id", "label": "content", "subtitle": "person_id"},
    "Agency": {"id": "agency_id", "label": "name", "subtitle": "type"},
    "Topic": {"id": "topic_id", "label": "name", "subtitle": "category"},
    "Article": {"id": "article_id", "label": "title", "subtitle": "author"},
    "Reader": {"id": "reader_id", "label": "tier", "subtitle": "region"},
    "Advertisement": {"id": "ad_id", "label": "advertiser", "subtitle": "category"},
    "AdInventory": {"id": "inventory_id", "label": "ad_id", "subtitle": "budget_krw"},
    "PollResult": {"id": "poll_id", "label": "topic", "subtitle": "pollster"},
    "SocialSignal": {"id": "signal_id", "label": "source_url", "subtitle": "source_type"},
}


# ─── Dispatchers ────────────────────────────────────────────────────────────

def _list_persons(max_rows: int) -> list[dict]:
    from data.real.member import fetch_members
    return [p.model_dump(mode="json") for p in fetch_members(max_rows=max_rows)]


def _list_parties(max_rows: int) -> list[dict]:
    from data.real.party import fetch_parties
    return [p.model_dump(mode="json") for p in fetch_parties(max_rows=max_rows)]


def _list_bills(max_rows: int) -> list[dict]:
    from data.real.bill import fetch_bills
    return [b.model_dump(mode="json") for b in fetch_bills(max_rows=max_rows)]


def _list_votes(max_rows: int) -> list[dict]:
    from data.real.vote import fetch_votes
    return [v.model_dump(mode="json") for v in fetch_votes(max_rows=max_rows)]


def _list_committees(max_rows: int) -> list[dict]:
    from data.real.committee import fetch_committees
    return [c.model_dump(mode="json") for c in fetch_committees(max_rows=max_rows)]


def _list_sessions(max_rows: int) -> list[dict]:
    from data.real.session import fetch_sessions_and_statements
    from data.schemas import Session
    items = list(fetch_sessions_and_statements(max_sessions=max_rows))
    return [i.model_dump(mode="json") for i in items if isinstance(i, Session)]


def _list_statements(max_rows: int) -> list[dict]:
    from data.real.session import fetch_sessions_and_statements
    from data.schemas import Statement
    items = list(fetch_sessions_and_statements(max_sessions=max_rows or 10))
    return [i.model_dump(mode="json") for i in items if isinstance(i, Statement)][:max_rows or 50]


def _list_agencies(max_rows: int) -> list[dict]:
    from data.real.agency import fetch_agencies
    return [a.model_dump(mode="json") for a in fetch_agencies(max_rows=max_rows)]


def _list_topics(max_rows: int) -> list[dict]:
    from data.synthetic.topics import to_graph_nodes
    return [t.model_dump(mode="json") for t in to_graph_nodes()][:max_rows]


def _list_articles(max_rows: int) -> list[dict]:
    from data.synthetic.article import generate_articles
    return [a.model_dump(mode="json") for a in generate_articles(count=max_rows or 10)]


def _list_readers(max_rows: int) -> list[dict]:
    from data.synthetic.reader import generate_readers
    return [r.model_dump(mode="json") for r in generate_readers(count=max_rows or 10)]


def _list_ads(max_rows: int) -> list[dict]:
    from data.synthetic.advertisement import generate_advertisements
    return [a.model_dump(mode="json") for a in generate_advertisements(count=max_rows or 10)]


def _list_ad_inventories(max_rows: int) -> list[dict]:
    from data.synthetic.advertisement import generate_ads_with_inventory
    _ads, invs = generate_ads_with_inventory(count=max_rows or 10)
    return [i.model_dump(mode="json") for i in invs]


def _list_social_signals(max_rows: int) -> list[dict]:
    from data.external.naver_news import fetch_news
    return [s.model_dump(mode="json") for s in fetch_news("국회 입법", display=min(max_rows or 10, 100))]


def _list_polls(max_rows: int) -> list[dict]:
    from data.external.poll_result import generate_polls
    return [p.model_dump(mode="json") for p in generate_polls(count=max_rows or 10)]


# 구현 안 된 클래스 → 빈 리스트.
def _list_empty(max_rows: int) -> list[dict]:
    return []


DISPATCHERS: dict[str, Callable[[int], list[dict]]] = {
    "Person": _list_persons,
    "Party": _list_parties,
    "Bill": _list_bills,
    "Vote": _list_votes,
    "Committee": _list_committees,
    "Session": _list_sessions,
    "Statement": _list_statements,
    "Agency": _list_agencies,
    "Topic": _list_topics,
    "Article": _list_articles,
    "Reader": _list_readers,
    "Advertisement": _list_ads,
    "AdInventory": _list_ad_inventories,
    "SocialSignal": _list_social_signals,
    "PollResult": _list_polls,
}


# ─── 공개 API ───────────────────────────────────────────────────────────────

def list_instances(class_name: str, limit: int = 10, offset: int = 0) -> tuple[list[dict], int]:
    """클래스 타입의 인스턴스 페이징.

    Returns: (page items, total_count_estimate)
    """
    dispatcher = DISPATCHERS.get(class_name, _list_empty)
    all_items = dispatcher(max_rows=limit + offset)
    page = all_items[offset: offset + limit]
    return page, len(all_items)


def get_class_meta(class_name: str) -> dict:
    """클래스 메타데이터 - schemas의 Pydantic model_fields 추출."""
    from data.schemas import NODE_CLASSES
    cls = NODE_CLASSES.get(class_name)
    if cls is None:
        return {"name": class_name, "fields": [], "implemented": False}
    fields = []
    for fname, finfo in cls.model_fields.items():
        ftype = str(finfo.annotation)
        # type alias 정리
        ftype = ftype.replace("typing.", "").replace("<class '", "").replace("'>", "")
        fields.append({
            "name": fname,
            "type": ftype,
            "required": finfo.is_required(),
        })
    return {
        "name": class_name,
        "fields": fields,
        "implemented": class_name in DISPATCHERS,
        "group": _find_group(class_name),
        "display": CLASS_DISPLAY_FIELDS.get(class_name, {}),
    }


def _find_group(class_name: str) -> str:
    for group, members in CLASS_GROUPS.items():
        if class_name in members:
            return group
    return "기타"
