"""시나리오 B - 3-stage 진화 챗봇 라우터.

엔드포인트:
- POST /api/chat         단일 모드 또는 3 모드 비교 (`mode` 파라미터)
- GET  /api/chat/modes   사용 가능한 모드 목록

페르소나는 `X-Persona-Id` 헤더로 전달. 누락 시 editorial fallback.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

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
