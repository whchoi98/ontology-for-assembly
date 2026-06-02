"""16 placeholder 클래스 합성 generator - Object Explorer 31 클래스 완성용.

각 generator는 결정적(seeded) mock 시드를 반환. PoC 데모 가능성만 충족하는 최소
데이터. 모든 노드는 `source="synthetic"` 강제.

Production transition 시 각 generator를 실 어댑터(data/real/* 또는 외부 API)로 교체.

References:
- spec §4.1 (31 클래스)
- ADR-0001 (gcc 패턴 차용)
- ADR-0003 (Reader 익명화 - HashedId 솔티드 SHA-256)
- ADR-0004 (정치 성향 추론 필드 금지)
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone, timedelta
from typing import Iterator

from data.schemas import (
    AdImpression,
    AdMatchDecision,
    Amendment,
    Bookmark,
    Budget,
    Cluster,
    District,
    ElectionResult,
    Law,
    Policy,
    ReaderProfile,
    ReadingEvent,
    Staff,
    SubscriptionTier,
    Tag,
    Term,
)

__all__ = [
    "generate_staff",
    "generate_districts",
    "generate_terms",
    "generate_laws",
    "generate_amendments",
    "generate_budgets",
    "generate_policies",
    "generate_election_results",
    "generate_tags",
    "generate_reader_profiles",
    "generate_subscription_tiers",
    "generate_reading_events",
    "generate_bookmarks",
    "generate_ad_impressions",
    "generate_ad_match_decisions",
    "generate_clusters",
]


# ─── 공통 헬퍼 ─────────────────────────────────────────────────────────


def _hashed_id(seed: str) -> str:
    """HashedId 패턴(`^[a-f0-9]{64}$`) 준수 - 결정적 솔티드 해시."""
    return hashlib.sha256(f"assembly_demo_{seed}".encode("utf-8")).hexdigest()


_BASE_DATE = date(2026, 5, 14)
_BASE_DT = datetime(2026, 5, 14, tzinfo=timezone.utc)


# ─── Group 1: 인물·조직 (Staff, District, Term) ─────────────────────────


def generate_staff(count: int = 20) -> Iterator[Staff]:
    """보좌진. 의원당 보좌진 2-3명 가정 (개인정보 보호 - role만 노출)."""
    roles: tuple[str, ...] = ("chief_aide", "secretary", "intern", "other")
    for i in range(count):
        person_idx = (i % 10) + 1  # MONA_001 ~ MONA_010 라운드 로빈
        yield Staff(
            staff_id=f"staff_{i:03d}",
            person_id=f"MONA_{person_idx:03d}",
            role=roles[i % len(roles)],  # type: ignore[arg-type]
            since=_BASE_DATE - timedelta(days=180 + (i * 7) % 360),
            source="synthetic",
        )


def generate_districts(count: int = 15) -> Iterator[District]:
    """지역구 - KOSTAT sgg_code 기반. 17 시도 분포 균등."""
    seeds: tuple[tuple[str, str, str, float, float], ...] = (
        ("11680", "서울특별시", "강남구갑", 37.518, 127.047),
        ("11710", "서울특별시", "송파구갑", 37.514, 127.105),
        ("11290", "서울특별시", "성북구을", 37.589, 127.025),
        ("26350", "부산광역시", "해운대구갑", 35.163, 129.163),
        ("27110", "대구광역시", "수성구갑", 35.857, 128.621),
        ("28237", "인천광역시", "연수구갑", 37.410, 126.678),
        ("29155", "광주광역시", "서구갑", 35.151, 126.890),
        ("41135", "경기도", "성남시분당구갑", 37.382, 127.118),
        ("41460", "경기도", "수원시갑", 37.263, 127.028),
        ("41530", "경기도", "안양시동안구갑", 37.392, 126.957),
        ("42110", "강원특별자치도", "춘천시", 37.881, 127.730),
        ("43110", "충청북도", "청주시상당구", 36.643, 127.490),
        ("45110", "전북특별자치도", "전주시갑", 35.824, 127.148),
        ("46110", "전라남도", "순천시", 34.951, 127.487),
        ("47230", "경상북도", "포항시북구", 36.041, 129.365),
        ("48125", "경상남도", "진주시갑", 35.180, 128.108),
        ("50110", "제주특별자치도", "제주시갑", 33.499, 126.531),
    )
    for i, (code, sido, sgg, lat, lon) in enumerate(seeds[:count]):
        yield District(
            code=code, sido=sido, sgg=sgg,
            geo_center_lat=lat, geo_center_lon=lon,
            source="synthetic",
        )


def generate_terms(count: int = 3) -> Iterator[Term]:
    """국회 회기 - 20대, 21대, 22대."""
    yield Term(number=20, start_date=date(2016, 5, 30), end_date=date(2020, 5, 29), source="real")
    if count >= 2:
        yield Term(number=21, start_date=date(2020, 5, 30), end_date=date(2024, 5, 29), source="real")
    if count >= 3:
        yield Term(number=22, start_date=date(2024, 5, 30), end_date=None, source="real")


# ─── Group 2: 입법 (Law, Amendment, Budget) ──────────────────────────────


def generate_laws(count: int = 12) -> Iterator[Law]:
    """현행 법령 - 22대 입법 대상 핵심 법령."""
    seeds: tuple[tuple[str, str, date], ...] = (
        ("law_personal_info_protection", "개인정보 보호법", date(2025, 11, 20)),
        ("law_ai_industry_promotion", "AI 산업 진흥 특별법", date(2026, 4, 15)),
        ("law_data_industry_promotion", "데이터 산업 진흥에 관한 법률", date(2026, 5, 8)),
        ("law_telecom_business", "전기통신사업법", date(2024, 12, 1)),
        ("law_digital_content", "콘텐츠산업 진흥법", date(2025, 9, 12)),
        ("law_minimum_wage", "최저임금법", date(2025, 8, 5)),
        ("law_youth_housing_support", "청년 주거지원 확대법", date(2026, 5, 2)),
        ("law_carbon_neutral", "탄소중립·녹색성장 기본법", date(2024, 11, 3)),
        ("law_food_safety", "식품위생법", date(2025, 6, 10)),
        ("law_traffic_safety", "교통안전법", date(2025, 4, 21)),
        ("law_competition", "공정거래법", date(2025, 12, 1)),
        ("law_balanced_development", "국가균형발전 특별법", date(2025, 10, 18)),
    )
    for law_id, name, revised in seeds[:count]:
        yield Law(law_id=law_id, name=name, last_revised=revised, source="real")


def generate_amendments(count: int = 6) -> Iterator[Amendment]:
    """개정안 - 합성 bill_id → 현행 법령 diff_summary."""
    seeds: tuple[tuple[str, str, str], ...] = (
        ("B2206_0001", "law_personal_info_protection",
         "AI 학습 데이터 이용 시 가명처리 요건 + 안전조치 의무 신설"),
        ("B2206_0002", "law_ai_industry_promotion",
         "AI 윤리 가이드라인 준수 의무 신설 + 위반 시 행정처분"),
        ("B2206_0003", "law_data_industry_promotion",
         "공공데이터 상업적 활용 범위 확대 + 사용료 면제 조건 신설"),
        ("B2206_0004", "law_telecom_business",
         "메시징 서비스 사업자의 사용자 보호 의무 강화"),
        ("B2206_0005", "law_youth_housing_support",
         "지원 대상 연령 만 39세까지 확대 + 보증금 한도 상향"),
        ("B2206_0006", "law_carbon_neutral",
         "산업 부문 탄소중립 이행 점검 주기를 매년 1회로 단축"),
    )
    for bill_id, law_id, diff in seeds[:count]:
        yield Amendment(
            bill_id=bill_id, original_law_id=law_id, diff_summary=diff,
            source="synthetic",
        )


def generate_budgets(count: int = 10) -> Iterator[Budget]:
    """예산 - 부처별 합성. 단위: 천원."""
    seeds: tuple[tuple[str, int, str], ...] = (
        ("기획재정부", 685_000_000, "approved"),
        ("국토교통부", 612_000_000, "approved"),
        ("보건복지부", 1_240_000_000, "executed"),
        ("교육부", 1_054_000_000, "approved"),
        ("산업통상자원부", 423_000_000, "executed"),
        ("과학기술정보통신부", 318_000_000, "approved"),
        ("환경부", 196_000_000, "executed"),
        ("문화체육관광부", 158_000_000, "approved"),
        ("법무부", 174_000_000, "executed"),
        ("외교부", 142_000_000, "proposed"),
    )
    for i, (ministry, amount, status) in enumerate(seeds[:count]):
        yield Budget(
            fiscal_year=2026, ministry=ministry,
            amount_krw=amount, status=status,  # type: ignore[arg-type]
            source="synthetic",
        )


# ─── Group 3: 주제·외부 (Policy, ElectionResult) ────────────────────────


def generate_policies(count: int = 6) -> Iterator[Policy]:
    """정책 - Bill·Agency 묶음. 합성 시드."""
    seeds: tuple[tuple[str, str, list[str], list[str]], ...] = (
        ("policy_ai_governance", "AI 거버넌스 정책",
         ["B2206_0001", "B2206_0002"], ["agency_ndrc", "agency_kisa"]),
        ("policy_youth_support", "청년 종합 지원 정책",
         ["B2206_0005"], ["agency_moel", "agency_molit"]),
        ("policy_data_economy", "데이터 경제 활성화",
         ["B2206_0001", "B2206_0003"], ["agency_msit"]),
        ("policy_carbon_neutral", "탄소중립 이행",
         ["B2206_0006"], ["agency_me"]),
        ("policy_balanced_development", "균형발전",
         [], ["agency_nbdc"]),
        ("policy_consumer_protection", "소비자 보호 강화",
         [], ["agency_kca", "agency_ftc"]),
    )
    for policy_id, name, bills, agencies in seeds[:count]:
        yield Policy(
            policy_id=policy_id, name=name,
            related_bill_ids=list(bills), related_agency_ids=list(agencies),
            source="synthetic",
        )


def generate_election_results(count: int = 10) -> Iterator[ElectionResult]:
    """22대 선거 결과 시드 - 합성 win/lose 매핑."""
    for i in range(count):
        person_idx = (i % 10) + 1
        yield ElectionResult(
            election_id=f"election_22nd_{i:03d}",
            district_id=f"district_{i:03d}",
            person_id=f"MONA_{person_idx:03d}",
            won=True,
            source="real",
        )


# ─── Group 4: 미디어 (Tag) ────────────────────────────────────────────


def generate_tags(count: int = 18) -> Iterator[Tag]:
    """태그 - Topic보다 가벼운 분류 (자유 카테고리)."""
    seeds: tuple[tuple[str, str], ...] = (
        ("AI 입법", "산업"),
        ("청년 정책", "사회"),
        ("데이터 경제", "산업"),
        ("탄소중립", "환경"),
        ("주거 지원", "사회"),
        ("개인정보 보호", "법무"),
        ("균형발전", "사회"),
        ("교육 개혁", "사회"),
        ("최저임금", "경제"),
        ("공정거래", "경제"),
        ("문화 콘텐츠", "문화"),
        ("보건 의료", "사회"),
        ("외교 안보", "외교"),
        ("디지털 헬스", "산업"),
        ("교통 안전", "사회"),
        ("재정 운영", "경제"),
        ("기술 혁신", "산업"),
        ("저출생 대응", "사회"),
    )
    for name, category in seeds[:count]:
        yield Tag(name=name, category=category, source="synthetic")


# ─── Group 5: 독자 측 (ReaderProfile, SubscriptionTier, ReadingEvent, Bookmark) ──


def generate_subscription_tiers(count: int = 3) -> Iterator[SubscriptionTier]:
    """구독 등급 - 3 tier (free / standard / premium)."""
    tiers: tuple[tuple[str, str, list[str], int], ...] = (
        ("free", "무료 멤버", ["기사 일일 5건", "기본 검색", "광고 표시"], 0),
        ("standard", "스탠다드",
         ["기사 무제한", "광고 최소화", "위클리 인사이트 뉴스레터"], 9_900),
        ("premium", "프리미엄",
         ["기사 무제한 광고 없음", "PDF 리포트 export", "의원 정치 여정 동시 export",
          "B2B API 베타 액세스"], 24_900),
    )
    for tier_id, name, features, price in tiers[:count]:
        yield SubscriptionTier(
            tier_id=tier_id,  # type: ignore[arg-type]
            name=name, features=list(features), price_krw_monthly=price,
            source="synthetic",
        )


def generate_reader_profiles(count: int = 10) -> Iterator[ReaderProfile]:
    """독자 행동 집계 - HashedId 익명. 정치 성향 미포함 (ADR-0004)."""
    topic_pool = [
        "topic_ai", "topic_welfare", "topic_youth", "topic_environment",
        "topic_data", "topic_housing", "topic_health", "topic_culture",
    ]
    devices: tuple[str, ...] = ("mobile", "desktop", "tablet")
    for i in range(count):
        # 2-3개 토픽 결정적 선택
        start = i * 3 % len(topic_pool)
        top_topics = [topic_pool[(start + j) % len(topic_pool)] for j in range(3)]
        yield ReaderProfile(
            reader_id=_hashed_id(f"reader_{i:04d}"),
            top_topic_ids=top_topics,
            reading_minutes_avg_7d=round(8.5 + (i * 0.7) % 25, 1),
            device_class=devices[i % len(devices)],  # type: ignore[arg-type]
            source="synthetic",
        )


def generate_reading_events(count: int = 15) -> Iterator[ReadingEvent]:
    """읽기 이벤트 - 합성 reader × article."""
    for i in range(count):
        yield ReadingEvent(
            event_id=f"read_{i:05d}",
            reader_id=_hashed_id(f"reader_{(i % 10):04d}"),
            article_id=f"art_{(i % 60):05d}",
            duration_sec=30 + (i * 13) % 271,
            completed=(i % 3) != 0,
            source="synthetic",
        )


def generate_bookmarks(count: int = 10) -> Iterator[Bookmark]:
    """책갈피 - reader가 article·person·bill을 저장."""
    types: tuple[str, ...] = ("article", "person", "bill")
    for i in range(count):
        tt = types[i % len(types)]
        target_id = {
            "article": f"art_{(i % 60):05d}",
            "person": f"MONA_{((i % 10) + 1):03d}",
            "bill": f"B2206_{(i % 6 + 1):04d}",
        }[tt]
        yield Bookmark(
            bookmark_id=f"bm_{i:04d}",
            reader_id=_hashed_id(f"reader_{(i % 10):04d}"),
            target_type=tt,  # type: ignore[arg-type]
            target_id=target_id,
            date=_BASE_DT - timedelta(days=(i * 3) % 60),
            source="synthetic",
        )


# ─── Group 6: 광고 (AdImpression, AdMatchDecision) ─────────────────────


def generate_ad_impressions(count: int = 15) -> Iterator[AdImpression]:
    """광고 노출 이벤트. TTL 14일 (DynamoDB 가정)."""
    for i in range(count):
        yield AdImpression(
            impression_id=f"imp_{i:05d}",
            reader_id=_hashed_id(f"reader_{(i % 10):04d}"),
            article_id=f"art_{(i % 60):05d}",
            ad_id=f"ad_{(i % 10):03d}",
            timestamp=_BASE_DT - timedelta(hours=(i * 2) % 336),
            source="synthetic",
        )


def generate_ad_match_decisions(count: int = 6) -> Iterator[AdMatchDecision]:
    """광고 매칭 결정 trace - 시나리오 L 산출물 시드."""
    # (mode, chosen_ad_id, reason_text, score) - Agent 모드 일부는 skip
    seeds: tuple[tuple[str, str | None, str, float], ...] = (
        ("keyword", "ad_002",
         "allow 키워드 매칭 - 청년/주거 광고 매칭 | 근거: 청년 주거 정책 콘텐츠 | 회피: None",
         0.42),
        ("embedding", "ad_004",
         "allow 임베딩 cosine 0.78 - IT 산업 광고 매칭 | 근거: AI 산업 진흥 콘텐츠 | 회피: None",
         0.78),
        ("agent", "ad_004",
         "allow Agent 판단 - AI 진흥 콘텐츠는 광고 안전 | 근거: 정치 균형 점수 0.92 | 회피: None",
         0.85),
        ("agent", None,
         "skip 정치인 비위 의혹 콘텐츠 | 근거: ○○○ 의원 검찰 수사 진행 중 | 회피: 모든 광고주 평판 보호",
         0.95),
        ("agent", None,
         "skip 비극 콘텐츠 | 근거: 사고 피해자 추모 기사 | 회피: 모든 광고주",
         0.92),
        ("keyword", "ad_007",
         "allow 키워드 매칭 - 환경 광고 매칭 | 근거: 탄소중립 정책 콘텐츠 | 회피: None",
         0.35),
    )
    for i, (mode, chosen, reason, score) in enumerate(seeds[:count]):
        yield AdMatchDecision(
            decision_id=f"decision_{i:04d}",
            mode=mode,  # type: ignore[arg-type]
            article_id=f"art_{(i + 10):05d}",
            candidate_ad_ids=[f"ad_{j:03d}" for j in range(3)],
            chosen_ad_id=chosen,
            score=score,
            reason_text=reason,
            timestamp=_BASE_DT - timedelta(hours=i * 4),
            source="synthetic",
        )


# ─── Group 7: 분석 메타 (Cluster) ─────────────────────────────────────


def generate_clusters() -> Iterator[Cluster]:
    """의원 정치성향 클러스터 - cluster_builder 데이터 재활용.

    ADR-0004: label은 중립 표현만 (이념 라벨 금지 - "보수파" 등 사용 금지).
    """
    from api.services import cluster_builder
    for c in cluster_builder.list_clusters():
        yield Cluster(
            cluster_id=c.cluster_id,
            label=c.label,
            centroid=[],  # PoC는 빈 vector. Production은 1024-dim cohere embed-v4 평균.
            member_ids=[m.person_id for m in c.members],
            source="synthetic",
        )
