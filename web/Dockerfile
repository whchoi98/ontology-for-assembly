# syntax=docker/dockerfile:1.7

# Next.js 14 App Router (standalone) - Fargate ARM64.
# next.config.js의 `output: 'standalone'`이 .next/standalone/ 자급 번들 생성.

FROM --platform=linux/arm64 node:20-slim AS deps

WORKDIR /app

# 의존성 설치
COPY web/package.json web/package-lock.json* ./
RUN npm ci --omit=dev=false --no-audit --no-fund


FROM --platform=linux/arm64 node:20-slim AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# 의존성 layer 재활용
COPY --from=deps /app/node_modules ./node_modules
COPY web/ ./

# 빌드
RUN npm run build


FROM --platform=linux/arm64 node:20-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# 비루트 사용자
RUN groupadd -g 10001 nodeapp && \
    useradd -u 10001 -g nodeapp -m -s /bin/bash nodeapp

# standalone 번들 + 정적 자산 + public/ (KOSTAT GeoJSON 7.5MB 등)
# 사용자 신고: 지역구 지도 SVG empty — Next.js standalone은 public/ 자동 포함 X.
COPY --from=builder --chown=nodeapp:nodeapp /app/.next/standalone ./
COPY --from=builder --chown=nodeapp:nodeapp /app/.next/static ./.next/static
COPY --from=builder --chown=nodeapp:nodeapp /app/public ./public

USER nodeapp

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/api/healthz', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
