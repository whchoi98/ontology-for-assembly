"""시나리오 I - 편향·중립성 가드레일 라우터 (ADR-0004 시연).

엔드포인트:
- GET  /api/neutrality/samples       데모 텍스트 4종 (낮음·중간·양호·우수)
- POST /api/neutrality/score         임의 텍스트 실시간 채점
- GET  /api/neutrality/recent        최근 ops_metrics trace (balance score 분포)
- GET  /api/neutrality/architecture  ADR-0004 4-layer 구성 메타

페르소나 차별:
- editorial: 데스크 책임 hint
- data_ai: 메트릭 dashboard 추천
- ad_sales: 광고 안전성 link
- general_reader: 친절한 설명
- paid_subscriber: 보고서 export
- b2b: API 사양
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from api.services import guardrails, ops_metrics
from api.services.persona import get as get_persona

router = APIRouter(prefix="/api/neutrality", tags=["neutrality"])


class BalanceComponentsModel(BaseModel):
    party_mention_balance: float
    citation_score: float
    assertion_penalty: float
    parties_mentioned: list[str]
    total_party_mentions: int
    citation_count: int
    assertion_count: int


class ScoreResponse(BaseModel):
    text: str
    score: float
    alarm: bool
    components: BalanceComponentsModel
    guardrail_passed: bool
    blocked_topics: list[str] = Field(default_factory=list)
    persona_id: str
    interpretation: str


class SampleEntry(BaseModel):
    sample_id: str
    label: str          # "낮음", "중간", "양호", "우수"
    description: str    # 1-2문장 설명
    text: str
    score: float
    components: BalanceComponentsModel
    alarm: bool


class SamplesResponse(BaseModel):
    persona_id: str
    samples: list[SampleEntry]
    threshold: float
    note: str


class RecentTraceEntry(BaseModel):
    ts_iso: str
    persona_id: str
    scenario_code: str
    political_balance_score: float
    alarm: bool
    alarm_reason: Optional[str] = None
    blocked_topics: list[str] = Field(default_factory=list)


class RecentResponse(BaseModel):
    persona_id: str
    traces: list[RecentTraceEntry]
    counters: dict
    threshold: float


class ArchitectureLayer(BaseModel):
    layer: int
    name: str
    where: str
    description: str
    is_active: bool


class ArchitectureResponse(BaseModel):
    persona_id: str
    layers: list[ArchitectureLayer]
    adr_reference: str
    party_catalog: list[str]
    weights: dict


class ScoreRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


# ─── 데모 시드 텍스트 (정치 중립성 시연용) ──────────────────────────────────
# 점수 분포를 보이기 위해 의도적으로 4단계 텍스트 준비.
# 모두 가상의 표현. 실제 의원·정당 비방 의도 없음.
_SAMPLE_TEXTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "low_balance_001",
        "낮음",
        "단정적 가치 판단·일방향 정당 언급·인용 없음 - 알람 trigger 의도.",
        (
            "더불어민주당이 추진한 본 법안은 실패했다고 평가할 수 있다. "
            "야당의 반대 의견은 옳다고 보기 어렵고, 본 정책의 결정 과정은 잘못했다는 분석이 다수다. "
            "결과적으로 본 정책 영역은 무능한 운영의 사례로 남을 가능성이 높다."
        ),
    ),
    (
        "mid_balance_002",
        "중간",
        "정당 한쪽만 다수 언급 + 출처 일부 - 균형 부족.",
        (
            "더불어민주당은 이번 회기에서 12건의 입법을 주도했다. "
            "더불어민주당 소속 의원들의 발언 빈도가 높았으나 표결 일치율도 91%로 안정적이었다. "
            "(출처: 국회 OpenAPI 2026-04)"
        ),
    ),
    (
        "good_balance_003",
        "양호",
        "양당 균형 + 출처 인용 - 알람 통과 (≥ 0.8).",
        (
            "이번 회기에서 더불어민주당과 국민의힘은 각각 12건, 11건의 입법을 발의했다. "
            "양당 일치율은 평균 62% 수준이며, 청년 주거 등 일부 의제에서는 96%로 높은 협력을 보였다. "
            "(출처: 국회 OpenAPI 2026-04, 표결 데이터셋)"
        ),
    ),
    (
        "excellent_balance_004",
        "우수",
        "양당+제3당 균형 언급 + 다수 출처 + 단정적 표현 회피.",
        (
            "22대 국회 1분기 발의 분포는 더불어민주당 12건, 국민의힘 11건, "
            "정의당 3건, 개혁신당 2건으로 집계됐다. 본회의 표결 일치율은 평균 62%로 "
            "전 회기 대비 변화 폭은 크지 않은 것으로 나타났다. "
            "(출처: 국회 OpenAPI 2026-04, [국회 OpenAPI] 본회의 의안 데이터셋, "
            "https://open.assembly.go.kr/)"
        ),
    ),
)


def _score_text(text: str) -> tuple[float, BalanceComponentsModel, bool, list[str], bool]:
    """텍스트 채점 헬퍼 - score / components / alarm / blocked / guardrail_passed 반환."""
    score, components = guardrails.political_balance_score(text)
    result = guardrails.check_output(text)
    alarm = score < guardrails.ALARM_THRESHOLD
    return (
        score,
        BalanceComponentsModel(**asdict(components)),
        alarm,
        list(result.blocked_topics),
        result.passed,
    )


def _interpret(score: float, components: BalanceComponentsModel) -> str:
    """점수의 자연어 해석 (UI에 표시)."""
    if score >= 0.95:
        return "우수 - 양당 균형 언급 + 출처 인용 + 단정적 표현 회피 모두 충족."
    if score >= 0.8:
        return "양호 - 알람 임계 통과. 운영 콘솔 알람 없이 응답 전달."
    if score >= 0.6:
        return (
            f"중간 - 알람 임계({guardrails.ALARM_THRESHOLD}) 미달. UI 노란색 경고 표시 + "
            "운영 콘솔 메트릭 기록. 보조 정보 추가 권장."
        )
    return (
        "낮음 - 알람 + 데스크 검토 권장. "
        "정당 언급 균형·출처 인용·단정적 가치 판단 회피를 보강하세요."
    )


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────


@router.get("/samples", response_model=SamplesResponse)
def list_samples(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> SamplesResponse:
    """데모 텍스트 4종 - 점수 분포 시연."""
    pid = x_persona_id or "editorial"
    samples: list[SampleEntry] = []
    for sample_id, label, description, text in _SAMPLE_TEXTS:
        score, components, alarm, _, _ = _score_text(text)
        samples.append(
            SampleEntry(
                sample_id=sample_id,
                label=label,
                description=description,
                text=text,
                score=round(score, 3),
                components=components,
                alarm=alarm,
            )
        )
    return SamplesResponse(
        persona_id=pid,
        samples=samples,
        threshold=guardrails.ALARM_THRESHOLD,
        note=(
            f"임계 {guardrails.ALARM_THRESHOLD} 미만은 노란색 경고. "
            "정당 비방 결합 패턴은 Layer 1 Bedrock Guardrails 단에서 차단."
        ),
    )


@router.post("/score", response_model=ScoreResponse)
def score_text(
    request: ScoreRequest,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ScoreResponse:
    """임의 텍스트 실시간 채점 - 데모 라이브 입력."""
    pid = x_persona_id or "editorial"
    score, components, alarm, blocked, passed = _score_text(request.text)
    return ScoreResponse(
        text=request.text,
        score=round(score, 3),
        alarm=alarm,
        components=components,
        guardrail_passed=passed,
        blocked_topics=blocked,
        persona_id=pid,
        interpretation=_interpret(score, components),
    )


@router.get("/recent", response_model=RecentResponse)
def recent_traces(
    limit: int = 20,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> RecentResponse:
    """최근 ops_metrics trace + 누적 카운터."""
    pid = x_persona_id or "editorial"
    traces = ops_metrics.get_recent_traces(limit=limit)
    counters = ops_metrics.get_guardrail_counters()
    return RecentResponse(
        persona_id=pid,
        traces=[
            RecentTraceEntry(
                ts_iso=t.ts_iso,
                persona_id=t.persona_id,
                scenario_code=t.scenario_code,
                political_balance_score=round(t.political_balance_score, 3),
                alarm=t.alarm,
                alarm_reason=t.alarm_reason,
                blocked_topics=list(t.blocked_topics),
            )
            for t in traces
        ],
        counters={
            "total_invocations": counters.total_invocations,
            "total_blocked": counters.total_blocked,
            "total_alarms_low_balance": counters.total_alarms_low_balance,
            "avg_balance_score": round(counters.avg_balance_score, 3),
            "blocked_by_topic": counters.blocked_by_topic,
        },
        threshold=guardrails.ALARM_THRESHOLD,
    )


@router.get("/architecture", response_model=ArchitectureResponse)
def get_architecture(
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ArchitectureResponse:
    """ADR-0004 4-layer 가드레일 구성 메타 (UI 다이어그램)."""
    pid = x_persona_id or "editorial"
    persona = get_persona(pid)
    layers = [
        ArchitectureLayer(
            layer=1,
            name="Bedrock Guardrails",
            where="aws/bedrock-runtime apply_guardrail()",
            description=(
                "Production: assembly-political-neutrality guardrail ID. "
                "정당 비방 결합 패턴 차단. INPUT·OUTPUT 양방향. "
                "DEMO_PUBLIC_MODE=true는 로컬 휴리스틱."
            ),
            is_active=True,
        ),
        ArchitectureLayer(
            layer=2,
            name="NEUTRALITY_GUARD_SUFFIX",
            where="api/services/persona.py",
            description=(
                "모든 system_prompt 끝에 자동 부착. '정파 평가·이념 라벨 금지' 등 "
                "6 페르소나 공통 룰. ADR-0004 Layer 2."
            ),
            is_active=True,
        ),
        ArchitectureLayer(
            layer=3,
            name="political_balance_score",
            where="api/services/guardrails.py",
            description=(
                f"3 컴포넌트 가중합 - 정당 균형 {guardrails.WEIGHT_PARTY_BALANCE}, "
                f"인용 {guardrails.WEIGHT_CITATION}, 단정적 표현 감점 {guardrails.WEIGHT_ASSERTION}. "
                f"< {guardrails.ALARM_THRESHOLD}은 운영 콘솔 알람."
            ),
            is_active=True,
        ),
        ArchitectureLayer(
            layer=4,
            name="FORBIDDEN_FIELDS",
            where="data/schemas.py + Pydantic extra='forbid'",
            description=(
                "Reader.political_leaning·Person.ideology_label 등 "
                "정치 성향 추론 필드 자체를 schema에서 금지. 데이터 단의 ADR-0004."
            ),
            is_active=True,
        ),
    ]
    party_catalog = [c for c, _ in guardrails.KNOWN_PARTIES]
    return ArchitectureResponse(
        persona_id=pid,
        layers=layers,
        adr_reference="ADR-0004 정치 중립성 가드레일",
        party_catalog=party_catalog,
        weights={
            "party_balance": guardrails.WEIGHT_PARTY_BALANCE,
            "citation": guardrails.WEIGHT_CITATION,
            "assertion_penalty": guardrails.WEIGHT_ASSERTION,
            "alarm_threshold": guardrails.ALARM_THRESHOLD,
            "_persona_tone": persona.get("tone", ""),
        },
    )
