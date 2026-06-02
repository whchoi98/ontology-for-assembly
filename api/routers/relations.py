"""시나리오 O — 인물 관계 분석 (real Neptune query).

두 의원 간 *공동발의·표결 일치율·공유 의안·위원회 cohort* 분석.

Endpoint:
- GET /api/relations/{a}/{b} — 두 의원 cross-tab 메트릭 + narrative
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.services import neptune as nep

router = APIRouter(prefix="/api/relations", tags=["relations"])


class MemberInfo(BaseModel):
    assembly_id: str
    name: str
    party: str
    district: str
    profile_image_url: str = ""


class RelationMetrics(BaseModel):
    co_propose_count: int       # CO_PROPOSED_WITH count
    shared_bills_count: int     # 공동 발의 의안 수
    vote_agreement_pct: int     # 표결 일치율 (0-100)
    common_votes: int           # 공통 표결 의안 수
    same_committee: bool
    cross_party: bool


class RelationResult(BaseModel):
    member_a: MemberInfo
    member_b: MemberInfo
    metrics: RelationMetrics
    cross_party_rating: str     # "strong" | "moderate" | "weak"
    narrative: str
    shared_topic: str           # 공유 토픽 (의안 카테고리)
    shared_bills: list[str]     # 공동 발의 의안 title (top 5)
    source: str = "real"


def _fetch_member(assembly_id: str) -> Optional[dict]:
    """Person 노드 메타 fetch (Neptune)."""
    res = nep.open_cypher(
        "MATCH (p:Person {assembly_id: $pid}) "
        "RETURN p.name AS name, p.party_id AS party, p.district_id AS district "
        "LIMIT 1",
        parameters={"pid": assembly_id},
    )
    rows = res.rows if hasattr(res, "rows") else res.get("results", [])
    if not rows:
        return None
    r = rows[0]
    photo = f"https://www.assembly.go.kr/static/portal/img/openassm/{assembly_id}.jpg"
    return {
        "assembly_id": assembly_id,
        "name": r.get("name") or assembly_id,
        "party": r.get("party") or "—",
        "district": r.get("district") or "—",
        "profile_image_url": photo,
    }


@router.get("/{a}/{b}", response_model=RelationResult)
def get_relation(
    a: str,
    b: str,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> RelationResult:
    """두 의원 간 관계 분석 — real Neptune query.

    Metrics:
    - co_propose_count: CO_PROPOSED_WITH 엣지 count
    - shared_bills_count: 두 의원이 모두 발의·공동발의한 의안 수
    - vote_agreement_pct: 공통 표결 의안에서 value 일치 비율
    - same_committee: MEMBER_OF 교집합 여부
    - cross_party: 정당 다름 여부
    """
    if a == b:
        raise HTTPException(400, "같은 의원은 비교 불가")

    ma = _fetch_member(a)
    mb = _fetch_member(b)
    if not ma or not mb:
        raise HTTPException(404, f"의원 미존재: a={a}, b={b}")

    # 1. CO_PROPOSED_WITH count
    co_res = nep.open_cypher(
        "MATCH (pa:Person {assembly_id: $a})-[r:CO_PROPOSED_WITH]-(pb:Person {assembly_id: $b}) "
        "RETURN r.count AS cnt LIMIT 1",
        parameters={"a": a, "b": b},
    )
    co_rows = co_res.rows if hasattr(co_res, "rows") else co_res.get("results", [])
    co_propose_count = int(co_rows[0]["cnt"]) if co_rows else 0

    # 2. 공유 의안 — 둘 다 PROPOSED 또는 CO_PROPOSED
    shared_res = nep.open_cypher(
        "MATCH (pa:Person {assembly_id: $a})-[:PROPOSED|CO_PROPOSED]->(b:Bill)<-[:PROPOSED|CO_PROPOSED]-(pb:Person {assembly_id: $b}) "
        "WHERE b.title IS NOT NULL AND b.title <> '' "
        "RETURN b.title AS title LIMIT 5",
        parameters={"a": a, "b": b},
    )
    shared_rows = shared_res.rows if hasattr(shared_res, "rows") else shared_res.get("results", [])
    shared_bills = [r.get("title") for r in shared_rows if r.get("title")]
    shared_bills_count = len(shared_bills)

    # 3. 공통 표결 + 일치율
    va_res = nep.open_cypher(
        "MATCH (pa:Person {assembly_id: $a})-[va:VOTED]->(b:Bill)<-[vb:VOTED]-(pb:Person {assembly_id: $b}) "
        "RETURN count(b) AS total, sum(CASE WHEN va.value = vb.value THEN 1 ELSE 0 END) AS agree",
        parameters={"a": a, "b": b},
    )
    va_rows = va_res.rows if hasattr(va_res, "rows") else va_res.get("results", [])
    total_votes = 0
    agree_votes = 0
    if va_rows:
        total_votes = int(va_rows[0].get("total") or 0)
        agree_votes = int(va_rows[0].get("agree") or 0)
    vote_agreement_pct = int((agree_votes / total_votes * 100)) if total_votes > 0 else 0

    # 4. 같은 위원회
    cmt_res = nep.open_cypher(
        "MATCH (pa:Person {assembly_id: $a})-[:MEMBER_OF]->(c:Committee)<-[:MEMBER_OF]-(pb:Person {assembly_id: $b}) "
        "RETURN count(c) AS cnt",
        parameters={"a": a, "b": b},
    )
    cmt_rows = cmt_res.rows if hasattr(cmt_res, "rows") else cmt_res.get("results", [])
    same_committee = (int(cmt_rows[0].get("cnt") or 0) > 0) if cmt_rows else False

    cross_party = ma["party"] != mb["party"]

    # 5. Cross-party rating
    if vote_agreement_pct >= 80:
        rating = "strong"
    elif vote_agreement_pct >= 60:
        rating = "moderate"
    else:
        rating = "weak"

    # 6. Shared topic 결정 우선순위:
    #    (a) 공동 발의 의안 카테고리 (가장 빈도 높은 카테고리)
    #    (b) 같은 위원회 소속이면 해당 위원회 이름
    #    (c) cross-party 표결 일치율이 의미 있으면 "양당 협력 표결" / "당론 분리 표결"
    #    (d) fallback: 정당간 비교
    shared_topic = "—"
    if shared_bills:
        topic_res = nep.open_cypher(
            "MATCH (pa:Person {assembly_id: $a})-[:PROPOSED|CO_PROPOSED]->(b:Bill)<-[:PROPOSED|CO_PROPOSED]-(pb:Person {assembly_id: $b}) "
            "WHERE b.category IS NOT NULL AND b.category <> '' "
            "RETURN b.category AS category, count(*) AS cnt "
            "ORDER BY cnt DESC LIMIT 1",
            parameters={"a": a, "b": b},
        )
        topic_rows = topic_res.rows if hasattr(topic_res, "rows") else topic_res.get("results", [])
        if topic_rows:
            shared_topic = topic_rows[0].get("category") or "—"
    if shared_topic == "—" and same_committee:
        # 같은 위원회 이름 lookup
        cmt_name_res = nep.open_cypher(
            "MATCH (pa:Person {assembly_id: $a})-[:MEMBER_OF]->(c:Committee)<-[:MEMBER_OF]-(pb:Person {assembly_id: $b}) "
            "RETURN c.name AS name LIMIT 1",
            parameters={"a": a, "b": b},
        )
        cmt_name_rows = cmt_name_res.rows if hasattr(cmt_name_res, "rows") else cmt_name_res.get("results", [])
        if cmt_name_rows and cmt_name_rows[0].get("name"):
            shared_topic = cmt_name_rows[0]["name"]
    if shared_topic == "—" and total_votes > 0:
        # 표결 일치율 기반 라벨
        if cross_party and vote_agreement_pct >= 80:
            shared_topic = f"양당 협력 표결 {vote_agreement_pct}%"
        elif cross_party and vote_agreement_pct < 30:
            shared_topic = f"당론 분리 표결 {vote_agreement_pct}%"
        elif not cross_party and vote_agreement_pct >= 90:
            shared_topic = f"당론 일치 {vote_agreement_pct}%"
        else:
            shared_topic = f"표결 일치율 {vote_agreement_pct}%"
    if shared_topic == "—":
        # 최종 fallback: 정당간 cross-party 라벨
        shared_topic = "정당간 비교" if cross_party else "당내 비교"

    # 7. Narrative
    if cross_party:
        relation_kind = f"*정파를 가로지르는 {rating} cross-party 협력*"
    else:
        relation_kind = f"같은 정당 내 *정책 친밀도 {rating}*"

    narrative = (
        f"{ma['name']}({ma['party']}) ↔ {mb['name']}({mb['party']}) — "
        f"공동발의 cohort {co_propose_count}건 · 공유 의안 {shared_bills_count}건 · "
        f"표결 일치율 {vote_agreement_pct}% (공통 {total_votes}건). "
        f"{relation_kind}. "
        + (f"공유 토픽: \"{shared_topic}\". " if shared_topic != "—" else "")
        + ("같은 위원회 소속. " if same_committee else "")
        + "(출처: 22대 임기 · Neptune real CO_PROPOSED_WITH + VOTED + MEMBER_OF)."
    )

    return RelationResult(
        member_a=MemberInfo(**ma),
        member_b=MemberInfo(**mb),
        metrics=RelationMetrics(
            co_propose_count=co_propose_count,
            shared_bills_count=shared_bills_count,
            vote_agreement_pct=vote_agreement_pct,
            common_votes=total_votes,
            same_committee=same_committee,
            cross_party=cross_party,
        ),
        cross_party_rating=rating,
        narrative=narrative,
        shared_topic=shared_topic,
        shared_bills=shared_bills,
        source="real",
    )
