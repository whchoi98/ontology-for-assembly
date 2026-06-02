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

    # 시나리오 L - 광고 매칭 (AI 거버넌스 데모 메인)
    from api.routers.ad_match import router as ad_match_router
    app.include_router(ad_match_router)

    # 운영 콘솔 - 5 패널 (ingest·guardrail·memory·eval·trace)
    from api.routers.ops import router as ops_router
    app.include_router(ops_router)

    # Object Explorer + Ontology 메타 - 31 클래스 탐색기
    from api.routers.objects import router as objects_router
    app.include_router(objects_router)

    # 시나리오 K - 표결 이상치 (PDF 시그니처)
    from api.routers.outlier import router as outlier_router
    app.include_router(outlier_router)

    # 시나리오 M - 의원 정치 여정 (PDF 시그니처)
    from api.routers.journey import router as journey_router
    app.include_router(journey_router)

    # 시나리오 I - 편향·중립성 가드레일 (ADR-0004 시연)
    from api.routers.neutrality import router as neutrality_router
    app.include_router(neutrality_router)

    # 시나리오 H - 지역구 지도 (17 시도 choropleth)
    from api.routers.district_map import router as district_map_router
    app.include_router(district_map_router)

    # 시나리오 C - 기사 인사이트
    from api.routers.insights import router as insights_router
    app.include_router(insights_router)

    # 시나리오 J - 외부 신호 융합 (3 패턴 narrative)
    from api.routers.external_signal import router as external_signal_router
    app.include_router(external_signal_router)

    # 시나리오 D - 페르소나 매칭 (6 페르소나 affinity 매트릭스)
    from api.routers.persona_match import router as persona_match_router
    app.include_router(persona_match_router)

    # 시나리오 E - 의원 클러스터링 (cross-party 협력 그룹)
    from api.routers.cluster import router as cluster_router
    app.include_router(cluster_router)

    # 시나리오 F - 의원 룩어라이크
    from api.routers.lookalike import router as lookalike_router
    app.include_router(lookalike_router)

    # 시나리오 N - 이슈×입법 상관 매트릭스
    from api.routers.issue_legislation import router as issue_legislation_router
    app.include_router(issue_legislation_router)

    # 시나리오 G - 기사 ROI (페르소나별 KPI 변환)
    from api.routers.article_roi import router as article_roi_router
    app.include_router(article_roi_router)

    # 페르소나 SSOT 노출 (Sidebar·홈·GuidedTour가 fetch)
    from api.routers.personas import router as personas_router
    app.include_router(personas_router)

    # 의원 디렉토리 + 랭킹 (kassembly 패턴, 실명·사진·메트릭)
    from api.routers.members import router as members_router
    app.include_router(members_router)

    # Generic AI 인사이트 (gcc 패턴 차용, 14 시나리오 공통)
    from api.routers.insight_generic import router as insight_generic_router
    app.include_router(insight_generic_router)

    # 시나리오 O — 인물 관계 (real Neptune query)
    from api.routers.relations import router as relations_router
    app.include_router(relations_router)

    # Phase 4f — 4 신규 시나리오 (T·U·V·W) real Cypher query
    from api.routers.insights_advanced import router as insights_advanced_router
    app.include_router(insights_advanced_router)

    # 14개 시나리오 라우터 모두 등록 완료.


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
