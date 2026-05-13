"""api.services.neptune openCypher wrapper 검증.

테스트 범위:
- parameters keyword-only 강제 (Cypher injection 가드)
- DEMO_PUBLIC_MODE에서 mock 응답
- mock 결과의 source 태깅 (DataSourceBadge 호환)
- CypherResult iterable + len + index 접근
- 쿼리 패턴별 mock 분기 (Bill/Person/Vote/Article/COUNT)
"""
from __future__ import annotations
import pytest

from api.services import neptune


# ─── parameters keyword-only 강제 ───────────────────────────────────────────

def test_open_cypher_requires_keyword_parameters():
    """parameters는 positional argument로 전달 시 TypeError.

    이게 사용자 입력 f-string interpolation을 syntactically 차단하는 핵심 가드.
    """
    with pytest.raises(TypeError):
        neptune.open_cypher("MATCH (p:Person) RETURN p", {"id": "MONA001"})  # type: ignore[misc]


def test_open_cypher_accepts_keyword_parameters():
    """parameters를 키워드로 전달은 정상."""
    result = neptune.open_cypher(
        "MATCH (p:Person {assembly_id: $id}) RETURN p",
        parameters={"id": "MONA001"},
    )
    assert isinstance(result, neptune.CypherResult)


def test_open_cypher_no_parameters_allowed():
    """parameters 미지정 (None)도 정상."""
    result = neptune.open_cypher("MATCH (p:Person) RETURN p")
    assert isinstance(result, neptune.CypherResult)


# ─── CypherResult 동작 ──────────────────────────────────────────────────────

def test_cypher_result_iterable():
    """CypherResult는 iterable."""
    result = neptune.open_cypher("MATCH (p:Person) RETURN p")
    rows = list(result)
    assert len(rows) >= 1


def test_cypher_result_len():
    """len(CypherResult)."""
    result = neptune.open_cypher("MATCH (p:Person) RETURN p")
    assert len(result) >= 1


def test_cypher_result_index():
    """CypherResult[0]."""
    result = neptune.open_cypher("MATCH (p:Person) RETURN p")
    first = result[0]
    assert isinstance(first, dict)


# ─── Demo mode mock 분기 ────────────────────────────────────────────────────

def test_mock_bill_query_returns_bills():
    result = neptune.open_cypher("MATCH (b:Bill) RETURN b")
    assert len(result) >= 1
    # 결과의 일부에 'b' key (RETURN 변수)
    assert all("b" in row for row in result)
    # 의안 속성 확인
    first_bill = result[0]["b"]
    assert "bill_id" in first_bill
    assert "title" in first_bill
    assert "status" in first_bill


def test_mock_person_query_returns_persons():
    result = neptune.open_cypher("MATCH (p:Person) RETURN p")
    assert len(result) >= 1
    first_person = result[0]["p"]
    assert "assembly_id" in first_person
    assert "name" in first_person
    assert first_person["term"] == 22


def test_mock_vote_query_returns_votes():
    result = neptune.open_cypher("MATCH (v:Vote) RETURN v")
    assert len(result) >= 1
    assert "vote_id" in result[0]["v"]


def test_mock_article_query_returns_articles():
    result = neptune.open_cypher("MATCH (a:Article) RETURN a")
    assert len(result) >= 1
    assert "article_id" in result[0]["a"]


def test_mock_count_query_returns_scalar():
    result = neptune.open_cypher("MATCH (n) RETURN count(n) AS count")
    assert len(result) == 1
    assert "count" in result[0]


def test_mock_unknown_pattern_returns_empty():
    """매칭되지 않는 쿼리는 빈 결과 반환."""
    result = neptune.open_cypher("MERGE (x:UnknownType {id: $id})", parameters={"id": "X"})
    assert len(result) == 0


# ─── source 태깅 (DataSourceBadge 호환) ─────────────────────────────────────

def test_mock_bills_have_source_tag():
    """Bill mock에는 source 필드 존재 (real 등)."""
    result = neptune.open_cypher("MATCH (b:Bill) RETURN b")
    for row in result:
        assert "source" in row["b"]
        assert row["b"]["source"] in ("real", "synthetic", "external")


def test_mock_persons_have_source_tag():
    result = neptune.open_cypher("MATCH (p:Person) RETURN p")
    for row in result:
        assert "source" in row["p"]


def test_mock_articles_are_synthetic():
    """Article은 합성 데이터."""
    result = neptune.open_cypher("MATCH (a:Article) RETURN a")
    for row in result:
        assert row["a"]["source"] == "synthetic"


# ─── CypherError ────────────────────────────────────────────────────────────

def test_cypher_error_is_runtime_error():
    """CypherError는 RuntimeError 서브클래스."""
    assert issubclass(neptune.CypherError, RuntimeError)
