"""시나리오 B - 3-stage 진화 챗봇 라우터.

엔드포인트:
- POST /api/chat          단일 모드 또는 3 모드 비교 (`mode` 파라미터, 동기)
- POST /api/chat/stream   3 모드 비교 SSE 스트림 (Phase 5 Track 5-5)
- GET  /api/chat/modes    사용 가능한 모드 목록

페르소나는 `X-Persona-Id` 헤더로 전달. 누락 시 editorial fallback.

SSE 이벤트 어휘:
- phase   stage 시작 알림 ({stage, status})
- log     도구·에이전트 호출 trace ({stage, tool_called|agent_invoked})
- result  한 stage 완료 결과 ({stage, ...StageResult})
- done    전체 완료 ({total_ms})
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Literal, Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.services import three_stage

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """POST /api/chat 요청."""
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["chatbot", "agent", "agentic", "compare"] = "compare"
    scenario_code: str = Field(default="B", pattern=r"^[A-N]$")


class StageResultModel(BaseModel):
    """StageResult Pydantic 직렬화 형식."""
    stage: str
    text: str
    sources_used: list[dict] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    agents_invoked: list[str] = Field(default_factory=list)
    political_balance_score: float
    alarm: bool
    duration_ms: int
    extras: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    mode: str
    persona_id: str
    query: str
    scenario_code: str
    results: dict[str, StageResultModel]


@router.post("", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> ChatResponse:
    """3-stage 챗봇.

    - mode=compare: Chatbot + Agent + Agentic 3 모드 모두 실행 (데모 메인)
    - mode=chatbot|agent|agentic: 단일 모드만 실행
    """
    pid = x_persona_id or "editorial"

    if req.mode == "compare":
        results = three_stage.run_all_stages(req.query, persona_id=pid)
    elif req.mode == "chatbot":
        results = {"chatbot": three_stage.stage1_chatbot(req.query, pid)}
    elif req.mode == "agent":
        results = {"agent": three_stage.stage2_agent(req.query, pid)}
    else:  # agentic
        results = {"agentic": three_stage.stage3_agentic(req.query, pid)}

    return ChatResponse(
        mode=req.mode,
        persona_id=pid,
        query=req.query,
        scenario_code=req.scenario_code,
        results={k: StageResultModel(**v.to_dict()) for k, v in results.items()},
    )


@router.get("/modes")
def list_modes() -> dict:
    """사용 가능한 챗 모드 목록."""
    return {
        "modes": [
            {"id": "chatbot", "name": "Chatbot (RAG)", "approach": "단순 검색 + 요약"},
            {"id": "agent", "name": "Agent (Tool Use)", "approach": "사전 정의 도구 순차 호출"},
            {"id": "agentic", "name": "Agentic AI", "approach": "4 에이전트 자율 협업"},
            {"id": "compare", "name": "3 모드 비교", "approach": "위 3개 모두 실행 (데모 메인)"},
        ]
    }


# ─── SSE Streaming (Phase 5 Track 5-5) ──────────────────────────────────────

@router.post("/stream")
def chat_stream(
    req: ChatRequest,
    x_persona_id: Optional[str] = Header(default="editorial", alias="X-Persona-Id"),
) -> EventSourceResponse:
    """3-stage 비교 SSE 스트림.

    데모 메인: 각 stage가 한 번에 한 단계씩 나타남. Stage 2는 도구 4개 호출이
    log로 노출, Stage 3는 4 에이전트(planner/graph/analyst/editor) 순차 출현.
    """
    pid = x_persona_id or "editorial"

    async def event_gen() -> AsyncIterator[dict]:
        import time
        import traceback
        t0 = time.monotonic()
        # mode 분기: compare(default 3-stage) | chatbot | agent | agentic (single stage)
        run_chatbot = req.mode in ("chatbot", "compare")
        run_agent   = req.mode in ("agent", "compare")
        run_agentic = req.mode in ("agentic", "compare")
        try:
            # ─── Stage 1: Chatbot (RAG) ────────────────────────────────────
            if run_chatbot:
                yield _sse("phase", {"stage": "chatbot", "status": "starting",
                                     "approach": "RAG"})
                await asyncio.sleep(0.02)
                r1 = three_stage.stage1_chatbot(req.query, persona_id=pid)
                async for chunk in _stream_text(r1.text):
                    yield _sse("delta", {"stage": "chatbot", "text": chunk})
                yield _sse("result", {"stage": "chatbot", **r1.to_dict()})

            # ─── Stage 2: Agent (Tool Use) ─────────────────────────────────
            if run_agent:
                yield _sse("phase", {"stage": "agent", "status": "starting",
                                     "approach": "Tool Use (사전 정의)"})
                for tool in ("search_bills", "get_proposers", "cosponsor_network", "analyze_votes"):
                    yield _sse("log", {"stage": "agent", "tool_called": tool})
                    await asyncio.sleep(0.04)
                r2 = three_stage.stage2_agent(req.query, persona_id=pid)
                async for chunk in _stream_text(r2.text):
                    yield _sse("delta", {"stage": "agent", "text": chunk})
                yield _sse("result", {"stage": "agent", **r2.to_dict()})

            # ─── Stage 3: Agentic (Multi-Agent) ────────────────────────────
            if run_agentic:
                yield _sse("phase", {"stage": "agentic", "status": "starting",
                                     "approach": "Multi-Agent (Planner/Graph/Analyst/Editor)"})
                for agent in ("planner", "graph", "analyst", "editor"):
                    yield _sse("log", {"stage": "agentic", "agent_invoked": agent})
                    await asyncio.sleep(0.06)
                r3 = three_stage.stage3_agentic(req.query, persona_id=pid)
                async for chunk in _stream_text(r3.text):
                    yield _sse("delta", {"stage": "agentic", "text": chunk})
                yield _sse("result", {"stage": "agentic", **r3.to_dict()})

            yield _sse("done", {"total_ms": int((time.monotonic() - t0) * 1000),
                                "persona_id": pid, "query": req.query})
        except Exception as exc:  # final emit try/except: mid-stream 예외 → connection close 모호성 제거
            tb = traceback.format_exc()
            # CloudWatch 로그 + 클라이언트 final 동시 보장
            import logging
            logging.exception("chat_stream failed: %s", exc)
            yield _sse("error", {"message": str(exc), "trace": tb[-2000:]})
            yield _sse("done", {"total_ms": int((time.monotonic() - t0) * 1000),
                                "persona_id": pid, "query": req.query, "aborted": True})

    return EventSourceResponse(event_gen())


async def _stream_text(full_text: str, chunk: int = 16, sleep: float = 0.015) -> AsyncIterator[str]:
    """텍스트를 토큰-급 chunk로 흘려보내 CloudFront keep-alive 카운터 reset.

    실제 Bedrock converse_stream contentBlockDelta는 services.bedrock.invoke_stream에 구현.
    /stream 라우터에서는 three_stage가 동기적으로 전체 텍스트를 반환하므로 chunk 시뮬레이션.
    """
    for i in range(0, len(full_text), chunk):
        yield full_text[i:i + chunk]
        await asyncio.sleep(sleep)


def _sse(event: str, data: dict) -> dict:
    """sse-starlette 형식: {"event": "...", "data": "..."}"""
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}
