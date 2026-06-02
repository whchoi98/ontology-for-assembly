#!/usr/bin/env bash
# 새 개발자 setup — 의존성 설치 + 환경 검증.
#
# Usage: bash scripts/setup.sh
#
# 이 프로젝트는 Python 3.12 + Node.js 20 multi-runtime — Python venv + npm install 모두.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "🚀 ontology-for-assembly setup (Python 3.12 + Node.js 20)"
echo ""

# 1. Python 버전 확인
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 not found. Install Python 3.12+."
  exit 1
fi
PY_VER=$(python3 --version | awk '{print $2}')
echo "  Python: $PY_VER"

# 2. Python 가상환경 (.venv)
if [ ! -d .venv ]; then
  echo "  Creating Python venv (.venv)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "  Installing requirements..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q -r requirements-dev.txt

# 3. Node.js 버전 확인
if ! command -v node >/dev/null 2>&1; then
  echo "✗ node not found. Install Node.js 20+."
  exit 1
fi
NODE_VER=$(node --version)
echo "  Node:   $NODE_VER"

# 4. web/ 의존성
if [ -d web ]; then
  echo "  Installing web/ dependencies..."
  (cd web && npm install --silent)
fi

# 5. infra-cdk/ 의존성
if [ -d infra-cdk ]; then
  echo "  Installing infra-cdk/ dependencies..."
  (cd infra-cdk && npm install --silent)
fi

# 6. .env 파일 안내
if [ ! -f .env ]; then
  echo ""
  echo "  ⚠  .env 파일 없음 — .env.example 참고하여 작성 권장:"
  echo "       cp .env.example .env"
fi

# 7. Git hooks 설치
if [ -d .git ]; then
  echo ""
  echo "  Installing Git hooks..."
  bash scripts/install-hooks.sh
fi

# 8. Smoke test
echo ""
echo "  Running pytest smoke test..."
if pytest -q tests/test_smoke.py 2>/dev/null; then
  echo "  ✓ smoke test passed"
else
  echo "  ⚠  smoke test failed — 환경 변수·외부 의존성 확인"
fi

echo ""
echo "✓ Setup 완료. 다음 단계:"
echo "  - DEMO_PUBLIC_MODE=true uvicorn api.main:app --reload  (백엔드 로컬 실행)"
echo "  - cd web && npm run dev                                 (프론트 로컬 실행)"
echo "  - make test                                              (전체 테스트)"
echo "  - docs/runbooks/01-deployment.md                         (배포 가이드)"
