"""Amazon OpenSearch Serverless wrapper - BM25 (Nori) + Cohere KNN + RRF.

`hybrid_search(query, top_k, source_filter)` - 단일 진입점.

`DEMO_PUBLIC_MODE=true`에서는 결정적 mock 응답으로 fallback.
실 환경: SigV4 signed POST to `/<index>/_search` with hybrid query.

References:
- CLAUDE.md "Tech Stack" — Nori + Cohere KNN, RRF fusion
- spec §3.1 시나리오 A
- ADR-0001 (gcc opensearch wrapper 패턴 차용)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["hybrid_search", "SearchHit", "SearchError"]


class SearchError(RuntimeError):
    """OpenSearch 호출 실패."""


@dataclass(frozen=True)
class SearchHit:
    """검색 결과 한 row.

    `source` 필드로 DataSourceBadge 호환 (real/synthetic/external).
    """
    id: str
    score: float
    source: str             # real | synthetic | external
    title: str
    snippet: str
    node_type: str = ""     # Bill | Person | Article | Statement | ...
    metadata: dict = field(default_factory=dict)


def hybrid_search(
    query: str,
    top_k: int = 10,
    source_filter: Optional[list[str]] = None,
    rrf_k: int = 60,
) -> list[SearchHit]:
    """BM25 (Nori) + KNN (Cohere embed-v4) 하이브리드 검색 + RRF 융합.

    Args:
        query: 한국어 자연어 쿼리.
        top_k: 반환할 결과 수.
        source_filter: 페르소나·시나리오 cohort 적용 결과
            (`cohort.select(persona_id, scenario_code)` 권장).
            None 또는 ['*'] = no filter.
        rrf_k: RRF 가중치 상수 (gcc 패턴 60 권장).

    Returns:
        list of SearchHit. 점수 내림차순.

    Raises:
        SearchError: 네트워크/응답 파싱 실패.
    """
    if _demo_mode():
        return _mock_search(query, top_k, source_filter)
    return _real_search(query, top_k, source_filter, rrf_k)


# ─── Production 경로 ─────────────────────────────────────────────────────────

def _real_search(
    query: str,
    top_k: int,
    source_filter: Optional[list[str]],
    rrf_k: int,
) -> list[SearchHit]:
    """SigV4 signed POST + BM25/KNN hybrid + RRF."""
    import requests  # lazy
    from aws_requests_auth.aws_auth import AWSRequestsAuth  # lazy
    from api.aws_clients import session as boto_session  # lazy
    from api.services.embedding import embed  # lazy

    endpoint = os.environ.get("OPENSEARCH_ENDPOINT", "")
    index = os.environ.get("OPENSEARCH_INDEX", "ontology-assembly-dev-kb-index")
    region = os.environ.get("AWS_REGION", "ap-northeast-2")

    if not endpoint:
        raise SearchError("OPENSEARCH_ENDPOINT not configured")

    # 임베딩 생성 (Cohere embed-v4)
    query_vector = embed(query)

    # 후보 풀은 top_k * 3 (RRF 후 정제하기 위해 풍부히)
    candidate_size = top_k * 3

    # BM25 + KNN hybrid (OpenSearch hybrid query plugin)
    inner_query: dict = {
        "hybrid": {
            "queries": [
                {"match": {"content": {"query": query, "analyzer": "nori"}}},
                {"knn": {"embedding": {"vector": query_vector, "k": candidate_size}}},
            ]
        }
    }

    # source_filter 적용 — cohort.select() 결과
    if source_filter and "*" not in source_filter:
        inner_query = {
            "bool": {
                "must": [inner_query],
                "filter": [{"terms": {"source": source_filter}}],
            }
        }

    body = {"size": candidate_size, "query": inner_query}

    session = boto_session()
    credentials = session.get_credentials()
    auth = AWSRequestsAuth(
        aws_access_key=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_token=credentials.token,
        aws_host=endpoint.replace("https://", "").replace("http://", ""),
        aws_region=region,
        aws_service="aoss",
    )

    url = f"{endpoint}/{index}/_search"
    try:
        response = requests.post(url, json=body, auth=auth, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        raise SearchError(f"OpenSearch HTTP error: {e}") from e

    return _parse_hits(payload, top_k)


def _parse_hits(payload: dict, top_k: int) -> list[SearchHit]:
    """OpenSearch response → SearchHit list."""
    hits: list[SearchHit] = []
    for h in payload.get("hits", {}).get("hits", [])[:top_k]:
        src = h.get("_source", {})
        hits.append(SearchHit(
            id=h.get("_id", ""),
            score=h.get("_score", 0.0),
            source=src.get("source", "real"),
            title=src.get("title", ""),
            snippet=(src.get("content") or "")[:200],
            node_type=src.get("node_type", ""),
            metadata=src,
        ))
    return hits


# ─── Demo mode mock ─────────────────────────────────────────────────────────

def _mock_search(
    query: str,
    top_k: int,
    source_filter: Optional[list[str]],
) -> list[SearchHit]:
    """결정적 mock 결과. 질의-시드 다양화 + 실 id (subgraph 매칭) + 다양한 node_type.

    - Person/Bill hit은 query 해시로 시드된 window에서 선택 → 질의마다 다른 결과
      (이전: 항상 composite_score top-3 고정이라 같은 3명만 노출되던 issue).
    - hit id는 member_directory(실 assembly_id)·objects_catalog(실 bill_id)에서 가져와
      search.py:_build_subgraph가 매칭에 성공 → 풍부한 1-hop subgraph 생성
      (이전: 합성 id라 매칭 실패 → singleton subgraph만 나오던 issue).
    """
    import hashlib
    from api.services import member_directory as md
    from api.services import objects_catalog

    seed = int(hashlib.sha1((query or "_").encode("utf-8")).hexdigest()[:8], 16)

    # ─── Person hits: 질의-시드 window (실 assembly_id, composite_score 풀에서 회전) ───
    pool = md.list_top_by_metric("composite_score", top_n=30) or []
    person_hits: list[SearchHit] = []
    if pool:
        off = seed % len(pool)
        window = (pool[off:] + pool[:off])[:10]  # 질의-시드 회전 window (wrap-around)
        # 정당 다양성 우선 선택 (ADR-0004: 한 정당 쏠림 방지 — 점수순 window가 동일
        # 정당에 안착하는 것을 막고 ≥2 정당이 노출되도록 보강).
        picked: list = []
        seen_parties: set[str] = set()
        for m in window:  # pass 1: 새 정당 우선
            if len(picked) >= 3:
                break
            if m.party not in seen_parties:
                picked.append(m)
                seen_parties.add(m.party)
        picked_ids = {m.assembly_id for m in picked}
        for m in window:  # pass 2: 남은 슬롯 채우기
            if len(picked) >= 3:
                break
            if m.assembly_id not in picked_ids:
                picked.append(m)
                picked_ids.add(m.assembly_id)
        for i, m in enumerate(picked):
            person_hits.append(SearchHit(
                id=m.assembly_id,
                score=0.90 - i * 0.02,
                source="real",
                title=f"{m.name} 의원 ({m.party})",
                snippet=(
                    f"{m.district} · {m.reelection} · {m.committee or '미배정 위원회'} · "
                    f"22대 활동 점수 {m.analytics.composite_score:.1f}/100 "
                    f"(발의 {m.analytics.bills_proposed}건, 출처: 국회 OpenAPI)"
                ),
                node_type="Person",
                metadata={
                    "term": m.term,
                    "district_id": m.district,
                    "party": m.party,
                    "profile_image_url": m.profile_image_url,
                    "composite_score": m.analytics.composite_score,
                },
            ))

    # ─── Bill hits: objects_catalog 실 Bill (실 bill_id → subgraph 매칭/풍부화) ───
    try:
        bills, _ = objects_catalog.list_instances("Bill", limit=50)
    except Exception:
        bills = []
    bill_hits: list[SearchHit] = []
    if bills:
        boff = seed % max(1, len(bills) - 1)
        for i, b in enumerate(bills[boff:boff + 2]):
            bid = str(b.get("bill_id") or "")
            if not bid:
                continue
            cat = str(b.get("category") or "")
            bill_hits.append(SearchHit(
                id=bid,
                score=0.95 - i * 0.03,
                source=str(b.get("source") or "real"),
                title=str(b.get("title") or b.get("bill_no") or "의안"),
                snippet=f"{cat + ' · ' if cat else ''}22대 의안 (출처: 국회 OpenAPI)",
                node_type="Bill",
                metadata={"category": cat, "proposed_date": str(b.get("proposed_date") or "")},
            ))

    # ─── 기타 node_type 다양성 (top hit 아님 — 합성 id 유지) ───
    other_hits = [
        SearchHit(
            id="ART001", score=0.83, source="synthetic",
            title="AI 입법 동향 분석 - 1분기 리뷰",
            snippet="22대 국회 첫 분기 AI 관련 법안 51건 발의 (출처: 합성)",
            node_type="Article", metadata={"published_at": "2026-05-10"},
        ),
        SearchHit(
            id="SS001", score=0.80, source="external",
            title="AI 입법 화제 - 네이버 뉴스",
            snippet="AI 산업 진흥법 관련 사회적 관심 증가 (출처: 네이버 뉴스 RSS)",
            node_type="SocialSignal", metadata={"source_type": "news"},
        ),
        SearchHit(
            id="ST001", score=0.78, source="real",
            title="AI 관련 본회의 발언",
            snippet="기술 혁신과 규제 균형에 대한 논의 (출처: 국회 회의록)",
            node_type="Statement", metadata={"date": "2026-04-25"},
        ),
    ]

    # 점수순 정렬 (Bill 0.95~ > Person 0.90~ > 기타) → top hit은 실 id Bill
    all_hits = sorted(bill_hits + person_hits + other_hits, key=lambda h: -h.score)
    if source_filter and "*" not in source_filter:
        all_hits = [h for h in all_hits if h.source in source_filter]
    return all_hits[:top_k]


def _demo_mode() -> bool:
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"
