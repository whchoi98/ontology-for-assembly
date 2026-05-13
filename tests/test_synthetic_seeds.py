"""data.synthetic.seeds PDF 시그니처 시드 검증.

검증:
- 7개 entity 시드 모두 Pydantic 검증 통과
- 시드 ID 상수 - 검증 스크립트가 참조 가능
- AdMatchDecision skip 결정의 reason_text는 ADR-0004 Layer 6 근거 포함
- Cluster.label은 중립 추상 (이념명 미포함)
- Article 본문 (비위 의혹)도 political_balance_score 알람 trigger
  → seeds.py는 의도적으로 alarm 영역 - 이것이 시나리오 L 데모 시드인 이유
"""
from __future__ import annotations
import pytest

from data.synthetic import seeds
from data.schemas import (
    AdMatchDecision, Article, Bill, Cluster, Person, Statement, Vote,
)


def test_seed_constants_defined():
    """시드 ID 상수 정의됨 - 검증·런북에서 참조."""
    assert seeds.DEMO_HUB_PERSON_ID.startswith("MONA_DEMO_")
    assert seeds.DEMO_AI_BILL_ID.startswith("DEMO_AI_BILL_")
    assert seeds.DEMO_TRAGIC_ARTICLE_ID.startswith("art_DEMO_")
    assert seeds.DEMO_SWING_VOTE_ID.startswith("V_DEMO_")


def test_seed_demo_nodes_returns_seven_entity_types():
    nodes = seeds.seed_demo_nodes()
    expected_keys = {"persons", "bills", "articles", "votes", "statements",
                     "ad_decisions", "clusters"}
    assert set(nodes.keys()) == expected_keys


def test_seed_nodes_pydantic_valid():
    """모든 시드 노드가 Pydantic 검증 통과."""
    nodes = seeds.seed_demo_nodes()
    assert all(isinstance(n, Person) for n in nodes["persons"])
    assert all(isinstance(n, Bill) for n in nodes["bills"])
    assert all(isinstance(n, Article) for n in nodes["articles"])
    assert all(isinstance(n, Vote) for n in nodes["votes"])
    assert all(isinstance(n, Statement) for n in nodes["statements"])
    assert all(isinstance(n, AdMatchDecision) for n in nodes["ad_decisions"])
    assert all(isinstance(n, Cluster) for n in nodes["clusters"])


def test_hub_person_marked_synthetic():
    nodes = seeds.seed_demo_nodes()
    hub = nodes["persons"][0]
    assert hub.assembly_id == seeds.DEMO_HUB_PERSON_ID
    assert hub.source == "synthetic"
    assert "시연용" in hub.name  # 실 인물과 혼동 방지


def test_ai_bill_proposer_is_hub():
    """AI 의안의 대표발의자는 허브 의원 (Scenario M 일관성)."""
    nodes = seeds.seed_demo_nodes()
    bill = nodes["bills"][0]
    assert bill.proposer_id == seeds.DEMO_HUB_PERSON_ID
    assert bill.bill_id == seeds.DEMO_AI_BILL_ID
    assert bill.status == "passed"


def test_tragic_article_has_judicial_topic():
    """비위 의혹 콘텐츠는 judicial 토픽 - Agent 광고 거절 trigger 조건."""
    nodes = seeds.seed_demo_nodes()
    article = nodes["articles"][0]
    assert article.article_id == seeds.DEMO_TRAGIC_ARTICLE_ID
    assert "topic_judicial" in article.topic_ids


def test_ad_skip_decision_chosen_is_none():
    """광고 거절 결정의 chosen_ad_id는 None (시나리오 L 핵심)."""
    nodes = seeds.seed_demo_nodes()
    decision = nodes["ad_decisions"][0]
    assert decision.chosen_ad_id is None
    assert decision.score == 0.0
    assert decision.mode == "agent"


def test_ad_skip_reason_text_references_adr():
    """광고 거절 reason_text는 ADR-0004 Layer 6 근거 포함."""
    nodes = seeds.seed_demo_nodes()
    decision = nodes["ad_decisions"][0]
    reason = decision.reason_text
    # 근거가 명시되어야 audit 자료로 가치 있음
    assert "skip" in reason or "거절" in reason
    assert "비위" in reason or "scandal" in reason.lower() or "수사" in reason
    assert "Layer" in reason or "ADR" in reason
    assert "회피" in reason


def test_cluster_label_neutral_no_ideology():
    """클러스터 라벨은 중립 추상 - 이념명 미포함."""
    nodes = seeds.seed_demo_nodes()
    cluster = nodes["clusters"][0]
    forbidden = {"보수", "진보", "좌파", "우파", "중도"}
    for label in forbidden:
        assert label not in cluster.label, f"이념 라벨 포함: {cluster.label}"


def test_cluster_members_include_hub_person():
    """클러스터 멤버에 허브 의원 포함 (Scenario E 일관성)."""
    nodes = seeds.seed_demo_nodes()
    cluster = nodes["clusters"][0]
    assert seeds.DEMO_HUB_PERSON_ID in cluster.member_ids


def test_swing_vote_references_demo_ai_bill():
    """시나리오 K 표결 시드가 DEMO_AI_BILL 참조 (cross-reference 일관성)."""
    nodes = seeds.seed_demo_nodes()
    vote = nodes["votes"][0]
    assert vote.bill_id == seeds.DEMO_AI_BILL_ID


def test_hub_statement_references_hub_person():
    """허브 의원 발언 시드가 정확한 person_id 사용 (Scenario M)."""
    nodes = seeds.seed_demo_nodes()
    stmt = nodes["statements"][0]
    assert stmt.person_id == seeds.DEMO_HUB_PERSON_ID


def test_iter_demo_node_ids_yields_seven():
    """iter_demo_node_ids는 7개 entity ID yield (검증 스크립트용)."""
    ids = list(seeds.iter_demo_node_ids())
    assert len(ids) == 7
    # 각 entity마다 정확히 하나씩
    entity_types = {entity for entity, _ in ids}
    assert entity_types == {
        "persons", "bills", "articles", "votes", "statements", "ad_decisions", "clusters"
    }


def test_demo_seeds_deterministic_across_calls():
    """seed_demo_nodes는 동일 결과 반환 (시연 안전성)."""
    a = seeds.seed_demo_nodes()
    b = seeds.seed_demo_nodes()
    # 같은 ID·이름이어야 함
    assert a["persons"][0].assembly_id == b["persons"][0].assembly_id
    assert a["bills"][0].bill_id == b["bills"][0].bill_id
