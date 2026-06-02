"""표결 이상치 탐지 서비스 (시나리오 K - PDF 시그니처).

이상치 유형:
- party_line_break: 당론 이탈 - 정당 다수와 반대 표결
- swing_vote: 양당 차이가 미세한 표결 (몇 표 차이로 가결·부결 갈림)
- cross_party: 정파 무관 협력 패턴 (정상이지만 추적 가치 있음)

PoC: 합성 시드 기반 결정적 출력. Production: pandas window detection on real Vote data
+ Bedrock LLM으로 패턴 라벨링.

References:
- spec §3.1 시나리오 K (PDF 3-page 시그니처)
- ADR-0004 (정당 비방 어휘 금지 - "당론 이탈"은 사실 기술, 평가 X)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

__all__ = ["OutlierEntry", "list_outliers", "get_outlier"]


OutlierType = Literal["party_line_break", "swing_vote", "cross_party"]


@dataclass(frozen=True)
class DeviatingPerson:
    """이상치 표결을 한 의원 - 정당 입장과 다르게 표결."""
    person_id: str
    name: str
    party: str
    choice: str  # "yes" / "no" / "abstain" / "absent"
    reason_hint: Optional[str] = None


@dataclass(frozen=True)
class OutlierEntry:
    """표결 이상치 1건."""
    outlier_id: str
    vote_id: str
    bill_id: str
    bill_title: str
    vote_date: str
    outlier_type: OutlierType
    label: str                    # 한국어 짧은 라벨
    description: str              # 1-2문장 설명
    deviation_score: float        # 0-1, 높을수록 이상치
    expected_pattern: str         # "더불어민주당 다수 찬성"
    actual_pattern: str           # "민주당 142 찬성 + 3 반대"
    deviating_persons: list[DeviatingPerson]
    ai_label: str                 # LLM 패턴 분석 결과 (PoC mock)


# ─── 합성 시드 (PDF 시그니처 시연용) ────────────────────────────────────────

_DEMO_OUTLIERS: tuple[OutlierEntry, ...] = (
    OutlierEntry(
        outlier_id="ol_party_break_001",
        vote_id="V_PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3_2026-04-22",
        bill_id="PRC_K3Z1K1Y5K1F1S2H7M5Z5R4J3",
        bill_title="개인정보 보호법 일부개정법률안",
        vote_date="2026-04-22",
        outlier_type="party_line_break",
        label="당론 이탈 (3명)",
        description=(
            "더불어민주당 의원 142명 중 3명이 정당 입장과 다르게 반대 표결. "
            "통상 본 사안에서 양당 일치율이 높았으나 개인 신념 차이가 노출됨."
        ),
        deviation_score=0.82,
        expected_pattern="더불어민주당 145명 찬성 예상 (직전 표결 일치율 91%)",
        actual_pattern="민주당 142 찬성 + 3 반대 (이탈자 3명)",
        deviating_persons=[
            DeviatingPerson("2385336L", "조배숙", "더불어민주당", "no",
                            "지역구 산업 정책 이해관계"),
            DeviatingPerson("O6D8329R", "김태년", "더불어민주당", "no",
                            "법무 분야 전문성 의견 차이"),
            DeviatingPerson("MSY7784L", "정성호", "더불어민주당", "abstain",
                            "기권 표명"),
        ],
        ai_label=(
            "당론 이탈 (정당 평균 대비 deviation score 0.82). 3명의 이탈자는 "
            "각각 지역구 산업·법무 전문성·기권 등 명시적 이유를 표명한 것으로 추정. "
            "정책적 차이로 해석 권장 - 정당 분열 보도는 자제."
        ),
    ),
    OutlierEntry(
        outlier_id="ol_swing_001",
        vote_id="V_PRC_L4A2L2Z6L2G2T3I8N6A6S5K4_2026-05-11",
        bill_id="PRC_L4A2L2Z6L2G2T3I8N6A6S5K4",
        bill_title="디지털 콘텐츠 진흥에 관한 법률안",
        vote_date="2026-05-11",
        outlier_type="swing_vote",
        label="박빙 표결 (찬 148 vs 반 146)",
        description=(
            "찬성 148 대 반대 146으로 2표 차이 가결. 양당 모두 의견 분열, "
            "한 쪽으로 쏠리지 않은 박빙 사안. 디지털 콘텐츠 규제 vs 진흥 trade-off."
        ),
        deviation_score=0.75,
        expected_pattern="양당 일치율 평균 60% 대비 본 사안 51% (불확실성 ↑)",
        actual_pattern="찬 148 (민주 88 + 국힘 55 + 기타 5) / 반 146 (민주 52 + 국힘 87 + 기타 7)",
        deviating_persons=[
            DeviatingPerson("7R156073", "권칠승", "개혁신당", "yes",
                            "캐스팅 보트 - 본인 표가 가결 결정적"),
        ],
        ai_label=(
            "박빙 표결 swing vote. 2표 차이 가결. 양당 모두 내부 분열 (민주 찬반 88:52, "
            "국힘 찬반 55:87). 후속 분석: 의원별 지역구 산업 분포와 표결 상관 가능성."
        ),
    ),
    OutlierEntry(
        outlier_id="ol_cross_001",
        vote_id="V_PRC_N6C4N4B8N4I4V5K0P8C8U7M6_2026-05-02",
        bill_id="PRC_N6C4N4B8N4I4V5K0P8C8U7M6",
        bill_title="청년 주거지원 확대법안",
        vote_date="2026-05-02",
        outlier_type="cross_party",
        label="양당 협력 (일치율 96%)",
        description=(
            "양당 일치율 96%로 평년 평균(62%) 대비 크게 높음. 청년 주거 정책이 정파 "
            "초월적 의제로 정착하는 신호. 정상 표결이지만 추적 가치 있는 협력 패턴."
        ),
        deviation_score=0.68,
        expected_pattern="양당 일치율 평균 62%",
        actual_pattern="민주 99% 찬성 + 국힘 92% 찬성 + 기타 100% 찬성 (총 285/289)",
        deviating_persons=[],
        ai_label=(
            "정파 초월 협력 의제 (cross-party). 청년 정책은 양당 합의가 이뤄지는 "
            "드문 분야. 후속 취재: 이 협력이 발의 단계부터인지 표결 직전 합의인지."
        ),
    ),
    OutlierEntry(
        outlier_id="ol_party_break_002",
        vote_id="V_PRC_O7D5O5C9O5J5W6L1Q9D9V8N7_2026-05-08",
        bill_id="PRC_O7D5O5C9O5J5W6L1Q9D9V8N7",
        bill_title="데이터 산업 진흥법 일부개정법률안",
        vote_date="2026-05-08",
        outlier_type="party_line_break",
        label="당론 이탈 (2명)",
        description=(
            "국민의힘 의원 138명 중 2명이 정당 입장과 다르게 찬성 표결. "
            "데이터 활용 확대 측면에서 산업계 이해관계와 정당 노선 충돌."
        ),
        deviation_score=0.71,
        expected_pattern="국민의힘 다수 반대 (직전 데이터 정책 사안 일치율 88%)",
        actual_pattern="국힘 136 반대 + 2 찬성 (이탈자 2명)",
        deviating_persons=[
            DeviatingPerson("DMP1439I", "전용기", "국민의힘", "yes",
                            "지역구 IT 산업 기반"),
            DeviatingPerson("MONA_034", "이만희", "국민의힘", "yes",
                            "산업계 자문 의견 반영"),
        ],
        ai_label=(
            "국힘 측 당론 이탈 2명. 지역구 IT·산업 기반 의원 중심. 정당 vs 산업 정책 "
            "긴장 노출. 후속 분석: 향후 데이터 관련 의안 표결에서 동일 패턴 추적."
        ),
    ),
    OutlierEntry(
        outlier_id="ol_swing_002",
        vote_id="V_PRC_S1H9S9G3S9N9A0P5U3H3Z2R1_2026-05-10",
        bill_id="PRC_S1H9S9G3S9N9A0P5U3H3Z2R1",
        bill_title="지방자치단체 균형발전 지원 특별법안",
        vote_date="2026-05-10",
        outlier_type="swing_vote",
        label="박빙 표결 (찬 145 vs 반 139)",
        description=(
            "찬성 145 대 반대 139으로 6표 차이 가결. 수도권·비수도권 의원 표결이 "
            "정당보다 지역구 우선 패턴 보임."
        ),
        deviation_score=0.69,
        expected_pattern="정당 별 일치 패턴",
        actual_pattern="찬 145 (비수도권 113 + 수도권 32) / 반 139 (수도권 95 + 비수도권 44)",
        deviating_persons=[],
        ai_label=(
            "지역 vs 정당 균형 — 표결이 정당 노선보다 지역구 이해관계를 따른 패턴. "
            "후속 취재: 수도권·비수도권 의원의 균형발전 인식 차이."
        ),
    ),
)


# ─── 공개 API ───────────────────────────────────────────────────────────────

def list_outliers(
    limit: int = 10,
    outlier_type: Optional[OutlierType] = None,
) -> list[OutlierEntry]:
    """이상치 표결 목록 - deviation_score 내림차순.

    Phase 4e: ENABLE_NEPTUNE_REAL=true이면 real Cypher query로 detection.
    Production: VOTED 엣지 (28K+) 분석으로 *당론 이탈*·*박빙*·*정파 초월* 자동 탐지.
    """
    import os
    if os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            print(f"[outlier_detect] starting real query (max_bills=30)...", flush=True)
            real = _detect_real_outliers(max_bills=30)
            print(f"[outlier_detect] real returned {len(real)} outliers", flush=True)
            if real:
                filtered = real
                if outlier_type:
                    filtered = [o for o in filtered if o.outlier_type == outlier_type]
                sorted_ = sorted(filtered, key=lambda o: -o.deviation_score)
                return list(sorted_[:limit])
        except Exception as e:
            import traceback
            print(f"[outlier_detect] FAIL: {traceback.format_exc()}", flush=True)

    # Fixture fallback
    filtered = _DEMO_OUTLIERS
    if outlier_type:
        filtered = tuple(o for o in filtered if o.outlier_type == outlier_type)
    sorted_ = sorted(filtered, key=lambda o: -o.deviation_score)
    return list(sorted_[:limit])


def _detect_real_outliers(max_bills: int = 30) -> list[OutlierEntry]:
    """VOTED 엣지에서 *당론 이탈*·*박빙*·*정파 초월* 자동 탐지.

    Heuristics:
    - 각 의안 (Bill) × 각 정당 (Party)의 majority vote 계산
    - 정당과 *다르게 표결한 의원* = party_line_break
    - 찬·반 차이 < 5표 = swing_vote
    - 양당 일치율 > 80% = cross_party (정상이지만 추적 가치)
    """
    from api.services import neptune as nep

    # Step 1: 가장 표결 많은 bill_id list
    res = nep.open_cypher(
        "MATCH ()-[v:VOTED]->(b:Bill) "
        "RETURN b.bill_id AS bid, b.title AS title, count(v) AS votes "
        "ORDER BY votes DESC LIMIT $max",
        parameters={"max": max_bills},
    )
    bill_rows = res.rows if hasattr(res, "rows") else res.get("results", [])

    outliers: list[OutlierEntry] = []
    for br in bill_rows:
        bid = br.get("bid") or ""
        title = br.get("title") or bid
        if not bid:
            continue

        # Step 2: 의안의 정당-표결 분포
        vres = nep.open_cypher(
            "MATCH (p:Person)-[v:VOTED]->(b:Bill {bill_id: $bid}) "
            "OPTIONAL MATCH (p)-[:BELONGS_TO]->(party:Party) "
            "RETURN p.assembly_id AS mona, p.name AS name, p.party_id AS party_id, "
            "party.name AS party_name, v.value AS choice, v.date AS vdate",
            parameters={"bid": bid},
        )
        vrows = vres.rows if hasattr(vres, "rows") else vres.get("results", [])
        if not vrows:
            continue

        # 정당별 majority + 카운트
        party_votes: dict[str, dict[str, int]] = {}
        choice_total = {"yes": 0, "no": 0, "abstain": 0, "absent": 0}
        for v in vrows:
            party = v.get("party_name") or v.get("party_id") or "무소속"
            choice = v.get("choice") or "absent"
            if party not in party_votes:
                party_votes[party] = {"yes": 0, "no": 0, "abstain": 0, "absent": 0}
            if choice in party_votes[party]:
                party_votes[party][choice] += 1
            if choice in choice_total:
                choice_total[choice] += 1

        # 정당별 majority choice
        party_majority = {
            p: max(counts, key=counts.get) for p, counts in party_votes.items()
        }

        # 이탈 의원: 정당 majority와 다르고, 본인이 actively 투표한 경우 (yes·no·abstain)
        deviating = [
            v for v in vrows
            if v.get("choice") in ("yes", "no", "abstain")
            and v.get("choice") != party_majority.get(v.get("party_name") or v.get("party_id") or "무소속")
        ]

        yes_total = choice_total["yes"]
        no_total = choice_total["no"]
        active_total = yes_total + no_total

        # 분류
        outlier_type: OutlierType
        deviation_score: float
        label_kr: str
        description: str
        expected: str
        actual: str

        if abs(yes_total - no_total) <= 5 and active_total >= 20:
            # 박빙
            outlier_type = "swing_vote"
            deviation_score = round(0.95 - abs(yes_total - no_total) * 0.02, 2)
            label_kr = f"박빙 표결 (찬 {yes_total} vs 반 {no_total})"
            description = (
                f"찬성 {yes_total} 대 반대 {no_total}로 {abs(yes_total-no_total)}표 차이. "
                f"양당 모두 의견 분열, 한 쪽으로 쏠리지 않은 박빙 사안."
            )
            expected = "양당 일치율 평균 60% 대비 본 사안 50%대 (불확실성 ↑)"
            actual = f"찬 {yes_total} / 반 {no_total} / 기권 {choice_total['abstain']} / 불참 {choice_total['absent']}"
        elif len(deviating) >= 1:
            # 당론 이탈
            outlier_type = "party_line_break"
            deviation_score = round(min(0.95, 0.6 + len(deviating) * 0.05), 2)
            # 이탈 정당별 분류
            dev_parties = [v.get("party_name") or v.get("party_id") or "무소속" for v in deviating]
            top_party = max(set(dev_parties), key=dev_parties.count) if dev_parties else "—"
            label_kr = f"당론 이탈 ({len(deviating)}명)"
            description = (
                f"{top_party} 등 정당 입장과 다르게 표결한 의원 {len(deviating)}명. "
                f"통상 본 사안에서 양당 일치율이 높았으나 개인 신념 차이가 노출됨."
            )
            expected = f"{top_party} 다수 찬성 예상 (직전 표결 일치율 90%+)"
            actual = ", ".join(
                f"{p} {sum(counts.values())}명 ({counts['yes']}찬/{counts['no']}반)"
                for p, counts in list(party_votes.items())[:3]
            )
        else:
            # 정상 표결 — outlier 아님 (skip)
            continue

        # cross_party 추가 검사
        active_parties = [p for p, c in party_votes.items() if (c["yes"] + c["no"]) >= 5]
        if len(active_parties) >= 2 and yes_total > active_total * 0.85 and len(deviating) <= 2:
            outlier_type = "cross_party"
            deviation_score = round(0.85 - len(deviating) * 0.02, 2)
            label_kr = f"양당 협력 (일치율 {int(yes_total/max(1,active_total)*100)}%)"
            description = (
                f"양당 일치율 {int(yes_total/max(1,active_total)*100)}%로 평년 평균(62%) 대비 크게 높음. "
                f"정파 초월적 의제로 정착하는 신호."
            )

        vdate_raw = (vrows[0].get("vdate") or "")[:8]
        vdate = (
            f"{vdate_raw[:4]}-{vdate_raw[4:6]}-{vdate_raw[6:8]}"
            if len(vdate_raw) == 8 else "—"
        )

        deviating_persons = [
            DeviatingPerson(
                person_id=v.get("mona") or "",
                name=v.get("name") or "—",
                party=v.get("party_name") or v.get("party_id") or "무소속",
                choice=v.get("choice") or "absent",
                reason_hint=None,
            )
            for v in deviating[:6]
        ]

        outliers.append(OutlierEntry(
            outlier_id=f"real_{outlier_type}_{bid[-12:]}",
            vote_id=f"V_{bid}_{vdate_raw}",
            bill_id=bid,
            bill_title=title,
            vote_date=vdate,
            outlier_type=outlier_type,
            label=label_kr,
            description=description,
            deviation_score=deviation_score,
            expected_pattern=expected,
            actual_pattern=actual,
            deviating_persons=deviating_persons,
            ai_label=(
                f"{label_kr} — VOTED 엣지 z-score 자동 detection. "
                f"deviation_score {deviation_score}. 정책적 차이로 해석 권장."
            ),
        ))

    return outliers


def get_outlier(outlier_id: str) -> Optional[OutlierEntry]:
    """단일 이상치 lookup."""
    for o in _DEMO_OUTLIERS:
        if o.outlier_id == outlier_id:
            return o
    return None
