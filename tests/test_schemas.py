"""data.schemas 31-class SSOT 검증.

테스트:
- 31개 노드 클래스 등록 완료
- GraphNode base가 source 필드 강제
- Reader HashedId 정규식 검증
- 모든 클래스에 ADR-0004 Layer 4 금지 필드 미존재
- RELATION_TYPES 카탈로그 무결성
- BillStatus·VoteChoice·AdMatchMode enum 일관성
- AdMatchDecision audit trace 구조
- import 시 자동 정치 중립성 가드 트리거
"""
from __future__ import annotations
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from data import schemas


# ─── 기본 등록 ────────────────────────────────────────────────────────────────

def test_thirty_one_node_classes_registered():
    """spec §4 - 31개 노드 클래스가 NODE_CLASSES에 등록되어야 한다."""
    assert len(schemas.NODE_CLASSES) == 31


def test_all_classes_inherit_graph_node():
    """모든 등록 클래스는 GraphNode를 상속 (source 필드 강제)."""
    for name, cls in schemas.NODE_CLASSES.items():
        assert issubclass(cls, schemas.GraphNode), f"{name} does not inherit GraphNode"


@pytest.mark.parametrize("cls_name", sorted(["Person", "Bill", "Vote", "Reader",
                                              "Advertisement", "AdMatchDecision", "Cluster"]))
def test_class_lookup_by_name(cls_name):
    """get_node_class()가 이름으로 클래스 lookup."""
    cls = schemas.get_node_class(cls_name)
    assert cls is not None
    assert cls.__name__ == cls_name


def test_unknown_class_returns_none():
    assert schemas.get_node_class("NonExistent") is None


# ─── ADR-0004 Layer 4 — 정치 중립성 금지 필드 ────────────────────────────────

def test_no_forbidden_fields_in_any_class():
    """ADR-0004 Layer 4 — 어떤 등록 클래스에도 정치 성향 추론 필드가 없어야 한다."""
    violations = schemas.validate_no_forbidden_fields()
    assert violations == [], f"금지 필드 발견: {violations}"


def test_forbidden_fields_set_intact():
    """금지 필드 set이 ADR-0004에 명시된 4개를 모두 포함."""
    expected = {"political_leaning", "political_loyalty_score", "bias_label", "party_attack_intent"}
    assert expected == set(schemas.FORBIDDEN_FIELDS)


# ─── source 필드 강제 ───────────────────────────────────────────────────────

def test_source_field_required():
    """모든 노드는 source 필드를 가져야 한다 (DataSourceBadge)."""
    with pytest.raises(ValidationError):
        schemas.Person(assembly_id="MONA_001", name="홍길동", term=22)  # source 누락


def test_source_field_enum_constraint():
    """source는 real/synthetic/external 중 하나만 허용."""
    with pytest.raises(ValidationError):
        schemas.Party(party_id="P001", name="민주당", source="invalid")  # type: ignore[arg-type]


def test_extra_fields_forbidden():
    """extra='forbid' - 미정의 필드 추가 시 ValidationError.

    이게 정치 성향 추론 필드 등을 런타임에서도 차단하는 안전장치.
    """
    with pytest.raises(ValidationError):
        schemas.Person(
            assembly_id="MONA_001", name="홍길동", term=22, source="real",
            political_leaning=0.5,  # type: ignore[call-arg]  # 금지 필드
        )


# ─── Reader 익명화 (ADR-0003) ────────────────────────────────────────────────

def test_reader_id_hashed_format():
    """Reader.reader_id는 64자 hex (솔티드 SHA-256만 허용)."""
    valid_hash = "a" * 64
    r = schemas.Reader(
        reader_id=valid_hash, tier="free",
        since=datetime.now(timezone.utc), source="synthetic",
    )
    assert r.reader_id == valid_hash


def test_reader_id_rejects_non_hex():
    """원본 쿠키·이메일 등 비-hex 문자 거부."""
    with pytest.raises(ValidationError):
        schemas.Reader(
            reader_id="cookie_abc123",
            tier="free",
            since=datetime.now(timezone.utc),
            source="synthetic",
        )


def test_reader_id_rejects_uppercase():
    """대문자 hex도 거부 (소문자 정규화 강제)."""
    with pytest.raises(ValidationError):
        schemas.Reader(
            reader_id="A" * 64,
            tier="free",
            since=datetime.now(timezone.utc),
            source="synthetic",
        )


def test_reader_id_rejects_short_hash():
    """64자 미만 거부."""
    with pytest.raises(ValidationError):
        schemas.Reader(
            reader_id="a" * 32,  # MD5 길이는 거부
            tier="free",
            since=datetime.now(timezone.utc),
            source="synthetic",
        )


# ─── AdMatchDecision audit trace ────────────────────────────────────────────

def test_ad_match_decision_skip_uses_none_chosen():
    """광고 노출 생략 결정은 chosen_ad_id=None."""
    d = schemas.AdMatchDecision(
        decision_id="dec_001",
        mode="agent",
        article_id="art_001",
        candidate_ad_ids=["ad_1", "ad_2"],
        chosen_ad_id=None,  # 생략 결정
        score=0.0,
        reason_text="skip 정치인 비위 의혹 콘텐츠 | 근거: 검찰 수사 진행 | 회피: 모든 광고주",
        timestamp=datetime.now(timezone.utc),
        source="synthetic",
    )
    assert d.chosen_ad_id is None
    assert d.score == 0.0


def test_ad_match_decision_allow_records_chosen():
    """광고 노출 결정은 chosen_ad_id 명시."""
    d = schemas.AdMatchDecision(
        decision_id="dec_002",
        mode="agent",
        article_id="art_002",
        candidate_ad_ids=["ad_3", "ad_4"],
        chosen_ad_id="ad_3",
        score=0.87,
        reason_text="allow 정책 정보성 콘텐츠 | 근거: 산업 동향 분석 | 회피: None",
        timestamp=datetime.now(timezone.utc),
        source="synthetic",
    )
    assert d.chosen_ad_id == "ad_3"


def test_ad_match_decision_score_bounds():
    """score는 0-1 범위."""
    with pytest.raises(ValidationError):
        schemas.AdMatchDecision(
            decision_id="dec_003", mode="agent", article_id="art_003",
            score=1.5,  # invalid
            reason_text="t", timestamp=datetime.now(timezone.utc), source="synthetic",
        )


# ─── 관계 카탈로그 무결성 ──────────────────────────────────────────────────

def test_relation_types_count():
    """관계 ~30개 등록 (spec §4.2)."""
    assert len(schemas.RELATION_TYPES) >= 30


def test_relation_endpoints_are_registered_classes():
    """모든 관계의 source/target 노드가 등록된 클래스여야 한다."""
    for rel_name, src, tgt, _props in schemas.RELATION_TYPES:
        assert src in schemas.NODE_CLASSES, f"{rel_name}: source class '{src}' not registered"
        assert tgt in schemas.NODE_CLASSES, f"{rel_name}: target class '{tgt}' not registered"


def test_voted_relation_has_choice_property():
    """(Person)-[:VOTED {choice}]->(Vote)에 choice 속성 필수."""
    voted = next(r for r in schemas.RELATION_TYPES if r[0] == "VOTED")
    assert "choice" in voted[3]


def test_ad_match_decision_relations():
    """AdMatchDecision은 Article·Advertisement와 관계가 있어야 한다 (audit trace)."""
    rels = {r[0] for r in schemas.RELATION_TYPES}
    assert "CONSIDERED" in rels        # (Article)->(AdMatchDecision)
    assert "CANDIDATE" in rels         # (AdMatchDecision)->(Advertisement)
    assert "CHOSE" in rels             # (AdMatchDecision)->(Advertisement)


# ─── 시나리오별 핵심 클래스 검증 ────────────────────────────────────────────

def test_scenario_b_chat_supported_classes():
    """시나리오 B: 3-stage chat이 Person·Bill·Topic·Statement 노드 사용."""
    for required in ("Person", "Bill", "Topic", "Statement"):
        assert required in schemas.NODE_CLASSES


def test_scenario_l_ad_match_supported_classes():
    """시나리오 L: 광고 매칭이 Advertisement·AdInventory·AdMatchDecision·AdImpression 사용."""
    for required in ("Advertisement", "AdInventory", "AdMatchDecision", "AdImpression"):
        assert required in schemas.NODE_CLASSES


def test_b2c_reader_classes():
    """B2C 페르소나(general_reader, paid_subscriber)가 Reader·ReadingEvent·Bookmark·SubscriptionTier·ReaderProfile 사용."""
    for required in ("Reader", "ReaderProfile", "SubscriptionTier", "ReadingEvent", "Bookmark"):
        assert required in schemas.NODE_CLASSES


# ─── 클래스 그룹 카운트 ────────────────────────────────────────────────────

CLASS_GROUPS = {
    "인물·조직": ["Person", "Party", "Staff", "Committee", "District", "Term"],
    "입법": ["Bill", "Law", "Amendment", "Vote", "Statement", "Session", "Budget"],
    "주제·외부": ["Topic", "Policy", "Agency", "ElectionResult", "PollResult", "SocialSignal"],
    "미디어": ["Article", "Tag"],
    "독자 측": ["Reader", "ReaderProfile", "SubscriptionTier", "ReadingEvent", "Bookmark"],
    "광고": ["Advertisement", "AdInventory", "AdImpression", "AdMatchDecision"],
    "분석 메타": ["Cluster"],
}


@pytest.mark.parametrize("group_name,members", list(CLASS_GROUPS.items()))
def test_class_group_completeness(group_name, members):
    """spec §4.1의 7개 그룹이 모두 등록되어야 한다."""
    for cls_name in members:
        assert cls_name in schemas.NODE_CLASSES, f"{group_name}: {cls_name} 미등록"


def test_group_totals():
    """그룹별 카운트 6/7/6/2/5/4/1 합계 = 31."""
    total = sum(len(m) for m in CLASS_GROUPS.values())
    assert total == 31
    assert total == len(schemas.NODE_CLASSES)


# ─── 정치 중립성 라벨 강제 ─────────────────────────────────────────────────

def test_party_no_ideology_tag_field():
    """Party 클래스에 ideology_tag(보수/진보) 등 필드 없음."""
    fields = set(schemas.Party.model_fields.keys())
    forbidden = {"ideology_tag", "political_leaning", "ideology", "spectrum"}
    assert not (fields & forbidden), f"Party에 금지 필드 발견: {fields & forbidden}"


def test_person_no_political_leaning():
    """Person 클래스에 정치 성향 추론 필드 없음."""
    fields = set(schemas.Person.model_fields.keys())
    forbidden = {"political_leaning", "political_loyalty_score", "ideology"}
    assert not (fields & forbidden)


def test_reader_no_political_leaning():
    """ADR-0004 - Reader/ReaderProfile에 정치 성향 추론 필드 없음."""
    reader_fields = set(schemas.Reader.model_fields.keys())
    profile_fields = set(schemas.ReaderProfile.model_fields.keys())
    forbidden = schemas.FORBIDDEN_FIELDS
    assert not (reader_fields & forbidden)
    assert not (profile_fields & forbidden)
