"""FastAPI 애플리케이션 엔트리포인트.

시나리오 라우터를 한 곳에 등록. 새 라우터 추가 시 `_register_routers()`에 한 줄 추가.

References:
- CLAUDE.md "Auto-Sync Rules" - 새 시나리오 추가 시 9곳 동시 수정 중 #4
- spec §2 프로젝트 구조
"""
from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리. 테스트에서도 동일 함수 사용."""
    app = FastAPI(
        title="ontology-for-assembly API",
        version="0.1.0",
        description=(
            "한국 언론사 Agentic 온톨로지 PoC - 14 시나리오(A–N) × 6 페르소나.\n"
            "차용 베이스: ontology-for-gcc (https://github.com/whchoi98/ontology-for-gcc)"
        ),
    )

    _register_routers(app)
    _register_health(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """시나리오 라우터 등록 한 곳에 모음.

    Auto-Sync 체크: 새 시나리오 라우터 추가 시 이 함수에 한 줄 추가.
    """
    # 시나리오 A - 의미 검색
    from api.routers.search import router as search_router
    app.include_router(search_router)

    # 시나리오 B - 3-stage 챗봇
    from api.routers.chat import router as chat_router
    app.include_router(chat_router)

    # 향후 시나리오 라우터들:
    # from api.routers.insights import router as insights_router; app.include_router(insights_router) # C
    # ... (D-N 그리고 objects, ontology, personas, ops)


def _register_health(app: FastAPI) -> None:
    """헬스 체크 - ALB target group, CloudFront origin probe."""
    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok", "service": "ontology-for-assembly", "version": app.version}

    @app.get("/api/healthz", tags=["ops"])
    def api_healthz() -> dict:
        return {"status": "ok", "service": "api"}


# 모듈 레벨 app 인스턴스 — uvicorn `api.main:app` 진입점.
app = create_app()
