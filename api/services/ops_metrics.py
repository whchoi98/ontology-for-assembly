"""운영 메트릭 - LLM 호출 trace ring buffer + 가드레일 통계.

bedrock.invoke()가 매 호출마다 record_trace를 호출해 최근 N개 LLM 호출의
메타데이터(persona, scenario, score, alarm, blocked_topics)를 보관.
운영 콘솔의 trace·guardrail 패널이 이 버퍼를 읽음.

References:
- spec §7 ops_metrics 컴포넌트
- ADR-0004 Layer 3 (political_balance_score 메트릭)
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

__all__ = [
    "TraceEntry",
    "GuardrailCounters",
    "record_trace",
    "get_recent_traces",
    "get_guardrail_counters",
    "reset",
    "BUFFER_SIZE",
]

# 링버퍼 크기. PoC 적정 - production은 CloudWatch Logs로 export 후 비움.
BUFFER_SIZE = 100


@dataclass(frozen=True)
class TraceEntry:
    """LLM 호출 trace - 운영 콘솔 panel에 노출되는 단위."""
    ts_iso: str
    persona_id: str
    scenario_code: str
    model_id: str
    political_balance_score: float
    alarm: bool
    alarm_reason: Optional[str]
    blocked_topics: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class GuardrailCounters:
    """가드레일 호출 통계 - 누적."""
    total_invocations: int = 0
    total_blocked: int = 0
    total_alarms_low_balance: int = 0
    avg_balance_score: float = 1.0
    blocked_by_topic: dict[str, int] = field(default_factory=dict)


# ─── 내부 상태 (thread-safe) ─────────────────────────────────────────────────

_lock = Lock()
_trace_buf: deque[TraceEntry] = deque(maxlen=BUFFER_SIZE)
_counters = GuardrailCounters()


# ─── 공개 API ───────────────────────────────────────────────────────────────

def record_trace(
    persona_id: str,
    scenario_code: str,
    model_id: str,
    political_balance_score: float,
    alarm: bool,
    alarm_reason: Optional[str] = None,
    blocked_topics: Optional[list[str]] = None,
    duration_ms: int = 0,
) -> TraceEntry:
    """LLM 호출 trace 1건 기록. bedrock.invoke()가 매 호출 시 호출.

    Returns: 생성된 TraceEntry (테스트·디버깅용).
    """
    entry = TraceEntry(
        ts_iso=_now_iso(),
        persona_id=persona_id,
        scenario_code=scenario_code,
        model_id=model_id,
        political_balance_score=political_balance_score,
        alarm=alarm,
        alarm_reason=alarm_reason,
        blocked_topics=list(blocked_topics or []),
        duration_ms=duration_ms,
    )

    with _lock:
        _trace_buf.append(entry)

        # Guardrail 카운터 갱신
        _counters.total_invocations += 1
        if blocked_topics:
            _counters.total_blocked += 1
            for t in blocked_topics:
                _counters.blocked_by_topic[t] = _counters.blocked_by_topic.get(t, 0) + 1
        if alarm and alarm_reason == "low_balance_score":
            _counters.total_alarms_low_balance += 1
        # running average
        n = _counters.total_invocations
        _counters.avg_balance_score = (
            (_counters.avg_balance_score * (n - 1) + political_balance_score) / n
        )

    return entry


def get_recent_traces(limit: int = 20) -> list[TraceEntry]:
    """최근 trace N개 (최신 우선)."""
    with _lock:
        return list(_trace_buf)[-limit:][::-1]


def get_guardrail_counters() -> GuardrailCounters:
    """누적 가드레일 카운터 - copy 반환 (외부 mutation 방지)."""
    with _lock:
        return GuardrailCounters(
            total_invocations=_counters.total_invocations,
            total_blocked=_counters.total_blocked,
            total_alarms_low_balance=_counters.total_alarms_low_balance,
            avg_balance_score=_counters.avg_balance_score,
            blocked_by_topic=dict(_counters.blocked_by_topic),
        )


def reset() -> None:
    """테스트·시연 리허설용 - 버퍼·카운터 초기화."""
    global _counters
    with _lock:
        _trace_buf.clear()
        _counters = GuardrailCounters()


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
