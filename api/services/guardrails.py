"""정치 중립성 가드레일 - ADR-0004 Layer 1·2·3 통합 구현.

3개 레이어:
- Layer 1: Bedrock Guardrails wrapper (`check_prompt`, `check_output`) - API 단
- Layer 2: NEUTRALITY_GUARD_SUFFIX (api.services.persona 정의, 여기서 re-export)
- Layer 3: `political_balance_score` — 모든 LLM 응답 자동 평가, 운영 콘솔 메트릭

이 서비스는 모든 LLM 응답 경로의 단일 통과점. bedrock.invoke() wrapper에서 자동 호출.
"""
from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass, field
from typing import Optional

# Layer 2 가드를 같은 모듈에서 import 가능하도록 re-export.
from api.services.persona import NEUTRALITY_GUARD_SUFFIX

__all__ = [
    "NEUTRALITY_GUARD_SUFFIX",
    "ALARM_THRESHOLD",
    "BalanceComponents",
    "GuardrailResult",
    "political_balance_score",
    "check_prompt",
    "check_output",
    "annotate_response",
]


# ─── 정당 카탈로그 (중립 등록명만) ─────────────────────────────────────────
# 정당 변경 시 `ontology/mappings/party_canonical_names.yaml` + 이 리스트 둘 다 갱신.
# 별칭은 정규화용. 절대 이념 라벨(보수/진보) 추가 금지 - ADR-0004 Layer 4.
KNOWN_PARTIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (canonical_name, (alias_1, alias_2, ...))
    ("더불어민주당", ("민주당",)),
    ("국민의힘", ("국힘",)),
    ("정의당", ()),
    ("진보당", ()),
    ("개혁신당", ()),
    ("기본소득당", ()),
    ("새로운미래", ()),
    ("녹색정의당", ()),
    ("무소속", ("당적 없음",)),
)


# ─── 패턴 정의 ────────────────────────────────────────────────────────────────

# 출처 인용 패턴 - 발견될수록 신뢰성 향상.
CITATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"출처\s*[:：]"),
    re.compile(r"\(자료\s*[:：]"),
    re.compile(r"\[국회\s*OpenAPI\]"),
    re.compile(r"\(국회\s*공공\s*데이터\)"),
    re.compile(r"\(?출처\)?\s*[:：]?\s*\[?\d{4}년"),
    re.compile(r"https?://[\w./\-]+"),
)

# 단정적 가치 판단 표현 - 발견될수록 감점.
ASSERTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"잘못[했하][다음였]"),
    re.compile(r"실패[했하][다음였]"),
    re.compile(r"성공[했하][다음였]"),
    re.compile(r"옳다|틀렸다"),
    re.compile(r"무능|훌륭|뛰어나"),
    re.compile(r"부패|타락"),
    re.compile(r"엉터리|쓰레기"),
)

# 정당 비방 결합 패턴 (Layer 1 차단 대상).
PARTY_ATTACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(더불어민주당|국민의힘|정의당|진보당|개혁신당|기본소득당|새로운미래|녹색정의당)"
        r"[은는이가]?\s*\S{0,10}(무능|부패|쓰레기|악마|기만|배신)"
    ),
)


# ─── 가중치 + 임계 (spec §6.3) ─────────────────────────────────────────────

# 세 컴포넌트의 가중치. 합 = 1.0. 변경 시 `tests/test_guardrails.py` 임계값도 동조.
WEIGHT_PARTY_BALANCE: float = 0.5     # 정당 언급 균형이 가장 중요
WEIGHT_CITATION: float = 0.3          # 출처 인용 여부
WEIGHT_ASSERTION: float = 0.2         # 가치 판단 표현 감점

# 알람 임계. < 이 값이면 UI 노란색 경고 + CloudWatch alarm.
ALARM_THRESHOLD: float = 0.8


# ─── 결과 모델 ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BalanceComponents:
    """political_balance_score 산출 세부 (audit trail용)."""
    party_mention_balance: float       # 0-1
    citation_score: float              # 0-1
    assertion_penalty: float           # 0-1 (높을수록 좋음)
    parties_mentioned: list[str] = field(default_factory=list)
    total_party_mentions: int = 0
    citation_count: int = 0
    assertion_count: int = 0


@dataclass(frozen=True)
class GuardrailResult:
    """Bedrock Guardrails 응답 정규화."""
    passed: bool
    blocked_topics: list[str] = field(default_factory=list)
    redacted_text: Optional[str] = None       # 출력 필터 시 변환된 텍스트


# ─── political_balance_score 핵심 ─────────────────────────────────────────

def political_balance_score(text: str) -> tuple[float, BalanceComponents]:
    """LLM 응답 텍스트의 정치 중립성 점수 계산.

    Returns:
        (score [0.0–1.0], components for audit log)

    Higher = more neutral. 0.8 미만은 알람.
    이 함수는 순수 함수 (no I/O, no LLM 호출) - 모든 응답에 동기 호출 가능.
    """
    # 1. 정당 언급 균형
    party_counts = _count_party_mentions(text)
    party_balance = _compute_party_balance(party_counts)

    # 2. 출처 인용
    citation_count = sum(len(p.findall(text)) for p in CITATION_PATTERNS)
    citation_score = min(1.0, citation_count / 2.0)  # 2건 이상이면 만점

    # 3. 단정적 가치 판단 감점
    assertion_count = sum(len(p.findall(text)) for p in ASSERTION_PATTERNS)
    assertion_penalty = max(0.0, 1.0 - assertion_count * 0.2)  # 5건 이상이면 0

    score = (
        WEIGHT_PARTY_BALANCE * party_balance
        + WEIGHT_CITATION * citation_score
        + WEIGHT_ASSERTION * assertion_penalty
    )

    return score, BalanceComponents(
        party_mention_balance=party_balance,
        citation_score=citation_score,
        assertion_penalty=assertion_penalty,
        parties_mentioned=sorted(party_counts.keys()),
        total_party_mentions=sum(party_counts.values()),
        citation_count=citation_count,
        assertion_count=assertion_count,
    )


def _count_party_mentions(text: str) -> dict[str, int]:
    """정당명·별칭별 언급 횟수 (canonical로 정규화).

    Substring 함정 회피: canonical을 먼저 카운트하고 placeholder로 치환한 뒤
    잔여 텍스트에서만 alias 검색. 예) '민주당'은 '더불어민주당'의 substring이므로
    1차로 canonical을 빼두지 않으면 이중 카운트.
    """
    counts: dict[str, int] = {}
    remaining = text
    # 1차: canonical 카운트 + placeholder 치환
    for canonical, _aliases in KNOWN_PARTIES:
        n = remaining.count(canonical)
        if n > 0:
            counts[canonical] = counts.get(canonical, 0) + n
            remaining = remaining.replace(canonical, "█" * len(canonical))
    # 2차: 잔여 텍스트에서만 alias 검색 (canonical에 흡수된 부분은 placeholder)
    for canonical, aliases in KNOWN_PARTIES:
        for alias in aliases:
            n = remaining.count(alias)
            if n > 0:
                counts[canonical] = counts.get(canonical, 0) + n
                remaining = remaining.replace(alias, "█" * len(alias))
    return counts


def _compute_party_balance(counts: dict[str, int]) -> float:
    """정당 언급 빈도 분포의 균형 점수 [0, 1].

    - 0–1개 정당만 언급: 1.0 (균형 무관)
    - 다수 정당 언급 시: 1 - 변동계수(CV). 빈도 차이 작을수록 점수 ↑
    """
    if len(counts) < 2:
        return 1.0
    values = list(counts.values())
    mean = statistics.mean(values)
    if mean == 0:
        return 1.0
    stdev = statistics.stdev(values)
    cv = stdev / mean  # 변동계수 (Coefficient of Variation)
    return max(0.0, 1.0 - min(1.0, cv))


# ─── Bedrock Guardrails wrapper (Layer 1) ───────────────────────────────────

def check_prompt(prompt: str, persona_id: Optional[str] = None) -> GuardrailResult:
    """Bedrock Guardrails 입력 스크럽.

    Production: `bedrock-runtime.apply_guardrail()` 호출.
    Test (`DEMO_PUBLIC_MODE=true`): 로컬 휴리스틱만 사용.

    persona_id는 미래 페르소나별 가드레일 룰 분기 여지를 위해 받지만 현재는 미사용.
    """
    if _demo_mode():
        return _local_check(prompt)

    # production 경로: boto3 호출 (Phase 2에서 구체화).
    return _bedrock_apply_guardrail(prompt, source="INPUT")


def check_output(text: str, persona_id: Optional[str] = None) -> GuardrailResult:
    """Bedrock Guardrails 출력 필터 + balance score 검증.

    Returns:
        - `passed=False`: 차단됨 - 응답 전달 금지
        - `passed=True` + `blocked_topics`에 `low_balance_score:<n>` 항목: 알람만,
          응답은 전달하되 UI에 노란색 경고 표시
    """
    base = _local_check(text) if _demo_mode() else _bedrock_apply_guardrail(text, source="OUTPUT")
    if not base.passed:
        return base
    score, _ = political_balance_score(text)
    if score < ALARM_THRESHOLD:
        return GuardrailResult(
            passed=True,
            blocked_topics=[f"low_balance_score:{score:.2f}"],
            redacted_text=base.redacted_text,
        )
    return base


def _local_check(text: str) -> GuardrailResult:
    """오프라인 휴리스틱 검사. 정당 비방 결합 패턴 차단."""
    blocked: list[str] = []
    for pattern in PARTY_ATTACK_PATTERNS:
        if pattern.search(text):
            blocked.append("party_attack")
            break
    return GuardrailResult(passed=not blocked, blocked_topics=blocked)


def _bedrock_apply_guardrail(text: str, source: str) -> GuardrailResult:
    """Bedrock Guardrails 호출 stub.

    Phase 2에서 실제 boto3 `bedrock-runtime.apply_guardrail` 호출로 교체.
    현재는 로컬 휴리스틱 fallback.
    """
    # TODO Phase 2: boto3 호출 구현
    # from api.aws_clients import session as boto_session
    # from api.config import settings
    # client = boto_session().client("bedrock-runtime")
    # resp = client.apply_guardrail(
    #     guardrailIdentifier=settings.bedrock_guardrail_id,
    #     guardrailVersion="DRAFT",
    #     source=source,
    #     content=[{"text": {"text": text}}],
    # )
    # parse and return GuardrailResult(...)
    return _local_check(text)


def _demo_mode() -> bool:
    """DEMO_PUBLIC_MODE는 라이브 시연·로컬 테스트용 우회."""
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"


# ─── 응답 어노테이션 헬퍼 ─────────────────────────────────────────────────

def annotate_response(text: str, persona_id: Optional[str] = None) -> dict:
    """LLM 응답에 첨부할 메타데이터 dict 반환.

    SSE `final` event의 `data` 필드에 그대로 머지 가능한 형태.

    Returns:
        {
          "political_balance_score": 0.85,
          "balance_components": {...},
          "guardrail_passed": True,
          "alarm": False,
          "alarm_reason": None,
        }
    """
    score, components = political_balance_score(text)
    result = check_output(text, persona_id)
    alarm = score < ALARM_THRESHOLD
    return {
        "political_balance_score": round(score, 3),
        "balance_components": {
            "party_mention_balance": round(components.party_mention_balance, 3),
            "citation_score": round(components.citation_score, 3),
            "assertion_penalty": round(components.assertion_penalty, 3),
            "parties_mentioned": components.parties_mentioned,
            "total_party_mentions": components.total_party_mentions,
            "citation_count": components.citation_count,
            "assertion_count": components.assertion_count,
        },
        "guardrail_passed": result.passed,
        "alarm": alarm,
        "alarm_reason": "low_balance_score" if alarm else None,
    }
