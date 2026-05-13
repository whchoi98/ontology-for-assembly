"""Amazon Neptune openCypher wrapper - 단일 진입점.

`open_cypher(query, *, parameters=None)` - **`parameters`는 키워드 전용**.
사용자 입력 f-string interpolation을 syntactically 금지 (Cypher injection 방어).

`DEMO_PUBLIC_MODE=true`에서는 mock 응답으로 fallback - 라우터를 미배포 환경에서도
개발 가능. 실 환경에서는 SigV4 signed POST.

References:
- CLAUDE.md "Conventions / Code" — Cypher 파라미터 키워드 강제
- .claude/skills/cypher-conventions.md
- ADR-0001 (gcc Neptune wrapper 패턴 차용)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

__all__ = ["open_cypher", "CypherResult", "CypherError"]


class CypherError(RuntimeError):
    """Neptune openCypher 호출 실패."""


@dataclass
class CypherResult:
    """openCypher 응답.

    `rows`는 항상 list of dict (key = Cypher RETURN 변수, value = 노드/관계/스칼라).
    `requestId`는 디버깅·트레이스용 (운영 콘솔 트레이스 panel에 노출).
    """
    rows: list[dict]
    request_id: Optional[str] = None

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx):
        return self.rows[idx]


def open_cypher(
    query: str,
    *,
    parameters: Optional[dict] = None,
) -> CypherResult:
    """Neptune openCypher 쿼리 실행.

    Args:
        query: Cypher 쿼리 문자열. `$name` 형식으로 파라미터 참조.
        parameters: **키워드 전용**. 모든 사용자 입력은 여기로.

    Returns:
        CypherResult — `.rows` list of dict, iterable.

    Raises:
        CypherError: HTTP 4xx/5xx 또는 응답 파싱 실패.

    Example:
        result = open_cypher(
            "MATCH (p:Person {assembly_id: $id})-[:PROPOSED]->(b:Bill) RETURN b",
            parameters={"id": person_id},
        )
        for row in result:
            print(row["b"]["title"])
    """
    if _demo_mode():
        return _mock_result(query, parameters or {})
    return _real_query(query, parameters or {})


# ─── Production 경로 ─────────────────────────────────────────────────────────

def _real_query(query: str, parameters: dict) -> CypherResult:
    """SigV4 signed POST to /openCypher."""
    import requests  # lazy
    from aws_requests_auth.aws_auth import AWSRequestsAuth  # lazy
    from api.aws_clients import session as boto_session  # lazy

    endpoint = os.environ.get("NEPTUNE_ENDPOINT", "")
    port = int(os.environ.get("NEPTUNE_PORT", "8182"))
    region = os.environ.get("AWS_REGION", "ap-northeast-2")

    if not endpoint:
        raise CypherError("NEPTUNE_ENDPOINT not configured")

    session = boto_session()
    credentials = session.get_credentials()
    auth = AWSRequestsAuth(
        aws_access_key=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_token=credentials.token,
        aws_host=endpoint,
        aws_region=region,
        aws_service="neptune-db",
    )

    url = f"https://{endpoint}:{port}/openCypher"
    body = {"query": query, "parameters": json.dumps(parameters)}

    try:
        response = requests.post(url, json=body, auth=auth, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        raise CypherError(f"Neptune HTTP error: {e}") from e
    except json.JSONDecodeError as e:
        raise CypherError(f"Neptune response parse error: {e}") from e

    return CypherResult(
        rows=payload.get("results", []),
        request_id=payload.get("requestId"),
    )


# ─── Demo mode mock ─────────────────────────────────────────────────────────

def _mock_result(query: str, parameters: dict) -> CypherResult:
    """Demo mode mock. 쿼리 substring 매칭으로 그럴듯한 응답.

    실 데이터 적재 전에 라우터·페이지 개발이 가능하도록.
    노드는 항상 source 태깅 포함 → DataSourceBadge 호환.
    """
    q = query.lower()

    # MATCH (b:Bill) — 의안
    if ":bill" in q or "match (b" in q:
        return CypherResult([
            {"b": {"bill_id": "B2206001", "title": "AI 산업 진흥 및 활용 촉진법안",
                   "proposed_date": "2026-04-15", "status": "in_committee",
                   "category": "산업", "source": "real"}},
            {"b": {"bill_id": "B2206002", "title": "개인정보 보호법 일부개정법률안",
                   "proposed_date": "2026-04-20", "status": "in_plenary",
                   "category": "법무", "source": "real"}},
            {"b": {"bill_id": "B2206003", "title": "디지털 콘텐츠 진흥법",
                   "proposed_date": "2026-04-22", "status": "proposed",
                   "category": "문화", "source": "real"}},
        ])

    # MATCH (p:Person) — 의원
    if ":person" in q or "match (p" in q:
        return CypherResult([
            {"p": {"assembly_id": "MONA001", "name": "○○○", "term": 22,
                   "district_id": "11110", "party_id": "P001", "source": "real"}},
            {"p": {"assembly_id": "MONA002", "name": "△△△", "term": 22,
                   "district_id": "11020", "party_id": "P002", "source": "real"}},
            {"p": {"assembly_id": "MONA003", "name": "□□□", "term": 22,
                   "district_id": "26110", "party_id": "P001", "source": "real"}},
        ])

    # MATCH (v:Vote) — 표결
    if ":vote" in q or "match (v" in q:
        return CypherResult([
            {"v": {"vote_id": "V001", "bill_id": "B2206001",
                   "date": "2026-04-30", "result": "passed",
                   "attendance_count": 287, "source": "real"}},
        ])

    # MATCH (a:Article) — 기사 (synthetic)
    if ":article" in q or "match (a" in q:
        return CypherResult([
            {"a": {"article_id": "ART001", "title": "AI 입법 동향 분석",
                   "published_at": "2026-05-10T09:00:00", "source": "synthetic"}},
        ])

    # COUNT 쿼리
    if "count" in q:
        return CypherResult([{"count": 42}])

    # 기본: 빈 결과
    return CypherResult([], request_id="mock-empty")


def _demo_mode() -> bool:
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"
