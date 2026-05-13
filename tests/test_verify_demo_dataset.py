"""scripts/verify_demo_dataset.py 검증 스크립트의 self-test.

`emit_synthetic_local + emit_real_local + emit_external_local`로 데이터셋을
생성한 뒤 검증 스크립트가 통과하는지 확인.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "verify_demo_dataset.py"


@pytest.fixture(scope="module")
def verify_module():
    """scripts/verify_demo_dataset.py를 모듈로 로드."""
    spec = importlib.util.spec_from_file_location("verify_demo_dataset", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demo_dataset(tmp_path_factory):
    """전체 데모 데이터셋 한 번 생성하여 module 단위로 재사용.

    real 어댑터는 max_rows를 비제한(None)으로 두어 cross-reference 무결성 검사
    (vote → bill, ad_inventory → ad) 통과를 보장. mock fixture 총 row가 작아
    full 적재해도 빠름.
    """
    out = tmp_path_factory.mktemp("demo")
    from data import load
    load.emit_synthetic_local(
        out_dir=out, article_count=20, reader_count=50, ad_count=10, verbose=False,
    )
    load.emit_real_local(
        out_dir=out, max_bills=None, max_members=None, max_votes=None, verbose=False,
    )
    load.emit_external_local(
        out_dir=out, news_count=5, poll_count=10, verbose=False,
    )
    return out


def test_check_files_exist_passes(verify_module, demo_dataset):
    ok, missing = verify_module.check_files_exist(demo_dataset)
    assert ok, f"누락 파일: {missing}"


def test_check_pydantic_round_trip(verify_module, demo_dataset):
    ok, errors = verify_module.check_pydantic_round_trip(demo_dataset)
    assert ok, f"Pydantic 검증 실패: {errors}"


def test_check_source_tagging(verify_module, demo_dataset):
    ok, errors = verify_module.check_source_tagging(demo_dataset)
    assert ok, f"source 태깅 오류: {errors}"


def test_check_article_political_balance(verify_module, demo_dataset):
    """모든 article 본문이 ALARM_THRESHOLD(0.8) 통과."""
    ok, low = verify_module.check_article_political_balance(demo_dataset)
    assert ok, f"임계 미달: {low}"


def test_check_cross_reference_integrity(verify_module, demo_dataset):
    """vote.bill_id → bill, ad_inventory.ad_id → ad 참조 무결성."""
    ok, errors = verify_module.check_cross_reference_integrity(demo_dataset)
    assert ok, f"참조 무결성 오류: {errors}"


def test_run_all_checks_returns_zero(verify_module, demo_dataset):
    """전체 검증 통과 시 exit code 0."""
    rc = verify_module.run_all_checks(demo_dataset)
    assert rc == 0


def test_run_all_checks_on_missing_dir_returns_two(verify_module, tmp_path):
    """존재하지 않는 디렉토리 입력 시 main()은 exit code 2."""
    missing = tmp_path / "nonexistent"
    rc = verify_module.main([str(missing)])
    assert rc == 2
