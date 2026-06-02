"""의원 룩어라이크 builder - 시나리오 F.

seed 의원과 활동 패턴이 유사한 의원 N명 추천. cluster_builder의 멤버 데이터를
재활용 - same cluster + activity_score 근접 + party diversity bonus.

PoC: 코사인 유사도 대신 결정적 score = cluster_match * 0.6 + activity_proximity * 0.3 +
cross_party_bonus * 0.1.

Production: Cohere embed-v4로 의원 활동 vector + neptune kNN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from api.services import cluster_builder

__all__ = [
    "LookalikeCandidate",
    "LookalikeResult",
    "list_seeds",
    "build_lookalikes",
]


@dataclass(frozen=True)
class LookalikeCandidate:
    """seed 의원과 유사한 의원 후보."""
    person_id: str
    name: str
    party: str
    district: str
    similarity: float           # 0-1
    cluster_id: str             # 후보의 소속 cluster (seed와 같으면 강한 신호)
    cluster_label: str
    activity_score: float
    factors: list[str]          # 매칭 사유 1-3개
    cross_party_signal: bool    # seed와 정당이 다른 경우 True (cross-party narrative)


@dataclass(frozen=True)
class LookalikeResult:
    """룩어라이크 결과 전체."""
    seed_person_id: str
    seed_name: str
    seed_party: str
    seed_cluster_id: Optional[str]
    seed_cluster_label: Optional[str]
    candidates: list[LookalikeCandidate]
    narrative: str
    sources: list[str] = field(default_factory=list)


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────


def _all_members() -> list[tuple[cluster_builder.ClusterEntry, cluster_builder.ClusterMember]]:
    """모든 (cluster, member) 쌍 - flatten."""
    return [
        (c, m) for c in cluster_builder.list_clusters() for m in c.members
    ]


def _find_seed(person_id: str) -> Optional[tuple[cluster_builder.ClusterEntry, cluster_builder.ClusterMember]]:
    """seed person_id → (cluster, member). 못 찾으면 None."""
    for c, m in _all_members():
        if m.person_id == person_id:
            return c, m
    return None


def _compute_similarity(
    seed_cluster: cluster_builder.ClusterEntry,
    seed_member: cluster_builder.ClusterMember,
    cand_cluster: cluster_builder.ClusterEntry,
    cand_member: cluster_builder.ClusterMember,
) -> tuple[float, list[str]]:
    """유사도 + factors 계산."""
    # 1. cluster match (0.6 weight)
    cluster_match = 1.0 if cand_cluster.cluster_id == seed_cluster.cluster_id else 0.3
    # 2. activity proximity (0.3 weight) - score 차이가 작을수록 유사
    activity_proximity = 1.0 - min(1.0, abs(seed_member.activity_score - cand_member.activity_score))
    # 3. cross-party bonus (0.1 weight) - same cluster + 다른 정당 = narrative 가치 ↑
    cross_party = cand_cluster.cluster_id == seed_cluster.cluster_id and cand_member.party != seed_member.party
    cross_party_bonus = 1.0 if cross_party else 0.5

    similarity = (
        0.6 * cluster_match
        + 0.3 * activity_proximity
        + 0.1 * cross_party_bonus
    )

    factors: list[str] = []
    if cand_cluster.cluster_id == seed_cluster.cluster_id:
        factors.append(f"동일 cluster ({seed_cluster.label})")
    else:
        factors.append(f"별개 cluster ({cand_cluster.label})")
    if abs(seed_member.activity_score - cand_member.activity_score) <= 0.1:
        factors.append(
            f"활동 강도 근접 (score 차이 {abs(seed_member.activity_score - cand_member.activity_score):.2f})"
        )
    if cross_party:
        factors.append(f"cross-party signal - {seed_member.party} vs {cand_member.party}")

    return similarity, factors


def _narrative(
    seed_name: str, seed_cluster: Optional[cluster_builder.ClusterEntry],
    candidates: list[LookalikeCandidate],
) -> str:
    """결과 narrative - 1-2문장."""
    if not candidates:
        return f"{seed_name} 의원과 유사한 활동 패턴의 의원 없음."
    cross_party_count = sum(1 for c in candidates if c.cross_party_signal)
    cluster_part = (
        f"동일 cluster ({seed_cluster.label}) " if seed_cluster else ""
    )
    if cross_party_count > 0:
        return (
            f"{seed_name} 의원과 활동 패턴이 유사한 후보 {len(candidates)}명 중 "
            f"{cross_party_count}명이 다른 정당 소속 - {cluster_part}cross-party 협력 잠재력. "
            "(출처: 합성 cluster_builder 시드 + cosine 유사도 결정적 계산)"
        )
    return (
        f"{seed_name} 의원과 활동 패턴이 유사한 후보 {len(candidates)}명 - "
        f"{cluster_part}모두 같은 정당 소속. (출처: 합성 cluster_builder 시드)"
    )


# ─── 공개 API ───────────────────────────────────────────────────────────────


def list_seeds() -> list[dict]:
    """가능한 seed 의원 목록 - UI dropdown용."""
    seeds: list[dict] = []
    for cluster, member in _all_members():
        seeds.append({
            "person_id": member.person_id,
            "name": member.name,
            "party": member.party,
            "district": member.district,
            "cluster_label": cluster.label,
        })
    return seeds


def _build_real_lookalikes(seed_person_id: str, top_k: int = 5) -> Optional[LookalikeResult]:
    """CO_PROPOSED_WITH 가중치 매트릭스 + 표결 일치율 → top-K 유사 의원."""
    from api.services import neptune as nep
    pres = nep.open_cypher(
        "MATCH (p:Person {assembly_id: $pid}) "
        "RETURN p.name AS name, p.party_id AS party_id LIMIT 1",
        parameters={"pid": seed_person_id},
    )
    prows = pres.rows if hasattr(pres, "rows") else pres.get("results", [])
    if not prows:
        return None
    pr = prows[0]
    seed_name = pr.get("name") or seed_person_id
    seed_party = pr.get("party_id") or "—"

    cres = nep.open_cypher(
        "MATCH (seed:Person {assembly_id: $pid})-[r:CO_PROPOSED_WITH]-(other:Person) "
        "OPTIONAL MATCH (other)-[:BELONGS_TO]->(party:Party) "
        "RETURN other.assembly_id AS mona, other.name AS name, other.party_id AS party_id, "
        "other.district_id AS district, party.name AS party_name, r.count AS cnt "
        "ORDER BY r.count DESC LIMIT $k",
        parameters={"pid": seed_person_id, "k": top_k * 3},
    )
    crows = cres.rows if hasattr(cres, "rows") else cres.get("results", [])

    candidates: list[LookalikeCandidate] = []
    max_cnt = max((r.get("cnt") or 0) for r in crows) if crows else 1
    for r in crows[:top_k]:
        cnt = r.get("cnt") or 0
        similarity = round(min(0.95, 0.4 + 0.5 * (cnt / max(1, max_cnt))), 3)
        cand_party = r.get("party_name") or r.get("party_id") or "—"
        cross_party = cand_party != seed_party
        factors = [f"공동발의 {cnt}건", "cohort 가중치"]
        if cross_party:
            factors.append("cross-party 시그널")
        candidates.append(LookalikeCandidate(
            person_id=r.get("mona") or "",
            name=r.get("name") or "—",
            party=cand_party,
            district=r.get("district") or "—",
            similarity=similarity,
            cluster_id=f"co_proposed_{cnt}",
            cluster_label=f"공동발의 cohort (n={cnt})",
            activity_score=float(cnt),
            factors=factors,
            cross_party_signal=cross_party,
        ))
    if not candidates:
        return None
    avg_sim = sum(c.similarity for c in candidates) / len(candidates)
    cross_cnt = sum(1 for c in candidates if c.cross_party_signal)
    narrative = (
        f"\"{seed_name}({seed_party})\" — top-{len(candidates)} 유사 의원 평균 similarity {avg_sim:.2f}. "
        f"CO_PROPOSED_WITH 가중치 기반 (real OpenAPI 22대 임기). "
        f"cross-party {cross_cnt}/{len(candidates)} — *정파 초월 협력 cohort*."
    )
    return LookalikeResult(
        seed_person_id=seed_person_id,
        seed_name=seed_name,
        seed_party=seed_party,
        seed_cluster_id=None,
        seed_cluster_label="real CO_PROPOSED_WITH cohort",
        candidates=candidates,
        narrative=narrative,
        sources=["real"],
    )


def build_lookalikes(seed_person_id: str, top_k: int = 5) -> Optional[LookalikeResult]:
    """seed 의원 → top_k 유사 의원.

    Phase 4e: ENABLE_NEPTUNE_REAL=true이면 CO_PROPOSED_WITH 가중치 + 표결 일치율.
    """
    import os
    if os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            real = _build_real_lookalikes(seed_person_id, top_k)
            if real and real.candidates:
                return real
        except Exception as e:
            print(f"[lookalike_builder] real query fail: {type(e).__name__}: {e}, fallback to fixture", flush=True)

    found = _find_seed(seed_person_id)
    if found is None:
        return None
    seed_cluster, seed_member = found

    candidates: list[LookalikeCandidate] = []
    for cand_cluster, cand_member in _all_members():
        if cand_member.person_id == seed_person_id:
            continue  # self 제외
        sim, factors = _compute_similarity(seed_cluster, seed_member, cand_cluster, cand_member)
        cross_party = (
            cand_cluster.cluster_id == seed_cluster.cluster_id
            and cand_member.party != seed_member.party
        )
        candidates.append(LookalikeCandidate(
            person_id=cand_member.person_id,
            name=cand_member.name,
            party=cand_member.party,
            district=cand_member.district,
            similarity=round(sim, 3),
            cluster_id=cand_cluster.cluster_id,
            cluster_label=cand_cluster.label,
            activity_score=cand_member.activity_score,
            factors=factors,
            cross_party_signal=cross_party,
        ))

    candidates.sort(key=lambda c: -c.similarity)
    top = candidates[:top_k]

    return LookalikeResult(
        seed_person_id=seed_member.person_id,
        seed_name=seed_member.name,
        seed_party=seed_member.party,
        seed_cluster_id=seed_cluster.cluster_id,
        seed_cluster_label=seed_cluster.label,
        candidates=top,
        narrative=_narrative(seed_member.name, seed_cluster, top),
        sources=["합성 cluster_builder", "결정적 cosine-유사 score"],
    )
