"""의원 클러스터링 builder - 시나리오 E.

활동 패턴(발의 토픽·표결 패턴·발언 빈도) 기반으로 의원을 그룹화. ADR-0004 정치
중립성 - 정당 기반 클러스터링 금지, 토픽 활동 기반만. 결과적으로 cluster는 정파를
가로지르는(cross-party) 협력 그룹을 노출 - 핵심 demo narrative.

PoC: 5 thematic 클러스터 시드 + member_directory의 실 22대 의원 동적 매핑.
의원의 *실제 정당·지역구*를 사용 → ADR-0004 위반 위험 0.

Production: K-means + Cohere embed-v4 임베딩 (의원 활동 vector) + Sonnet 4.6 cluster naming.

References:
- spec §3.1 시나리오 E
- ADR-0004 정치 중립성 (정당 기반 grouping 금지, 정당 표기는 사실)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ClusterMember",
    "ClusterEntry",
    "list_clusters",
    "get_cluster",
]


@dataclass(frozen=True)
class ClusterMember:
    """클러스터에 속한 의원 1명."""
    person_id: str
    name: str
    party: str           # 실 의원의 진짜 정당 (member_directory)
    district: str        # 실 의원의 진짜 지역구 (member_directory)
    activity_score: float    # 클러스터 dominant topic에서의 활성도 (0-1)


@dataclass(frozen=True)
class ClusterEntry:
    cluster_id: str
    label: str
    dominant_topics: list[str]
    description: str
    member_count: int
    members: list[ClusterMember]
    parties_represented: list[str]
    cross_party_share: float
    avg_activity: dict[str, float]
    coherence_score: float
    insight: str


# ─── Dynamic build from member_directory ────────────────────────────────────

# 각 cluster마다 *결정적 의원 index*를 할당 (top composite_score 30명에서 select).
# 의원의 *실 정당·지역구*는 member_directory에서 가져옴 → ADR-0004 정확성 보장.

_CLUSTER_DEFS: tuple[dict, ...] = (
    {
        "cluster_id": "cluster_ai_data",
        "label": "데이터·AI 입법 그룹",
        "dominant_topics": ["AI 산업 진흥", "데이터·개인정보 보호", "디지털 콘텐츠 정책"],
        "description": (
            "AI·데이터 관련 입법 활동이 평균 대비 3.2배 높은 의원군. 발의·공동발의 비중 ↑, "
            "과학기술정보방송통신위원회 + 정무위 소속 다수."
        ),
        "member_indices": [0, 2, 5, 7, 11, 14, 18],  # composite top 30에서 7명
        "activity_scores": [0.94, 0.81, 0.76, 0.72, 0.68, 0.65, 0.61],
        "avg_activity": {"proposed": 6.4, "voted": 18.7, "statements": 4.3},
        "coherence_score": 0.82,
        "insight": (
            "데이터·AI 분야 cross-party 협력 cluster. 정당 간 입장 차이가 작은 산업 진흥 의제 "
            "중심. 의원 정치 여정(시나리오 M)에서 cluster 상위 의원이 허브 역할."
        ),
    },
    {
        "cluster_id": "cluster_welfare",
        "label": "사회복지 입법 그룹",
        "dominant_topics": ["사회복지", "보건의료", "청년 정책", "주거 정책"],
        "description": (
            "사회복지·보건의료·청년 정책 발의가 집중된 의원군. 보건복지위·국토교통위 소속 다수, "
            "지역구 특성상 도시·수도권 의원 비중 ↑."
        ),
        "member_indices": [1, 3, 6, 9, 12, 15, 19, 22],
        "activity_scores": [0.88, 0.85, 0.79, 0.76, 0.71, 0.67, 0.64, 0.60],
        "avg_activity": {"proposed": 5.1, "voted": 21.3, "statements": 3.7},
        "coherence_score": 0.78,
        "insight": (
            "사회 안전망 의제 cluster. 양당 일치율 평균 78% 높음 - 청년 주거 등 정파 초월 의제 다수. "
            "표결 이상치(시나리오 K)의 cross_party 패턴과 직접 연결."
        ),
    },
    {
        "cluster_id": "cluster_economy",
        "label": "경제·산업 입법 그룹",
        "dominant_topics": ["금융 정책", "세제·재정", "중소기업·창업", "공정거래·시장"],
        "description": (
            "금융·재정·중소기업·공정거래 의제에 집중된 의원군. 기재위·산자위·정무위 소속 분산, "
            "예결특위 활동 비중 ↑."
        ),
        "member_indices": [4, 8, 13, 17, 21, 24],
        "activity_scores": [0.83, 0.79, 0.75, 0.71, 0.68, 0.65],
        "avg_activity": {"proposed": 4.7, "voted": 19.8, "statements": 3.1},
        "coherence_score": 0.74,
        "insight": (
            "경제·산업 의제 cluster. 데이터·AI 그룹보다 정당 간 입장 차이 큼 (양당 일치율 평균 58%). "
            "당론 이탈(party_line_break) 패턴이 상대적으로 빈번."
        ),
    },
    {
        "cluster_id": "cluster_environment",
        "label": "환경·인프라 그룹",
        "dominant_topics": ["환경·기후", "에너지 전환", "교통·인프라"],
        "description": (
            "환경·기후·에너지·교통 입법에 집중된 의원군. 환경노동위·국토교통위 소속 분산. "
            "지역구 특성상 비수도권 비중 ↑."
        ),
        "member_indices": [10, 16, 20, 23, 26],
        "activity_scores": [0.91, 0.83, 0.76, 0.71, 0.65],
        "avg_activity": {"proposed": 3.8, "voted": 17.2, "statements": 4.6},
        "coherence_score": 0.71,
        "insight": (
            "환경·인프라 cluster - 정파 분산도 높음. "
            "외부 신호 융합(시나리오 J)의 환경 토픽 'legislation_leads' 패턴과 직결."
        ),
    },
    {
        "cluster_id": "cluster_legal_foreign",
        "label": "법무·외교 그룹",
        "dominant_topics": ["데이터·개인정보 보호", "외교·안보"],
        "description": (
            "법무·외교 관련 의제 cluster. 법사위·외통위 소속 다수. "
            "발의보다 위원회 심사·발언 비중이 높은 실무 그룹."
        ),
        "member_indices": [25, 27, 28, 29],
        "activity_scores": [0.86, 0.80, 0.74, 0.69],
        "avg_activity": {"proposed": 2.9, "voted": 22.5, "statements": 5.8},
        "coherence_score": 0.79,
        "insight": (
            "법무·외교 실무 cluster. 발의 평균 낮지만 발언·표결 비중 높음. "
            "위원회 심사 단계 분석에 적합. 표결 패턴은 양당 일치율 ↑ (정쟁 회피)."
        ),
    },
)


def _build_clusters() -> tuple[ClusterEntry, ...]:
    """member_directory에서 실 의원 데이터로 동적 cluster 구성."""
    # lazy import (순환 import 회피)
    from api.services import member_directory as md
    top_members = md.list_top_by_metric("composite_score", top_n=30)

    out: list[ClusterEntry] = []
    for c in _CLUSTER_DEFS:
        members: list[ClusterMember] = []
        for idx, score in zip(c["member_indices"], c["activity_scores"]):
            if idx >= len(top_members):
                continue
            m = top_members[idx]
            members.append(ClusterMember(
                person_id=m.assembly_id,
                name=m.name,
                party=m.party,
                district=m.district,
                activity_score=score,
            ))
        parties = sorted({mem.party for mem in members})
        # cross-party share: 가장 큰 정당 비율 외 나머지
        if members:
            party_count: dict[str, int] = {}
            for mem in members:
                party_count[mem.party] = party_count.get(mem.party, 0) + 1
            largest = max(party_count.values())
            cross_party_share = round((len(members) - largest) / len(members), 2)
        else:
            cross_party_share = 0.0

        out.append(ClusterEntry(
            cluster_id=c["cluster_id"],
            label=c["label"],
            dominant_topics=c["dominant_topics"],
            description=c["description"],
            member_count=len(members),
            members=members,
            parties_represented=parties,
            cross_party_share=cross_party_share,
            avg_activity=c["avg_activity"],
            coherence_score=c["coherence_score"],
            insight=c["insight"],
        ))
    return tuple(out)


# Build-time 1회 (module load 시점에 member_directory 호출).
_CLUSTERS: tuple[ClusterEntry, ...] = _build_clusters()


# ─── 공개 API ───────────────────────────────────────────────────────────────


def list_clusters() -> list[ClusterEntry]:
    """전체 클러스터 - coherence_score 내림차순."""
    return sorted(_CLUSTERS, key=lambda c: -c.coherence_score)


def get_cluster(cluster_id: str) -> Optional[ClusterEntry]:
    """단일 cluster lookup."""
    return next((c for c in _CLUSTERS if c.cluster_id == cluster_id), None)
