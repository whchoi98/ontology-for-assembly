"""합성 Topic 카탈로그 - article·reader·advertisement가 공유하는 foundation.

25개 중립 정책 토픽 사전 정의. 이념 라벨(보수/진보) 절대 미포함 - ADR-0004 Layer 4.

이 카탈로그는 LLM이 자동 추출하는 Topic 노드와 별개로, 합성 데이터 generation에
사용되는 결정적 토픽 풀. 실 데이터에서는 Topic이 LLM 임베딩으로 자동 생성됨.

References:
- spec §4.1 (Topic 클래스)
- ADR-0004 Layer 4 (정치 중립성 - 이념 라벨 금지)
"""
from __future__ import annotations

from dataclasses import dataclass

from data.schemas import Topic


@dataclass(frozen=True)
class TopicSeed:
    """Topic 합성용 시드. 코드용 한 줄 식별."""
    id: str
    name: str
    category: str
    keywords: tuple[str, ...]


# 25개 중립 정책 토픽 - 한국 입법 도메인 흔한 카테고리만.
TOPIC_SEEDS: tuple[TopicSeed, ...] = (
    # 산업·과학기술 (5)
    TopicSeed("topic_ai", "AI 산업 진흥", "산업", ("AI", "인공지능", "산업 진흥")),
    TopicSeed("topic_data", "데이터·개인정보 보호", "법무", ("데이터", "개인정보", "프라이버시")),
    TopicSeed("topic_digital", "디지털 콘텐츠 정책", "문화", ("디지털", "콘텐츠", "플랫폼")),
    TopicSeed("topic_telecom", "통신·방송 정책", "산업", ("통신", "방송", "주파수")),
    TopicSeed("topic_science", "과학기술 혁신", "산업", ("연구개발", "R&D", "혁신")),

    # 경제·재정 (4)
    TopicSeed("topic_finance", "금융 정책", "경제", ("금융", "은행", "투자")),
    TopicSeed("topic_tax", "세제·재정", "경제", ("세금", "재정", "예산")),
    TopicSeed("topic_market", "공정거래·시장", "경제", ("공정거래", "독점", "소비자")),
    TopicSeed("topic_smb", "중소기업·창업", "경제", ("중소기업", "창업", "벤처")),

    # 사회·복지 (5)
    TopicSeed("topic_welfare", "사회복지", "사회", ("복지", "기초생활", "장애인")),
    TopicSeed("topic_health", "보건의료", "사회", ("의료", "건강보험", "공공보건")),
    TopicSeed("topic_youth", "청년 정책", "사회", ("청년", "취업", "주거지원")),
    TopicSeed("topic_housing", "주거 정책", "사회", ("주택", "임대", "부동산")),
    TopicSeed("topic_population", "인구·저출생", "사회", ("저출생", "육아", "보육")),

    # 환경·인프라 (3)
    TopicSeed("topic_environment", "환경·기후", "환경", ("환경", "탄소", "기후변화")),
    TopicSeed("topic_energy", "에너지 전환", "산업", ("에너지", "재생에너지", "전력")),
    TopicSeed("topic_transport", "교통·인프라", "사회", ("교통", "도로", "철도")),

    # 노동·교육 (3)
    TopicSeed("topic_labor", "노동·고용", "사회", ("노동", "고용", "최저임금")),
    TopicSeed("topic_education", "교육 정책", "사회", ("교육", "대학", "공교육")),
    TopicSeed("topic_culture", "문화·체육", "문화", ("문화", "예술", "체육")),

    # 행정·사법 (3)
    TopicSeed("topic_admin", "행정 개혁", "법무", ("행정", "공공기관", "규제개혁")),
    TopicSeed("topic_judicial", "사법 개혁", "법무", ("사법", "법원", "검찰")),
    TopicSeed("topic_local", "지방자치·균형발전", "사회", ("지방자치", "균형발전", "지역")),

    # 안보·외교 (2)
    TopicSeed("topic_defense", "국방·안보", "외교안보", ("국방", "안보", "병역")),
    TopicSeed("topic_diplomacy", "외교", "외교안보", ("외교", "통상", "국제협력")),
)

assert len(TOPIC_SEEDS) == 25, f"Expected 25 topic seeds, got {len(TOPIC_SEEDS)}"


# ID lookup
TOPIC_INDEX: dict[str, TopicSeed] = {t.id: t for t in TOPIC_SEEDS}


def list_topic_ids() -> list[str]:
    """전체 토픽 ID 리스트 (article·reader·advertisement가 샘플링 시 사용)."""
    return [t.id for t in TOPIC_SEEDS]


def list_categories() -> list[str]:
    """카테고리 distinct 리스트."""
    return sorted({t.category for t in TOPIC_SEEDS})


def to_graph_nodes(source: str = "synthetic") -> list[Topic]:
    """25개 Topic 시드를 Pydantic Topic 노드로 변환.

    실 환경에서는 LLM 자동 추출이 Topic을 만들지만, PoC 합성 데모는 이 25개 사전 정의 풀
    사용. 동일 ID로 article·reader·advertisement가 cross-reference 가능.
    """
    return [
        Topic(
            topic_id=t.id,
            name=t.name,
            category=t.category,
            embedding=None,  # 실 환경에서 Cohere embed-v4가 채움
            source=source,
        )
        for t in TOPIC_SEEDS
    ]


def get(topic_id: str) -> TopicSeed | None:
    """ID로 시드 lookup."""
    return TOPIC_INDEX.get(topic_id)
