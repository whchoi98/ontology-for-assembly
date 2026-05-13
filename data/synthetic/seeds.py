"""PDF 시그니처 시연 시드 - 시나리오 B·K·L·M의 핵심 데모 자산.

이 시드들은 라이브 시연 중 *반드시 동일하게 등장*해야 하는 결정적 데이터:
- B (3-stage chat): 허브 의원 + AI 관련 의안 + 공동발의 네트워크
- K (표결 이상치): 당론 이탈 패턴 (PDF 3페이지 시그니처)
- L (광고 매칭): 정치인 비위 의혹 콘텐츠 → Agent 광고 거절 trigger
- M (의원 정치 여정): 1인 의원의 발의·표결·발언 통합 timeline

랜덤 generator의 출력에 의존하지 않고 고정 seed로 보장. 시연 안전성 + 백업 영상
재현성의 핵심.

References:
- spec §3.1 (시나리오 카탈로그)·§3.3 (시나리오 B 상세)·§3.4 (시나리오 L)
- ADR-0004 Layer 6 (광고 매칭 거버넌스)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterator

from data.schemas import (
    AdMatchDecision,
    Article,
    Bill,
    Cluster,
    Person,
    Statement,
    Vote,
)

__all__ = [
    "DEMO_HUB_PERSON_ID",
    "DEMO_AI_BILL_ID",
    "DEMO_TRAGIC_ARTICLE_ID",
    "DEMO_SWING_VOTE_ID",
    "seed_demo_nodes",
]


# ─── 시연 자산 ID (테스트·검증·런북에서 참조) ──────────────────────────────

# 시나리오 B 허브 의원 (3-stage chat 데모의 핵심 인물)
DEMO_HUB_PERSON_ID = "MONA_DEMO_HUB"

# 시나리오 B/M AI 입법 의안 (가장 많이 보일 의안)
DEMO_AI_BILL_ID = "DEMO_AI_BILL_001"

# 시나리오 L 비위 의혹 콘텐츠 (Agent 광고 거절 trigger)
DEMO_TRAGIC_ARTICLE_ID = "art_DEMO_TRAGIC_001"

# 시나리오 K 당론 이탈 표결 (이상치 탐지 데모)
DEMO_SWING_VOTE_ID = "V_DEMO_SWING_2026-04-22"


# ─── 시드 노드 정의 ────────────────────────────────────────────────────────

def _demo_hub_person() -> Person:
    """시나리오 B의 '공동발의 허브' 의원.

    양당 의원과 모두 연결된 정파 무관 허브. 데모에서 3-stage chat이 이 인물을
    중심으로 네트워크 분석을 수행.
    """
    return Person(
        assembly_id=DEMO_HUB_PERSON_ID,
        name="김민주 (시연용)",   # 합성 인물 명시
        term=22,
        district_id="11110",       # 서울 강남구갑
        party_id="더불어민주당",
        profile_image_url=None,
        election_district_type="constituency",
        source="synthetic",
    )


def _demo_ai_bill() -> Bill:
    """AI 산업 진흥 의안 - 시나리오 B/C/E/M 데모 중심 의안.

    상태: passed (양당 모두 찬성한 협력적 의제).
    """
    return Bill(
        bill_id=DEMO_AI_BILL_ID,
        title="AI 산업 진흥 종합 대책 특별법 (시연용)",
        proposed_date=date(2026, 3, 15),
        status="passed",
        category="과학기술정보방송통신위원회",
        proposer_id=DEMO_HUB_PERSON_ID,
        summary_text=(
            "인공지능 산업 진흥과 활용 촉진을 위한 종합 대책. "
            "산업 진흥·인재 양성·윤리 가이드라인을 포함하는 종합 입법."
        ),
        full_text_url=None,
        source="synthetic",
    )


def _demo_tragic_article() -> Article:
    """시나리오 L에서 Agent가 '광고 거절' 판단해야 할 콘텐츠.

    내용: 정치인 비위 의혹 + 검찰 수사 진행 중. 광고 매칭 시
    Agent 모드의 `chosen_ad_id=None` 결정을 trigger해야 함 (ADR-0004 Layer 6).

    NOTE: 실 인물·실 사건 가리키지 않음. 시연용 가공 시나리오.
    """
    return Article(
        article_id=DEMO_TRAGIC_ARTICLE_ID,
        title="○○○ 의원 위증 의혹 - 검찰 수사 진행 중",
        content=(
            "○○○ 의원에 대한 위증 의혹이 제기된 가운데 검찰 수사가 진행 중이다. "
            "관련 사실관계는 아직 확정되지 않았으며 의혹 단계임을 명시한다 "
            "(출처: 합성 시연 시나리오). "
            "본 콘텐츠는 광고 매칭 거버넌스 데모용으로, Agent 판단 모드가 광고 노출을 "
            "자동 생략하는 reasoning trace를 보여주기 위해 설계되었다."
        ),
        published_at=datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc),
        author="author_DEMO",
        topic_ids=["topic_judicial"],
        referenced_person_ids=[DEMO_HUB_PERSON_ID],
        referenced_bill_ids=[],
        source="synthetic",
    )


def _demo_swing_vote() -> Vote:
    """시나리오 K 당론 이탈 표결 시드.

    한 의안에서 양당 일치율이 평소보다 크게 다른 패턴 - 이상치 탐지 데모.
    """
    return Vote(
        vote_id=DEMO_SWING_VOTE_ID,
        bill_id=DEMO_AI_BILL_ID,
        date=date(2026, 4, 22),
        result="passed",
        attendance_count=287,
        source="synthetic",
    )


def _demo_agentic_ad_skip_decision() -> AdMatchDecision:
    """시나리오 L의 핵심 trace - Agent가 광고를 거절한 결정 시드.

    DEMO_TRAGIC_ARTICLE에 대해 Agent 판단 모드가 비위 의혹 콘텐츠임을 인식하고
    광고 노출을 생략한 결정. 운영 콘솔 트레이스 패널 데모.
    """
    return AdMatchDecision(
        decision_id="dec_DEMO_SKIP_001",
        mode="agent",
        article_id=DEMO_TRAGIC_ARTICLE_ID,
        candidate_ad_ids=["ad_0001", "ad_0042", "ad_0123"],
        chosen_ad_id=None,            # 광고 생략 결정
        score=0.0,
        reason_text=(
            "skip 정치인 비위 의혹 콘텐츠 | "
            "근거: 검찰 수사 진행 중 + 사실관계 미확정 | "
            "회피: 모든 광고주 평판 보호 (ADR-0004 Layer 6 trigger)"
        ),
        timestamp=datetime(2026, 5, 10, 9, 1, tzinfo=timezone.utc),
        source="synthetic",
    )


def _demo_hub_journey_statement() -> Statement:
    """시나리오 M 의원 정치 여정 시드 - 허브 의원의 본회의 발언."""
    return Statement(
        statement_id="stmt_DEMO_HUB_001",
        person_id=DEMO_HUB_PERSON_ID,
        session_id="sess_DEMO_PLENARY_001",
        date=date(2026, 4, 22),
        content=(
            "AI 산업 진흥 종합 대책 특별법안에 대해 발언드리겠습니다. "
            "본 법안은 양당 의원 다수의 공동발의로 추진되어 왔으며 "
            "산업 진흥과 윤리 가이드라인 양 측면을 모두 포함합니다."
        ),
        sentiment=0.2,                  # 중립~약한 긍정
        topics=["topic_ai", "topic_data"],
        source="synthetic",
    )


def _demo_cluster_label() -> Cluster:
    """시나리오 E 클러스터 라벨 시드 - 중립 추상 명만 사용."""
    return Cluster(
        cluster_id="cluster_DEMO_INNOVATION",
        label="혁신 입법 다수파",         # 이념명 금지 - 중립 추상
        centroid=[],                     # 실 환경에서 임베딩 평균
        member_ids=[DEMO_HUB_PERSON_ID, "MONA_001", "MONA_007", "MONA_009"],
        source="synthetic",
    )


# ─── 일괄 추출 ──────────────────────────────────────────────────────────────

def seed_demo_nodes() -> dict[str, list]:
    """모든 데모 시드를 entity별 dict로 반환.

    load.py 또는 verification 스크립트가 이 함수를 호출해 합성 데이터셋에 시드를
    덧붙임 / 검증.

    Returns:
        {
          "persons": [...],
          "bills": [...],
          "articles": [...],
          "votes": [...],
          "statements": [...],
          "ad_decisions": [...],
          "clusters": [...],
        }
    """
    return {
        "persons": [_demo_hub_person()],
        "bills": [_demo_ai_bill()],
        "articles": [_demo_tragic_article()],
        "votes": [_demo_swing_vote()],
        "statements": [_demo_hub_journey_statement()],
        "ad_decisions": [_demo_agentic_ad_skip_decision()],
        "clusters": [_demo_cluster_label()],
    }


def iter_demo_node_ids() -> Iterator[tuple[str, str]]:
    """모든 데모 시드의 (entity_type, id) iterator - 검증 스크립트용."""
    seeds = seed_demo_nodes()
    for entity, nodes in seeds.items():
        for node in nodes:
            # Pydantic 모델의 첫 ID 속성 추출 (예: assembly_id, bill_id, ...)
            for attr in ("assembly_id", "bill_id", "article_id", "vote_id",
                         "statement_id", "decision_id", "cluster_id"):
                if hasattr(node, attr):
                    yield entity, getattr(node, attr)
                    break
