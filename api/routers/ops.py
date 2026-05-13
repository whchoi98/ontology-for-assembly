"""운영 콘솔 라우터 - 5 패널 (Phase 5 Track 5-2).

엔드포인트:
- GET /api/ops/ingest       적재 상태 (NDJSON 파일 수, source 분포)
- GET /api/ops/guardrail    가드레일 누적 통계 + 알람 카운트
- GET /api/ops/memory       AgentCore Memory store 상태 (PoC 한정)
- GET /api/ops/wow-quality  wow-query 최근 평가 결과 (84 케이스)
- GET /api/ops/trace        최근 LLM 호출 ring buffer (live 갱신)

각 패널은 시연자가 데이터·가드레일·LLM 동작을 한눈에 확인하는 용도.

References:
- spec §7 운영 콘솔 5 패널
- ADR-0004 Layer 3 (메트릭 자동 노출)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.services import ops_metrics

router = APIRouter(prefix="/api/ops", tags=["ops"])


# ─── Response 모델 ──────────────────────────────────────────────────────────

class IngestPanel(BaseModel):
    output_dir: Optional[str]
    last_updated: Optional[str]
    file_counts: dict[str, int]
    source_distribution: dict[str, int]
    note: str


class GuardrailPanel(BaseModel):
    total_invocations: int
    total_blocked: int
    total_alarms_low_balance: int
    avg_balance_score: float
    blocked_by_topic: dict[str, int]
    threshold: float


class MemoryPanel(BaseModel):
    store_id: Optional[str]
    active_sessions_estimate: int
    namespaces: list[str]
    note: str


class QualityPanel(BaseModel):
    last_run_iso: Optional[str]
    total_cases: int
    pass_count: int
    pass_rate: float
    avg_balance_score: Optional[float]
    note: str


class TraceEntryModel(BaseModel):
    ts_iso: str
    persona_id: str
    scenario_code: str
    model_id: str
    political_balance_score: float
    alarm: bool
    alarm_reason: Optional[str]
    blocked_topics: list[str]
    duration_ms: int


class TracePanel(BaseModel):
    buffer_size: int
    entries: list[TraceEntryModel]


# ─── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.get("/ingest", response_model=IngestPanel)
def panel_ingest() -> IngestPanel:
    """패널 1: 데이터 적재 상태 - data/output/ 디렉토리 스캔."""
    out_dir = Path(os.environ.get("DATA_OUTPUT_DIR", "data/output"))
    file_counts: dict[str, int] = {}
    source_distribution: dict[str, int] = {}
    last_updated: Optional[str] = None

    if out_dir.is_dir():
        for f in sorted(out_dir.glob("*.ndjson")):
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
                file_counts[f.stem] = sum(1 for ln in lines if ln.strip())
                # source 분포 - 첫 50줄만 sampling.
                if lines:
                    import json as _json
                    for ln in lines[:50]:
                        try:
                            obj = _json.loads(ln)
                            src = obj.get("source")
                            if src:
                                source_distribution[src] = source_distribution.get(src, 0) + 1
                        except _json.JSONDecodeError:
                            pass
                stat = f.stat()
                ts = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                if last_updated is None or ts > last_updated:
                    last_updated = ts
            except OSError:
                pass

    return IngestPanel(
        output_dir=str(out_dir.absolute()) if out_dir.is_dir() else None,
        last_updated=last_updated,
        file_counts=file_counts,
        source_distribution=source_distribution,
        note=(
            "data/output/ NDJSON 카운트. 빈 디렉토리면 `python -m data.load --source all --demo` 실행."
        ),
    )


@router.get("/guardrail", response_model=GuardrailPanel)
def panel_guardrail() -> GuardrailPanel:
    """패널 2: 가드레일 누적 통계 (ops_metrics 링버퍼 기반)."""
    from api.services.guardrails import ALARM_THRESHOLD
    counters = ops_metrics.get_guardrail_counters()
    return GuardrailPanel(
        total_invocations=counters.total_invocations,
        total_blocked=counters.total_blocked,
        total_alarms_low_balance=counters.total_alarms_low_balance,
        avg_balance_score=round(counters.avg_balance_score, 3),
        blocked_by_topic=counters.blocked_by_topic,
        threshold=ALARM_THRESHOLD,
    )


@router.get("/memory", response_model=MemoryPanel)
def panel_memory() -> MemoryPanel:
    """패널 3: AgentCore Memory 상태 - PoC는 환경변수 + 추정."""
    store_id = os.environ.get("AGENTCORE_MEMORY_ID") or None
    traces = ops_metrics.get_recent_traces(limit=ops_metrics.BUFFER_SIZE)
    sessions_estimate = len({(t.persona_id, t.scenario_code) for t in traces})
    return MemoryPanel(
        store_id=store_id,
        active_sessions_estimate=sessions_estimate,
        namespaces=["staff", "subscriber", "guest"],
        note=(
            "PoC: 활성 세션은 최근 trace 버퍼의 distinct persona·scenario 조합 추정. "
            "Production: AgentCore Memory API로 실제 세션 카운트."
        ),
    )


@router.get("/wow-quality", response_model=QualityPanel)
def panel_wow_quality() -> QualityPanel:
    """패널 4: wow-query 최근 평가 결과 - .harness-eval/latest.json 읽기."""
    quality_path = Path(".harness-eval/latest.json")
    if quality_path.is_file():
        import json as _json
        try:
            data = _json.loads(quality_path.read_text(encoding="utf-8"))
            return QualityPanel(
                last_run_iso=data.get("run_iso"),
                total_cases=data.get("total_cases", 0),
                pass_count=data.get("pass_count", 0),
                pass_rate=data.get("pass_rate", 0.0),
                avg_balance_score=data.get("avg_balance_score"),
                note="latest.json 기반.",
            )
        except _json.JSONDecodeError:
            pass

    return QualityPanel(
        last_run_iso=None,
        total_cases=0,
        pass_count=0,
        pass_rate=0.0,
        avg_balance_score=None,
        note=(
            "아직 wow-query 평가 실행되지 않음. `python scripts/eval_wow_queries.py`로 "
            "84 케이스 실행 후 .harness-eval/latest.json 생성."
        ),
    )


@router.get("/trace", response_model=TracePanel)
def panel_trace(
    limit: int = Query(default=20, ge=1, le=100),
) -> TracePanel:
    """패널 5: 최근 LLM 호출 trace 링버퍼 (최신 우선)."""
    entries = ops_metrics.get_recent_traces(limit=limit)
    return TracePanel(
        buffer_size=ops_metrics.BUFFER_SIZE,
        entries=[
            TraceEntryModel(
                ts_iso=e.ts_iso,
                persona_id=e.persona_id,
                scenario_code=e.scenario_code,
                model_id=e.model_id,
                political_balance_score=e.political_balance_score,
                alarm=e.alarm,
                alarm_reason=e.alarm_reason,
                blocked_topics=e.blocked_topics,
                duration_ms=e.duration_ms,
            )
            for e in entries
        ],
    )
