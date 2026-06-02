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
    # 인물·조직
    "Person": {"id": "assembly_id", "label": "name", "subtitle": "party_id"},
    "Party": {"id": "party_id", "label": "name", "subtitle": "party_id"},
    "Staff": {"id": "staff_id", "label": "role", "subtitle": "person_id"},
    "Committee": {"id": "committee_id", "label": "name", "subtitle": "type"},
    "District": {"id": "code", "label": "sgg", "subtitle": "sido"},
    "Term": {"id": "number", "label": "number", "subtitle": "start_date"},
    # 입법
    "Bill": {"id": "bill_id", "label": "title", "subtitle": "status"},
    "Law": {"id": "law_id", "label": "name", "subtitle": "last_revised"},
    "Amendment": {"id": "bill_id", "label": "diff_summary", "subtitle": "original_law_id"},
    "Vote": {"id": "vote_id", "label": "result", "subtitle": "date"},
    "Statement": {"id": "statement_id", "label": "content", "subtitle": "person_id"},
    "Session": {"id": "session_id", "label": "session_id", "subtitle": "type"},
    "Budget": {"id": "ministry", "label": "ministry", "subtitle": "amount_krw"},
    # 주제·외부
    "Topic": {"id": "topic_id", "label": "name", "subtitle": "category"},
    "Policy": {"id": "policy_id", "label": "name", "subtitle": "policy_id"},
    "Agency": {"id": "agency_id", "label": "name", "subtitle": "type"},
    "ElectionResult": {"id": "election_id", "label": "person_id", "subtitle": "district_id"},
    "PollResult": {"id": "poll_id", "label": "topic", "subtitle": "pollster"},
    "SocialSignal": {"id": "signal_id", "label": "source_url", "subtitle": "source_type"},
    # 미디어
    "Article": {"id": "article_id", "label": "title", "subtitle": "author"},
    "Tag": {"id": "name", "label": "name", "subtitle": "category"},
    # 독자 측
    "Reader": {"id": "reader_id", "label": "tier", "subtitle": "region"},
    "ReaderProfile": {"id": "reader_id", "label": "device_class", "subtitle": "reading_minutes_avg_7d"},
    "SubscriptionTier": {"id": "tier_id", "label": "name", "subtitle": "price_krw_monthly"},
    "ReadingEvent": {"id": "event_id", "label": "article_id", "subtitle": "duration_sec"},
    "Bookmark": {"id": "bookmark_id", "label": "target_id", "subtitle": "target_type"},
    # 광고
    "Advertisement": {"id": "ad_id", "label": "advertiser", "subtitle": "category"},
    "AdInventory": {"id": "inventory_id", "label": "ad_id", "subtitle": "budget_krw"},
    "AdImpression": {"id": "impression_id", "label": "ad_id", "subtitle": "article_id"},
    "AdMatchDecision": {"id": "decision_id", "label": "mode", "subtitle": "reason_text"},
    # 분석 메타
    "Cluster": {"id": "cluster_id", "label": "label", "subtitle": "cluster_id"},
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


# ─── Phase 5 Track 5-8: 16 placeholder dispatchers ──────────────────────


def _list_staff(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_staff
    return [n.model_dump(mode="json") for n in generate_staff(count=max_rows or 20)]


def _list_districts(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_districts
    return [n.model_dump(mode="json") for n in generate_districts(count=max_rows or 17)]


def _list_terms(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_terms
    return [n.model_dump(mode="json") for n in generate_terms(count=max_rows or 3)]


def _list_laws(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_laws
    return [n.model_dump(mode="json") for n in generate_laws(count=max_rows or 12)]


def _list_amendments(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_amendments
    return [n.model_dump(mode="json") for n in generate_amendments(count=max_rows or 6)]


def _list_budgets(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_budgets
    return [n.model_dump(mode="json") for n in generate_budgets(count=max_rows or 10)]


def _list_policies(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_policies
    return [n.model_dump(mode="json") for n in generate_policies(count=max_rows or 6)]


def _list_election_results(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_election_results
    return [n.model_dump(mode="json") for n in generate_election_results(count=max_rows or 10)]


def _list_tags(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_tags
    return [n.model_dump(mode="json") for n in generate_tags(count=max_rows or 18)]


def _list_reader_profiles(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_reader_profiles
    return [n.model_dump(mode="json") for n in generate_reader_profiles(count=max_rows or 10)]


def _list_subscription_tiers(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_subscription_tiers
    return [n.model_dump(mode="json") for n in generate_subscription_tiers(count=max_rows or 3)]


def _list_reading_events(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_reading_events
    return [n.model_dump(mode="json") for n in generate_reading_events(count=max_rows or 15)]


def _list_bookmarks(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_bookmarks
    return [n.model_dump(mode="json") for n in generate_bookmarks(count=max_rows or 10)]


def _list_ad_impressions(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_ad_impressions
    return [n.model_dump(mode="json") for n in generate_ad_impressions(count=max_rows or 15)]


def _list_ad_match_decisions(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_ad_match_decisions
    return [n.model_dump(mode="json") for n in generate_ad_match_decisions(count=max_rows or 6)]


def _list_clusters(max_rows: int) -> list[dict]:
    from data.synthetic.placeholders import generate_clusters
    return [n.model_dump(mode="json") for n in generate_clusters()][:max_rows or 5]


# 구현 안 된 클래스 → 빈 리스트 (현재 0개 - 31/31 모두 dispatcher 등록).
def _list_empty(max_rows: int) -> list[dict]:
    return []


DISPATCHERS: dict[str, Callable[[int], list[dict]]] = {
    # 인물·조직 (6)
    "Person": _list_persons,
    "Party": _list_parties,
    "Staff": _list_staff,
    "Committee": _list_committees,
    "District": _list_districts,
    "Term": _list_terms,
    # 입법 (7)
    "Bill": _list_bills,
    "Law": _list_laws,
    "Amendment": _list_amendments,
    "Vote": _list_votes,
    "Statement": _list_statements,
    "Session": _list_sessions,
    "Budget": _list_budgets,
    # 주제·외부 (6)
    "Topic": _list_topics,
    "Policy": _list_policies,
    "Agency": _list_agencies,
    "ElectionResult": _list_election_results,
    "PollResult": _list_polls,
    "SocialSignal": _list_social_signals,
    # 미디어 (2)
    "Article": _list_articles,
    "Tag": _list_tags,
    # 독자 측 (5)
    "Reader": _list_readers,
    "ReaderProfile": _list_reader_profiles,
    "SubscriptionTier": _list_subscription_tiers,
    "ReadingEvent": _list_reading_events,
    "Bookmark": _list_bookmarks,
    # 광고 (4)
    "Advertisement": _list_ads,
    "AdInventory": _list_ad_inventories,
    "AdImpression": _list_ad_impressions,
    "AdMatchDecision": _list_ad_match_decisions,
    # 분석 메타 (1)
    "Cluster": _list_clusters,
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
