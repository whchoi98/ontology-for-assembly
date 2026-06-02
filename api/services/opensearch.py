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
    """결정적 mock 결과. 균형 잡힌 정당 분포 + 다양한 node_type.

    Person hit은 member_directory의 실 22대 의원 (composite_score top 3) 사용.
    """
    # 실 의원 top 3 - 양당 균형 분포 (정치 중립성: 점수순)
    from api.services import member_directory as md
    top_members = md.list_top_by_metric("composite_score", top_n=3)
    person_hits: list[SearchHit] = []
    for i, m in enumerate(top_members):
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

    # 균형: 정당 언급 없거나 양쪽 균형 (정치 중립성 가드 통과)
    base_hits = [
        SearchHit(
            id="B2206001", score=0.95, source="real",
            title="AI 산업 진흥 및 활용 촉진법안",
            snippet="인공지능 산업의 진흥과 활용 촉진을 위한 종합 대책 (출처: 국회 OpenAPI)",
            node_type="Bill",
            metadata={"category": "산업", "proposed_date": "2026-04-15"},
        ),
        SearchHit(
            id="B2206002", score=0.92, source="real",
            title="개인정보 보호법 일부개정법률안",
            snippet="데이터 활용 확대와 개인정보 보호의 균형 (출처: 국회 OpenAPI)",
            node_type="Bill",
            metadata={"category": "법무", "proposed_date": "2026-04-20"},
        ),
        # placeholder Person hit 제거 - 실 의원 person_hits로 교체
        SearchHit(
            id="ART001", score=0.85, source="synthetic",
            title="AI 입법 동향 분석 - 1분기 리뷰",
            snippet="22대 국회 첫 분기 AI 관련 법안 51건 발의 (출처: 합성)",
            node_type="Article",
            metadata={"published_at": "2026-05-10"},
        ),
        SearchHit(
            id="SS001", score=0.80, source="external",
            title="AI 입법 화제 - 네이버 뉴스",
            snippet="AI 산업 진흥법 관련 사회적 관심 증가 (출처: 네이버 뉴스 RSS)",
            node_type="SocialSignal",
            metadata={"source_type": "news"},
        ),
        SearchHit(
            id="ST001", score=0.78, source="real",
            title="AI 관련 본회의 발언",
            snippet="기술 혁신과 규제 균형에 대한 논의 (출처: 국회 회의록)",
            node_type="Statement",
            metadata={"date": "2026-04-25"},
        ),
    ]

    # 실 의원 hit를 적절한 위치에 삽입 (점수순 자연 정렬)
    all_hits = sorted(base_hits + person_hits, key=lambda h: -h.score)

    # source_filter 적용
    if source_filter and "*" not in source_filter:
        all_hits = [h for h in all_hits if h.source in source_filter]

    return all_hits[:top_k]


def _demo_mode() -> bool:
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"
