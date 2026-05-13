.PHONY: help install test test-fast lint type-check ast cdk-synth cdk-test wow-eval clean

help:
	@echo "ontology-for-assembly - 주요 명령"
	@echo "  install        - Python + Node 의존성 설치"
	@echo "  test           - pytest 전체 스위트"
	@echo "  test-fast      - smoke + ast (1초 이하)"
	@echo "  lint           - ruff lint"
	@echo "  type-check     - mypy (Python) + tsc (TS)"
	@echo "  ast            - python compileall AST 검증"
	@echo "  cdk-synth      - CDK synth 6 stacks"
	@echo "  cdk-test       - Jest 스냅샷 테스트"
	@echo "  wow-eval       - 14 시나리오 × 6 페르소나 wow 쿼리 평가 (배포 후 사용)"
	@echo "  clean          - .venv, node_modules, cdk.out 정리"

install:
	python3 -m venv .venv && \
		.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	cd web && npm ci
	cd infra-cdk && npm ci

test:
	pytest tests -q

test-fast:
	python3 -m compileall -q api data scripts
	pytest tests/test_smoke.py -q

lint:
	ruff check api data scripts tests

type-check:
	cd web && npx tsc --noEmit
	cd infra-cdk && npx tsc --noEmit
	mypy api --ignore-missing-imports

ast:
	python3 -m compileall -q api data scripts

cdk-synth:
	cd infra-cdk && npx cdk synth --quiet

cdk-test:
	cd infra-cdk && npx jest --ci

wow-eval:
	python3 scripts/eval_wow_queries.py

clean:
	rm -rf .venv web/node_modules infra-cdk/node_modules infra-cdk/cdk.out
	find . -type d -name __pycache__ -exec rm -rf {} +
