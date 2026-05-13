"""스모크 import — 모듈 로드 가능 여부만 확인. 라우터 추가 시 parametrize 확장.

이 파일은 Phase 1 진행에 따라 라우터가 추가될 때마다 entry를 늘려나갑니다.
현재는 services 레이어만 import 가능. routers는 후속 단계에서 작성.
"""
from __future__ import annotations
import importlib

import pytest


# Phase 0–1 — services + schemas + routers + main 레이어 import 검증
SERVICE_MODULES = [
    "api.main",
    "api.services.persona",
    "api.services.guardrails",
    "api.services.cohort",
    "api.services.bedrock",
    "api.services.neptune",
    "api.services.opensearch",
    "api.services.three_stage",
    "api.services.multi_agent",
    "api.routers.chat",
    "data.schemas",
]


@pytest.mark.parametrize("module_path", SERVICE_MODULES)
def test_service_module_importable(module_path):
    """services 모듈이 import 가능해야 한다."""
    mod = importlib.import_module(module_path)
    assert mod is not None


# TODO Phase 1+: 라우터 추가 시 아래 확장
# ROUTER_MODULES = [
#     "api.routers.search",      # A
#     "api.routers.chat",        # B
#     "api.routers.insights",    # C
#     ... (14 시나리오 + objects + ontology + personas + ops)
# ]
# @pytest.mark.parametrize("module_path", ROUTER_MODULES)
# def test_router_module_importable(module_path):
#     mod = importlib.import_module(module_path)
#     assert mod is not None
