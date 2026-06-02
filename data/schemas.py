"""31-class graph node SSOT for ontology-for-assembly.

Pydantic v2 모델. 모든 노드는 GraphNode base를 상속하여 `source` 태깅을 강제한다
(DataSourceBadge 노출에 사용). `ontology/classes/*.yaml`은 이 SSOT에서 파생되는
사람용 카탈로그.

Class groups:
- 인물·조직 (6): Person, Party, Staff, Committee, District, Term
- 입법 (7):     Bill, Law, Amendment, Vote, Statement, Session, Budget
- 주제·외부 (6): Topic, Policy, Agency, ElectionResult, PollResult, SocialSignal
- 미디어 (2):   Article, Tag
- 독자 측 (5):  Reader, ReaderProfile, SubscriptionTier, ReadingEvent, Bookmark
- 광고 (4):     Advertisement, AdInventory, AdImpression, AdMatchDecision
- 분석 (1):     Cluster

Persona는 코드 SSOT (api.services.persona) - 그래프 노드 아님.

References:
- ADR-0002 (six-persona design)
- ADR-0003 (customer-facing extension - Reader 익명화)
- ADR-0004 (political neutrality - Layer 4 금지 필드)
- spec §4 클래스 카탈로그
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# ─── 공통 타입 ───────────────────────────────────────────────────────────────

Source = Literal["real", "synthetic", "external"]

# 솔티드 SHA-256 해시 ID (Reader 익명화 - ADR-0003).
# 64자 hex만 허용 - 쿠키·이메일 원본 저장 시 정규식 fail.
HashedId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class GraphNode(BaseModel):
    """모든 Neptune 노드의 base.

    - `source` 필드 필수 - DataSourceBadge UI 노출에 사용.
    - `extra="forbid"` - 정치 성향 추론 필드 등 미정의 속성 차단.
    - `str_strip_whitespace=True` - 공백 정규화.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: Source


# ─── Group 1: 인물·조직 (6) ──────────────────────────────────────────────────

class Person(GraphNode):
    """국회의원. 국회 OpenAPI /member 매핑.

    의도적 미포함 (ADR-0004 Layer 4): political_leaning, political_loyalty_score,
    party_attack_intent. CI grep job이 추가를 차단.
    """
    assembly_id: str       # MONA_CD
    name: str
    term: int              # 회기 (21, 22, ...)
    district_id: Optional[str] = None
    party_id: Optional[str] = None
    profile_image_url: Optional[str] = None
    election_district_type: Optional[Literal["constituency", "proportional"]] = None  # 지역구/비례


class Party(GraphNode):
    """정당.

    `name`은 정식 등록명만. 약칭·별명 금지 (`ontology/mappings/party_canonical_names.yaml`).
    `ideology_tag`(보수/진보 등) 필드 의도적 미포함 - ADR-0004 정치 중립성.
    """
    party_id: str
    name: str
    founded_date: Optional[date] = None


class Staff(GraphNode):
    """보좌진. 개인정보 보호상 person_id와 role만 보유."""
    staff_id: str
    person_id: str
    role: Literal["chief_aide", "secretary", "intern", "other"]
    since: Optional[date] = None


class Committee(GraphNode):
    """위원회. 국회 OpenAPI /committee 매핑."""
    committee_id: str
    name: str
    type: Literal["standing", "special", "permanent"]
    chair_person_id: Optional[str] = None


class District(GraphNode):
    """지역구. KOSTAT 행정구역코드(sgg_code) 기반."""
    code: str              # KOSTAT sgg_code
    sido: str
    sgg: str
    geo_center_lat: Optional[float] = None
    geo_center_lon: Optional[float] = None


class Term(GraphNode):
    """회기."""
    number: int            # 21, 22, ...
    start_date: date
    end_date: Optional[date] = None


# ─── Group 2: 입법 (7) ────────────────────────────────────────────────────────

BillStatus = Literal[
    "proposed",        # 발의
    "in_committee",    # 상임위 심사 중
    "in_plenary",      # 본회의 상정
    "passed",          # 가결
    "rejected",        # 부결
    "withdrawn",       # 철회
]


class Bill(GraphNode):
    """의안. 국회 OpenAPI /bill 매핑."""
    bill_id: str
    title: str
    proposed_date: date
    status: BillStatus
    category: Optional[str] = None
    proposer_id: Optional[str] = None        # 대표발의자 assembly_id (RST_MONA_CD)
    summary_text: Optional[str] = None
    full_text_url: Optional[str] = None
    # 국회 OpenAPI 보강 필드 (Phase 4b)
    bill_no: Optional[str] = None            # BILL_NO (의안 번호, 예: "2219026")
    lead_proposer_name: Optional[str] = None # RST_PROPOSER (대표 발의자 이름)
    co_proposer_ids: list[str] = Field(default_factory=list)   # PUBL_MONA_CD parse
    co_proposer_names: list[str] = Field(default_factory=list) # PUBL_PROPOSER parse
    co_proposer_count: int = 0


class Law(GraphNode):
    """현행 법령."""
    law_id: str
    name: str
    last_revised: Optional[date] = None


class Amendment(GraphNode):
    """개정안. Bill의 한 종류로 모델링."""
    bill_id: str
    original_law_id: str
    diff_summary: Optional[str] = None


VoteResult = Literal["passed", "rejected", "withdrawn"]


class Vote(GraphNode):
    """표결 이벤트. 의안 1건당 0~N개."""
    vote_id: str
    bill_id: str
    date: date
    result: VoteResult
    attendance_count: int
    # 국회 OpenAPI 집계 필드 (Phase 4b: nkalemivaqmoibxro)
    bill_no: Optional[str] = None
    bill_name: Optional[str] = None
    bill_kind: Optional[str] = None     # "결산", "법률안", "결의안" 등
    committee_name: Optional[str] = None
    yes_count: int = 0
    no_count: int = 0
    blank_count: int = 0
    link_url: Optional[str] = None


# 개별 의원의 선택 (관계 속성으로 사용).
VoteChoice = Literal["yes", "no", "abstain", "absent"]


class Statement(GraphNode):
    """발언. 회의록 텍스트 단위."""
    statement_id: str
    person_id: str
    session_id: str
    date: date
    content: str
    sentiment: Optional[float] = Field(default=None, ge=-1.0, le=1.0)  # LLM 추론
    topics: list[str] = Field(default_factory=list)  # Topic ID list


class Session(GraphNode):
    """회의 (본회의/상임위)."""
    session_id: str
    type: Literal["plenary", "committee"]
    date: date
    committee_id: Optional[str] = None


class Budget(GraphNode):
    """예산."""
    fiscal_year: int
    ministry: str
    amount_krw: int                  # 단위: 천원
    status: Literal["proposed", "approved", "executed"]


# ─── Group 3: 주제·외부 (6) ──────────────────────────────────────────────────

class Topic(GraphNode):
    """LLM 자동 추출 토픽. Cohere embed-v4 임베딩 포함."""
    topic_id: str
    name: str
    category: Optional[str] = None
    embedding: Optional[list[float]] = None  # 1024-dim cohere embed-v4


class Policy(GraphNode):
    """정책. 다수 Bill·Agency를 묶는 추상."""
    policy_id: str
    name: str
    related_bill_ids: list[str] = Field(default_factory=list)
    related_agency_ids: list[str] = Field(default_factory=list)


class Agency(GraphNode):
    """국정감사 대상 기관."""
    agency_id: str
    name: str
    type: Literal["government", "public_enterprise", "constitutional_organ"]


class ElectionResult(GraphNode):
    """선거 결과."""
    election_id: str
    district_id: str
    person_id: str
    won: bool


class PollResult(GraphNode):
    """여론조사 결과.

    `breakdown`은 정당명·이슈명별 비율(0-1). 정치 성향 추론·예측 금지 (ADR-0004).
    """
    poll_id: str
    pollster: str
    date: date
    topic: str
    sample_size: int
    breakdown: dict[str, float] = Field(default_factory=dict)


SocialSignalSourceType = Literal["news", "sns_twitter", "sns_facebook", "blog"]


class SocialSignal(GraphNode):
    """SNS·뉴스 신호 (시나리오 J 외부 신호 융합)."""
    signal_id: str
    source_url: str
    source_type: SocialSignalSourceType
    date: datetime
    sentiment: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    topic_ids: list[str] = Field(default_factory=list)


# ─── Group 4: 미디어 (2) ─────────────────────────────────────────────────────

class Article(GraphNode):
    """기사 (합성 ~2,000개)."""
    article_id: str
    title: str
    content: str
    published_at: datetime
    author: Optional[str] = None
    topic_ids: list[str] = Field(default_factory=list)
    referenced_person_ids: list[str] = Field(default_factory=list)
    referenced_bill_ids: list[str] = Field(default_factory=list)


class Tag(GraphNode):
    """태그. Topic보다 가벼운 분류."""
    name: str
    category: Optional[str] = None


# ─── Group 5: 독자 측 (5) — ADR-0003 (B2C 신규) ─────────────────────────────

ReaderTier = Literal["anonymous", "free", "paid"]


class Reader(GraphNode):
    """독자 (B2C). 익명성 가드 - ADR-0004 Layer 4.

    절대 추가 금지 필드 (CI 정치 중립성 가드가 차단):
    - political_leaning
    - political_loyalty_score
    - bias_label
    - party_attack_intent

    IP·UA·정확 GPS·광고ID(IDFA/AAID)·종교·건강 정보 절대 저장 금지.
    `region`은 시도 단위만 (sgg 이상 정밀도 금지).
    """
    reader_id: HashedId            # 솔티드 SHA-256만. 쿠키 원본 절대 저장 금지.
    tier: ReaderTier
    interests: list[str] = Field(default_factory=list)  # Topic ID list
    region: Optional[str] = None   # 시도 단위만
    since: datetime                # 가입/첫 방문 시점만


class ReaderProfile(GraphNode):
    """독자 행동 집계. 정치 성향 추론 절대 금지 (ADR-0004 Layer 4)."""
    reader_id: HashedId
    top_topic_ids: list[str] = Field(default_factory=list)
    reading_minutes_avg_7d: float = 0.0
    device_class: Optional[Literal["mobile", "desktop", "tablet"]] = None


class SubscriptionTier(GraphNode):
    """구독 등급."""
    tier_id: Literal["free", "standard", "premium"]
    name: str
    features: list[str] = Field(default_factory=list)
    price_krw_monthly: int = 0


class ReadingEvent(GraphNode):
    """읽기 이벤트."""
    event_id: str
    reader_id: HashedId
    article_id: str
    duration_sec: int
    completed: bool


class Bookmark(GraphNode):
    """책갈피."""
    bookmark_id: str
    reader_id: HashedId
    target_type: Literal["article", "person", "bill"]
    target_id: str
    date: datetime


# ─── Group 6: 광고 (4) — 시나리오 L ───────────────────────────────────────────

class Advertisement(GraphNode):
    """광고."""
    ad_id: str
    advertiser: str
    category: str
    content_summary: str
    # 광고주가 명시한 노출 회피 토픽 (예: 자사 경쟁사 분야, 정치 민감 이슈).
    avoid_topics: list[str] = Field(default_factory=list)


class AdInventory(GraphNode):
    """광고 인벤토리."""
    inventory_id: str
    ad_id: str
    budget_krw: int
    period_start: date
    period_end: date
    target_personas: list[str] = Field(default_factory=list)


class AdImpression(GraphNode):
    """광고 노출 이벤트.

    TTL 14일 (DynamoDB). reader_id는 항상 솔티드 해시.
    """
    impression_id: str
    reader_id: HashedId
    article_id: str
    ad_id: str
    timestamp: datetime


AdMatchMode = Literal["keyword", "embedding", "agent"]


class AdMatchDecision(GraphNode):
    """광고 매칭 결정 trace. 시나리오 L 핵심 산출물 + 운영 감사 자료.

    `chosen_ad_id is None` = 광고 노출 생략 결정. Agent 모드에서 비극·정치인 비위·
    미성년 피해자 콘텐츠에 자동 발생 (ADR-0004 Layer 6).

    `reason_text` 형식 권장 (Agent 모드):
        "[allow|skip] <한 줄 결정> | 근거: <콘텐츠 토픽 요약> | 회피: <회피된 광고주 또는 None>"
    예시:
        "skip 정치인 비위 의혹 콘텐츠 | 근거: ○○○ 의원 검찰 수사 진행 중 | 회피: 모든 광고주 평판 보호"
    """
    decision_id: str
    mode: AdMatchMode
    article_id: str
    candidate_ad_ids: list[str] = Field(default_factory=list)
    chosen_ad_id: Optional[str] = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_text: str
    timestamp: datetime


# ─── Group 7: 분석 메타 (1) ──────────────────────────────────────────────────

class Cluster(GraphNode):
    """의원 정치성향 클러스터. KMeans + LLM 라벨링 (시나리오 E).

    `label`은 중립 추상 표현만. 정당명·"보수/진보" 등 이념명 금지.
    예 허용: "혁신 입법 다수파", "재정 보수 성향", "복지 입법 적극형"
    예 금지: "○○당계", "보수파", "진보 진영"
    """
    cluster_id: str
    label: str
    centroid: list[float] = Field(default_factory=list)
    member_ids: list[str] = Field(default_factory=list)


# Persona는 코드 SSOT (api.services.persona) - 그래프 노드 아님.
# 참조용 타입만 별도 export.
PersonaId = Literal[
    "editorial", "data_ai", "ad_sales",
    "general_reader", "paid_subscriber", "b2b",
]


# ─── 관계 타입 카탈로그 (~30 edges) ─────────────────────────────────────────

# 형식: (relation_type, source_node, target_node, optional_properties)
RELATION_TYPES: list[tuple[str, str, str, list[str]]] = [
    # 인물·정당·지역
    ("BELONGS_TO",   "Person", "Party",      ["from", "to"]),
    ("REPRESENTS",   "Person", "District",   []),
    ("SERVED_IN",    "Person", "Term",       []),
    ("WORKS_FOR",    "Staff",  "Person",     []),

    # 입법
    ("PROPOSED",     "Person", "Bill",       []),
    ("CO_PROPOSED",  "Person", "Bill",       []),
    ("MEMBER_OF",    "Person", "Committee",  ["from", "to"]),
    ("OVERSEES",     "Committee", "Agency",  []),
    ("AMENDS",       "Bill",   "Law",        []),
    ("RELATES_TO",   "Bill",   "Topic",      []),
    ("ASSIGNED_TO",  "Bill",   "Committee",  []),
    ("VOTE_ON",      "Vote",   "Bill",       []),
    ("VOTED",        "Person", "Vote",       ["choice"]),  # choice ∈ VoteChoice
    ("SAID",         "Person", "Statement",  []),
    ("STATEMENT_AT", "Statement", "Session", []),
    ("ABOUT_TOPIC",  "Statement", "Topic",   []),
    ("SESSION_OF",   "Session", "Committee", []),

    # 주제·외부
    ("POLICY_LINKS", "Policy", "Bill",       []),
    ("ARTICLE_ABOUT", "Article", "Topic",    []),
    ("ARTICLE_REFS_PERSON", "Article", "Person", []),
    ("ARTICLE_REFS_BILL",   "Article", "Bill",   []),
    ("POLL_ABOUT",   "PollResult", "Topic",  []),
    ("SIGNAL_ABOUT", "SocialSignal", "Topic", []),

    # 미디어·독자·광고
    ("READ_EVENT",   "Reader", "ReadingEvent", []),
    ("EVENT_OF",     "ReadingEvent", "Article", []),
    ("FOLLOWS",      "Reader", "Person",     []),       # 동일 관계명, target은 Topic도 허용
    ("BOOKMARKED",   "Reader", "Bookmark",   []),
    ("HAS_TIER",     "Reader", "SubscriptionTier", []),
    ("CONSIDERED",   "Article", "AdMatchDecision", []),
    ("CANDIDATE",    "AdMatchDecision", "Advertisement", []),
    ("CHOSE",        "AdMatchDecision", "Advertisement", []),
    ("IMPRESSION_OF",   "AdImpression", "Advertisement", []),
    ("IMPRESSION_ON",   "AdImpression", "Article", []),
    ("IMPRESSION_TO",   "AdImpression", "Reader",  []),

    # 분석 메타
    ("IN_CLUSTER",   "Person", "Cluster",    []),
]


# ─── 노드 클래스 카탈로그 (objects.py가 lookup) ─────────────────────────────

NODE_CLASSES: dict[str, type[GraphNode]] = {
    cls.__name__: cls
    for cls in (
        # Group 1: 인물·조직 (6)
        Person, Party, Staff, Committee, District, Term,
        # Group 2: 입법 (7)
        Bill, Law, Amendment, Vote, Statement, Session, Budget,
        # Group 3: 주제·외부 (6)
        Topic, Policy, Agency, ElectionResult, PollResult, SocialSignal,
        # Group 4: 미디어 (2)
        Article, Tag,
        # Group 5: 독자 측 (5)
        Reader, ReaderProfile, SubscriptionTier, ReadingEvent, Bookmark,
        # Group 6: 광고 (4)
        Advertisement, AdInventory, AdImpression, AdMatchDecision,
        # Group 7: 분석 메타 (1)
        Cluster,
    )
}

# 총 31 그래프 노드 클래스 (+ Persona는 코드 SSOT).
assert len(NODE_CLASSES) == 31, f"Expected 31 node classes, got {len(NODE_CLASSES)}"


def get_node_class(name: str) -> Optional[type[GraphNode]]:
    """문자열 이름으로 노드 클래스 lookup. objects.py 라우터가 사용."""
    return NODE_CLASSES.get(name)


# ─── ADR-0004 Layer 4 - 금지 필드 가드 ──────────────────────────────────────

# 절대 노드 모델에 추가 금지. CI grep job(`political-neutrality-check`)이 차단.
# 이 set은 런타임 검증에도 사용 - validate_no_forbidden_fields() 참조.
FORBIDDEN_FIELDS = frozenset({
    "political_leaning",
    "political_loyalty_score",
    "bias_label",
    "party_attack_intent",
})


def validate_no_forbidden_fields() -> list[str]:
    """모든 등록된 NODE_CLASSES에 금지 필드가 없는지 검증. import-time + 테스트.

    Returns: 위반된 (class_name, field_name) 리스트. 비어있으면 통과.
    """
    violations: list[str] = []
    for cls_name, cls in NODE_CLASSES.items():
        for field_name in cls.model_fields:
            if field_name in FORBIDDEN_FIELDS:
                violations.append(f"{cls_name}.{field_name}")
    return violations


# Import time 검증 - 모듈 로드 즉시 정치 중립성 가드 트리거.
_violations = validate_no_forbidden_fields()
if _violations:
    raise RuntimeError(
        f"ADR-0004 Layer 4 위반: 정치 성향 추론 필드 발견 - {_violations}"
    )
