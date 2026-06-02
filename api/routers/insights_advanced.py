"""고급 인사이트 시나리오 — Phase 4f.

74,249 real edges 기반 *추가 분석*:
- T 정당 응집도 (Party Cohesion Score)
- U 의원 영향력 (Influence Rank, CO_PROPOSED_WITH degree centrality)
- V 표결 패턴 cluster (Voting Pattern Cluster — 정당 majority 기반)
- W Swing voter detection (정당 이탈 빈번 의원)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from api.services import neptune as nep

router = APIRouter(prefix="/api/insights", tags=["insights-advanced"])


# ─── T 정당 응집도 ─────────────────────────────────────────────────────────

class PartyCohesion(BaseModel):
    party: str
    member_count: int
    total_votes: int
    majority_alignment_pct: int  # 정당 majority value와 일치한 의원 표결 비율
    cohesion_score: float        # 0-1


class PartyCohesionResponse(BaseModel):
    parties: list[PartyCohesion]
    overall_cohesion: float
    source: str = "real"


@router.get("/party-cohesion", response_model=PartyCohesionResponse)
def get_party_cohesion() -> PartyCohesionResponse:
    """각 정당의 응집도 score — 정당 majority와 다른 의원 표결 비율 측정."""
    # 각 의원의 정당·표결 fetch
    res = nep.open_cypher(
        "MATCH (p:Person)-[v:VOTED]->(b:Bill) "
        "OPTIONAL MATCH (p)-[:BELONGS_TO]->(pa:Party) "
        "RETURN p.assembly_id AS mona, p.party_id AS party_id, pa.name AS party_name, "
        "v.value AS choice, b.bill_id AS bid",
    )
    rows = res.rows if hasattr(res, "rows") else res.get("results", [])

    # bill_id × party majority 계산
    from collections import defaultdict
    bill_party_votes: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_votes_per_party: dict[str, list] = defaultdict(list)

    for r in rows:
        party = r.get("party_name") or r.get("party_id") or "무소속"
        choice = r.get("choice") or "absent"
        bid = r.get("bid") or ""
        if not bid:
            continue
        bill_party_votes[(bid, party)][choice] += 1
        all_votes_per_party[party].append((bid, choice))

    # 각 (bill, party)의 majority
    bill_party_majority: dict[tuple, str] = {}
    for key, choices in bill_party_votes.items():
        # absent는 majority에서 제외
        active = {k: v for k, v in choices.items() if k in ("yes", "no", "abstain")}
        if active:
            bill_party_majority[key] = max(active, key=active.get)
        else:
            bill_party_majority[key] = "absent"

    # 정당별 응집도
    party_stats = []
    for party, votes in all_votes_per_party.items():
        if not votes:
            continue
        # member_count from BELONGS_TO
        mc_res = nep.open_cypher(
            "MATCH (p:Person)-[:BELONGS_TO]->(pa:Party {name: $name}) "
            "RETURN count(p) AS cnt",
            parameters={"name": party},
        )
        mc_rows = mc_res.rows if hasattr(mc_res, "rows") else mc_res.get("results", [])
        member_count = int(mc_rows[0].get("cnt") or 0) if mc_rows else 0

        # active 표결만 (absent 제외) 응집도 계산
        active_votes = [(bid, c) for bid, c in votes if c in ("yes", "no", "abstain")]
        if not active_votes:
            party_stats.append(PartyCohesion(
                party=party, member_count=member_count,
                total_votes=len(votes), majority_alignment_pct=0, cohesion_score=0.0,
            ))
            continue
        aligned = sum(
            1 for bid, c in active_votes
            if bill_party_majority.get((bid, party)) == c
        )
        align_pct = int(aligned / len(active_votes) * 100)
        party_stats.append(PartyCohesion(
            party=party,
            member_count=member_count,
            total_votes=len(active_votes),
            majority_alignment_pct=align_pct,
            cohesion_score=round(align_pct / 100, 3),
        ))

    party_stats.sort(key=lambda p: -p.cohesion_score)
    overall = sum(p.cohesion_score for p in party_stats) / max(1, len(party_stats))

    return PartyCohesionResponse(
        parties=party_stats,
        overall_cohesion=round(overall, 3),
        source="real",
    )


# ─── U 의원 영향력 (Degree Centrality) ───────────────────────────────────

class InfluenceMember(BaseModel):
    assembly_id: str
    name: str
    party: str
    district: str
    proposed_count: int        # 대표 발의 수
    co_proposed_count: int     # 공동 발의 수
    cohort_weight_sum: int     # CO_PROPOSED_WITH count 합 (영향력 proxy)
    voted_count: int           # 표결 참여 수
    influence_score: float     # 0-1 normalized


class InfluenceRankResponse(BaseModel):
    members: list[InfluenceMember]
    total_members: int
    source: str = "real"


@router.get("/influence-rank", response_model=InfluenceRankResponse)
def get_influence_rank(
    limit: int = Query(default=20, ge=1, le=100),
) -> InfluenceRankResponse:
    """의원 영향력 ranking — CO_PROPOSED_WITH cohort 가중치 합 기반.

    Phase 4f 최적화: cohort weight 가장 큰 top-N 의원만 expand (heavy OPTIONAL MATCH 회피).
    """
    # Step 1: cohort weight 기준 top-N candidates
    cohort_res = nep.open_cypher(
        "MATCH (p:Person)-[r:CO_PROPOSED_WITH]-(:Person) "
        "WITH p, sum(r.count) AS cohort_weight "
        "ORDER BY cohort_weight DESC LIMIT $cap "
        "RETURN p.assembly_id AS mona, cohort_weight",
        parameters={"cap": limit * 2},
    )
    cohort_rows = cohort_res.rows if hasattr(cohort_res, "rows") else cohort_res.get("results", [])
    if not cohort_rows:
        return InfluenceRankResponse(members=[], total_members=0, source="real")

    cohort_map = {r.get("mona"): int(r.get("cohort_weight") or 0) for r in cohort_rows}
    top_ids = list(cohort_map.keys())

    # Step 2: meta + counts in 2 small queries (heavy aggregation 회피)
    # 2a) meta only
    meta_res = nep.open_cypher(
        "UNWIND $ids AS mid "
        "MATCH (p:Person {assembly_id: mid}) "
        "OPTIONAL MATCH (p)-[:BELONGS_TO]->(pa:Party) "
        "RETURN p.assembly_id AS mona, p.name AS name, p.party_id AS party_id, "
        "pa.name AS party, p.district_id AS district",
        parameters={"ids": top_ids},
    )
    meta_rows = meta_res.rows if hasattr(meta_res, "rows") else meta_res.get("results", [])
    meta_map = {r.get("mona"): r for r in meta_rows}

    # 2b) per-person counts — VOTED 제외 (cardinality blow-up 회피)
    # voted count는 영향력 score 가중치 작아서 skip 가능
    res = nep.open_cypher(
        "UNWIND $ids AS mid "
        "MATCH (p:Person {assembly_id: mid}) "
        "OPTIONAL MATCH (p)-[pr:PROPOSED]->(:Bill) "
        "OPTIONAL MATCH (p)-[cp:CO_PROPOSED]->(:Bill) "
        "RETURN p.assembly_id AS mona, "
        "count(DISTINCT pr) AS proposed, count(DISTINCT cp) AS co_proposed",
        parameters={"ids": top_ids},
    )
    rows = res.rows if hasattr(res, "rows") else res.get("results", [])

    max_cohort = max(cohort_map.values()) if cohort_map else 1
    members = []
    for r in rows:
        mona = r.get("mona") or ""
        cohort = cohort_map.get(mona, 0)
        proposed = int(r.get("proposed") or 0)
        co_proposed = int(r.get("co_proposed") or 0)
        voted = 0  # heavy VOTED count skipped (Phase 4g에서 lightweight 별도 query로 보강 가능)
        meta = meta_map.get(mona, {})
        # influence: 0.6 * cohort_norm + 0.25 * proposed_norm + 0.15 * co_norm (voted 가중치 cohort에 흡수)
        influence = round(min(1.0,
            0.6 * (cohort / max(1, max_cohort)) +
            0.25 * (proposed / 30.0) +
            0.15 * (co_proposed / 200.0)
        ), 3)
        members.append(InfluenceMember(
            assembly_id=mona,
            name=meta.get("name") or "—",
            party=meta.get("party") or meta.get("party_id") or "—",
            district=meta.get("district") or "—",
            proposed_count=proposed,
            co_proposed_count=co_proposed,
            cohort_weight_sum=cohort,
            voted_count=voted,
            influence_score=influence,
        ))

    members.sort(key=lambda m: -m.influence_score)
    return InfluenceRankResponse(
        members=members[:limit],
        total_members=len(cohort_rows),
        source="real",
    )


# ─── V 표결 패턴 cluster (간단 카테고리 분류 — KMeans 없이) ───────────

class VotingCluster(BaseModel):
    cluster_id: str
    label: str
    members: list[dict]
    member_count: int
    dominant_parties: list[str]
    avg_yes_rate: float


class VotingClusterResponse(BaseModel):
    clusters: list[VotingCluster]
    source: str = "real"
    method: str = "정당 majority 기반 cohort 분류"


@router.get("/voting-cluster", response_model=VotingClusterResponse)
def get_voting_cluster() -> VotingClusterResponse:
    """표결 패턴 cluster — 정당별 + 응집도 cohort 분류 (KMeans 없이 단순 분류).

    Phase 4f 최적화: WITH 절로 의원별 aggregation 먼저 (memory 축소).
    """
    res = nep.open_cypher(
        "MATCH (p:Person)-[v:VOTED]->(:Bill) "
        "WITH p, count(v) AS total, sum(CASE WHEN v.value = 'yes' THEN 1 ELSE 0 END) AS yes_cnt "
        "WHERE total >= 5 "
        "OPTIONAL MATCH (p)-[:BELONGS_TO]->(pa:Party) "
        "RETURN p.assembly_id AS mona, p.name AS name, pa.name AS party, total, yes_cnt",
    )
    rows = res.rows if hasattr(res, "rows") else res.get("results", [])

    # cluster by party + yes_rate
    from collections import defaultdict
    cluster_members: dict[str, list] = defaultdict(list)
    for r in rows:
        total = int(r.get("total") or 0)
        if total < 5:
            continue
        yes_cnt = int(r.get("yes_cnt") or 0)
        yes_rate = yes_cnt / total
        party = r.get("party") or "무소속"
        # 5 cluster: 보수 high-yes / 보수 low-yes / 진보 high-yes / 진보 low-yes / 중도
        if party in ("더불어민주당", "조국혁신당", "진보당", "기본소득당"):
            cluster_id = "progressive_high" if yes_rate >= 0.7 else "progressive_low"
            label = "진보계열 · 높은 찬성률" if yes_rate >= 0.7 else "진보계열 · 신중 표결"
        elif party in ("국민의힘", "개혁신당"):
            cluster_id = "conservative_high" if yes_rate >= 0.7 else "conservative_low"
            label = "보수계열 · 높은 찬성률" if yes_rate >= 0.7 else "보수계열 · 신중 표결"
        else:
            cluster_id = "centrist"
            label = "중도·무소속 cluster"
        member_info = {
            "assembly_id": r.get("mona"),
            "name": r.get("name"),
            "party": party,
            "yes_rate": round(yes_rate, 2),
            "total_votes": total,
        }
        cluster_members[(cluster_id, label)].append(member_info)

    clusters = []
    for (cid, label), members in cluster_members.items():
        parties_count = {}
        yes_sum = 0
        for m in members:
            parties_count[m["party"]] = parties_count.get(m["party"], 0) + 1
            yes_sum += m["yes_rate"]
        dominant = sorted(parties_count.items(), key=lambda x: -x[1])[:3]
        clusters.append(VotingCluster(
            cluster_id=cid,
            label=label,
            members=members[:10],  # top 10 sample
            member_count=len(members),
            dominant_parties=[p for p, _ in dominant],
            avg_yes_rate=round(yes_sum / max(1, len(members)), 2),
        ))

    clusters.sort(key=lambda c: -c.member_count)
    return VotingClusterResponse(clusters=clusters, source="real")


# ─── W Swing voter detection ─────────────────────────────────────────────

class SwingMember(BaseModel):
    assembly_id: str
    name: str
    party: str
    district: str
    party_majority_alignment_pct: int
    total_active_votes: int
    deviation_count: int


class SwingVotersResponse(BaseModel):
    members: list[SwingMember]
    total_evaluated: int
    threshold_pct: int
    source: str = "real"


@router.get("/swing-voters", response_model=SwingVotersResponse)
def get_swing_voters(
    limit: int = Query(default=20, ge=1, le=100),
    threshold_pct: int = Query(default=85, ge=50, le=100),
) -> SwingVotersResponse:
    """정당 일치율 < threshold_pct인 의원 ranking (swing voter).

    Phase 4f 최적화: VOTED 엣지가 많은 의원만 evaluation.
    """
    # 표결 참여가 충분한 의원만 (최소 10건)
    res = nep.open_cypher(
        "MATCH (p:Person)-[v:VOTED]->(b:Bill) "
        "WHERE v.value IN ['yes','no','abstain'] "
        "OPTIONAL MATCH (p)-[:BELONGS_TO]->(pa:Party) "
        "WITH p, pa, b, v "
        "RETURN p.assembly_id AS mona, p.name AS name, pa.name AS party, "
        "p.district_id AS district, "
        "b.bill_id AS bid, v.value AS choice",
    )
    rows = res.rows if hasattr(res, "rows") else res.get("results", [])

    # bill × party majority
    from collections import defaultdict
    bill_party_votes: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    member_votes: dict[str, dict] = defaultdict(lambda: {
        "name": "", "party": "", "district": "",
        "votes": []
    })

    for r in rows:
        party = r.get("party") or "무소속"
        choice = r.get("choice") or "absent"
        bid = r.get("bid") or ""
        mona = r.get("mona") or ""
        if not bid or not mona:
            continue
        if choice in ("yes", "no", "abstain"):
            bill_party_votes[(bid, party)][choice] += 1
        member_votes[mona]["name"] = r.get("name") or ""
        member_votes[mona]["party"] = party
        member_votes[mona]["district"] = r.get("district") or ""
        member_votes[mona]["votes"].append((bid, choice))

    bill_party_majority = {}
    for key, choices in bill_party_votes.items():
        if choices:
            bill_party_majority[key] = max(choices, key=choices.get)

    swings = []
    for mona, info in member_votes.items():
        active = [(bid, c) for bid, c in info["votes"] if c in ("yes", "no", "abstain")]
        if len(active) < 10:
            continue  # 최소 10건 active 표결
        aligned = sum(
            1 for bid, c in active
            if bill_party_majority.get((bid, info["party"])) == c
        )
        align_pct = int(aligned / len(active) * 100)
        deviation_count = len(active) - aligned
        if align_pct < threshold_pct:
            swings.append(SwingMember(
                assembly_id=mona,
                name=info["name"],
                party=info["party"],
                district=info["district"],
                party_majority_alignment_pct=align_pct,
                total_active_votes=len(active),
                deviation_count=deviation_count,
            ))

    swings.sort(key=lambda s: s.party_majority_alignment_pct)
    return SwingVotersResponse(
        members=swings[:limit],
        total_evaluated=len(member_votes),
        threshold_pct=threshold_pct,
        source="real",
    )
