# syntax=docker/dockerfile:1.7

# API + 일회성 데이터 로더 겸용 (ADR-0001 D5).
# - uvicorn(default): FastAPI 14 시나리오 + ops + objects
# - python -m data.load (one-shot ECS task): Neptune + OpenSearch 적재
# ARM64 (Graviton) — `--platform linux/arm64` 강제.

FROM --platform=linux/arm64 python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 시스템 패키지 최소
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 layer 먼저 (캐시 효율)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드
COPY api/ ./api/
COPY data/ ./data/
COPY ontology/ ./ontology/

# 비루트 사용자
RUN useradd -m -u 10001 -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD curl -fsS http://localhost:8080/healthz || exit 1

# 기본 명령: API 서버. one-shot 로더는 ECS task override로 변경.
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "2", \
     "--log-level", "info", \
     "--proxy-headers"]
