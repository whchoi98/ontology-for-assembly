"""scripts/eval_wow_queries.py 평가 스크립트 검증 (Phase 5 Track 5-4)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "eval_wow_queries.py"


@pytest.fixture(scope="module")
def eval_module():
    import sys
    spec = importlib.util.spec_from_file_location("eval_wow_queries", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclass 필드가 모듈 namespace를 lookup하므로 sys.modules에 미리 등록.
    sys.modules["eval_wow_queries"] = module
    spec.loader.exec_module(module)
    return module


# ─── 케이스 카탈로그 ────────────────────────────────────────────────────────

def test_build_cases_returns_84(eval_module):
    """6 페르소나 × 14 시나리오 = 84 케이스."""
    cases = eval_module.build_cases()
    assert len(cases) == 84


def test_active_cases_count(eval_module):
    """Phase 4 완료 - 14/14 시나리오 모두 active = 6 페르소나 × 14 = 84 active."""
    cases = eval_module.build_cases()
    active = [c for c in cases if c.implemented]
    skipped = [c for c in cases if not c.implemented]
    assert len(active) == 84
    assert len(skipped) == 0


def test_each_persona_has_all_14_active_cases(eval_module):
    cases = eval_module.build_cases()
    expected = set("ABCDEFGHIJKLMN")
    for persona in eval_module.PERSONAS:
        active = [c for c in cases if c.persona == persona and c.implemented]
        assert len(active) == 14
        scenario_set = {c.scenario for c in active}
        assert scenario_set == expected


# ─── 케이스 실행 ────────────────────────────────────────────────────────────

def test_run_case_skipped_unimplemented(eval_module):
    """미구현 시나리오는 skipped로 반환."""
    case = eval_module.CaseDefinition(
        persona="editorial", scenario="C", query="(미구현)", implemented=False,
    )
    result = eval_module.run_case(case, base_url="http://nowhere")
    assert result.skipped is True
    assert result.passed is False
    assert "미구현" in result.reason


# ─── 집계 ───────────────────────────────────────────────────────────────────

def test_summarize_calculates_pass_rate(eval_module):
    """active 케이스 기준 pass_rate."""
    Result = eval_module.CaseResult
    results = [
        Result("editorial", "A", "q", passed=True, skipped=False, balance_score=0.9, latency_ms=10),
        Result("editorial", "B", "q", passed=True, skipped=False, balance_score=0.85, latency_ms=10),
        Result("editorial", "C", "q", passed=False, skipped=True, balance_score=1.0, latency_ms=0),
    ]
    summary = eval_module.summarize(results)
    assert summary["active_cases"] == 2
    assert summary["pass_count"] == 2
    assert summary["pass_rate"] == 1.0
    assert summary["skipped_cases"] == 1


def test_summarize_partial_failure(eval_module):
    Result = eval_module.CaseResult
    results = [
        Result("e", "A", "q", passed=True, skipped=False, balance_score=0.9, latency_ms=10),
        Result("e", "B", "q", passed=False, skipped=False, balance_score=0.5, latency_ms=10),
    ]
    summary = eval_module.summarize(results)
    assert summary["active_cases"] == 2
    assert summary["pass_count"] == 1
    assert summary["pass_rate"] == 0.5


def test_summarize_threshold_constants(eval_module):
    """PASS_RATE_THRESHOLD=0.85 / BALANCE_THRESHOLD=0.8."""
    assert eval_module.PASS_RATE_THRESHOLD == 0.85
    assert eval_module.BALANCE_THRESHOLD == 0.8


# ─── JSON 출력 ─────────────────────────────────────────────────────────────

def test_write_latest_creates_valid_json(tmp_path, eval_module):
    """write_latest는 유효한 JSON 생성 + 디렉토리 자동 생성."""
    Result = eval_module.CaseResult
    results = [
        Result("e", "A", "q", passed=True, skipped=False, balance_score=0.9, latency_ms=10),
    ]
    summary = eval_module.summarize(results)
    out_path = tmp_path / "nested" / "harness" / "latest.json"
    eval_module.write_latest(summary, out_path)
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["pass_count"] == 1
    assert "run_iso" in loaded


# ─── 통합: in-process 전체 실행 ────────────────────────────────────────────

def test_full_run_inproc_returns_zero(tmp_path, eval_module, monkeypatch):
    """in-process TestClient로 전체 실행 - 84 active 100% PASS 기대 (Phase 4 완료)."""
    monkeypatch.setenv("DEMO_PUBLIC_MODE", "true")
    out_path = tmp_path / "latest.json"
    rc = eval_module.main(["--base-url", "inproc", "--output", str(out_path), "--quiet"])
    assert rc == 0
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["active_cases"] == 84
    assert summary["pass_count"] == 84
    assert summary["pass_rate"] == 1.0
    assert summary["avg_balance_score"] >= 0.8
