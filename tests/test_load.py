"""data.load CLI 통합 검증.

테스트 범위:
- emit_synthetic_local NDJSON 출력 파일 무결성
- 각 라인 valid JSON + Pydantic 모델로 round-trip 가능
- counts 반환 값 정확
- CLI argparse 정상 동작 (--source/--to/--out-dir)
- Phase 3 stub은 NotImplementedError
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from data import load


# ─── write_ndjson ──────────────────────────────────────────────────────────

def test_write_ndjson_creates_file(tmp_path: Path):
    """NDJSON 파일이 생성되고 라인 수 정확."""
    from data.synthetic.topics import to_graph_nodes
    nodes = to_graph_nodes()
    out = tmp_path / "topics.ndjson"
    n = load.write_ndjson(nodes, out)
    assert n == 25
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 25


def test_write_ndjson_each_line_valid_json(tmp_path: Path):
    """각 라인이 valid JSON으로 파싱 가능."""
    from data.synthetic.topics import to_graph_nodes
    out = tmp_path / "topics.ndjson"
    load.write_ndjson(to_graph_nodes(), out)
    for line in out.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        assert "topic_id" in obj
        assert obj["source"] == "synthetic"


def test_write_ndjson_round_trip_pydantic(tmp_path: Path):
    """NDJSON → Pydantic 역방향 round-trip 가능."""
    from data.schemas import Article
    from data.synthetic.article import generate_articles
    out = tmp_path / "articles.ndjson"
    load.write_ndjson(generate_articles(count=5, seed=42), out)
    parsed = [Article.model_validate_json(line) for line in out.read_text().splitlines()]
    assert len(parsed) == 5
    assert all(isinstance(a, Article) for a in parsed)


def test_write_ndjson_creates_parent_dirs(tmp_path: Path):
    """중첩 디렉토리 자동 생성."""
    from data.synthetic.topics import to_graph_nodes
    out = tmp_path / "nested" / "deeper" / "topics.ndjson"
    load.write_ndjson(to_graph_nodes(), out)
    assert out.exists()


# ─── emit_synthetic_local ──────────────────────────────────────────────────

def test_emit_synthetic_local_writes_five_files(tmp_path: Path):
    """5개 NDJSON 파일 생성: topics, articles, readers, advertisements, ad_inventories."""
    counts = load.emit_synthetic_local(
        out_dir=tmp_path,
        article_count=50,
        reader_count=100,
        ad_count=20,
        verbose=False,
    )
    expected = {
        "topics.ndjson",
        "articles.ndjson",
        "readers.ndjson",
        "advertisements.ndjson",
        "ad_inventories.ndjson",
    }
    actual = {p.name for p in tmp_path.iterdir() if p.suffix == ".ndjson"}
    assert expected == actual


def test_emit_synthetic_local_counts_match(tmp_path: Path):
    """반환 counts가 실제 생성 수와 일치."""
    counts = load.emit_synthetic_local(
        out_dir=tmp_path,
        article_count=30,
        reader_count=200,
        ad_count=15,
        verbose=False,
    )
    assert counts == {
        "topic": 25,
        "article": 30,
        "reader": 200,
        "advertisement": 15,
        "ad_inventory": 15,
    }


def test_emit_synthetic_local_deterministic(tmp_path: Path):
    """같은 seed → 같은 파일 내용."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    load.emit_synthetic_local(out_dir=out1, article_count=10, reader_count=20, ad_count=5,
                              seed=42, verbose=False)
    load.emit_synthetic_local(out_dir=out2, article_count=10, reader_count=20, ad_count=5,
                              seed=42, verbose=False)
    for name in ("topics.ndjson", "articles.ndjson", "readers.ndjson",
                 "advertisements.ndjson", "ad_inventories.ndjson"):
        assert (out1 / name).read_text() == (out2 / name).read_text(), f"{name} 불일치"


# ─── Phase 3 stub ──────────────────────────────────────────────────────────

def test_emit_synthetic_s3_not_implemented():
    """S3 emit은 Phase 3."""
    with pytest.raises(NotImplementedError, match="Phase 3"):
        load.emit_synthetic_s3(bucket="fake-bucket")


def test_emit_real_not_implemented():
    with pytest.raises(NotImplementedError):
        load.emit_real()


def test_emit_external_not_implemented():
    with pytest.raises(NotImplementedError):
        load.emit_external()


# ─── CLI argparse ──────────────────────────────────────────────────────────

def test_cli_synthetic_local_runs(tmp_path: Path, capsys):
    """`python -m data.load --source synthetic --to local --out-dir ...` 통과."""
    rc = load.main([
        "--source", "synthetic",
        "--to", "local",
        "--out-dir", str(tmp_path),
        "--article-count", "10",
        "--reader-count", "20",
        "--ad-count", "5",
        "--quiet",
    ])
    assert rc == 0
    # 5개 파일 생성 확인
    assert (tmp_path / "topics.ndjson").exists()
    assert (tmp_path / "articles.ndjson").exists()
    assert (tmp_path / "readers.ndjson").exists()


def test_cli_real_source_returns_phase_3_stub(capsys, tmp_path: Path):
    """--source real은 exit code 2 (Phase 3 안내)."""
    rc = load.main(["--source", "real", "--out-dir", str(tmp_path)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Phase 3" in captured.err


def test_cli_s3_target_returns_phase_3_stub(capsys, tmp_path: Path):
    """--to s3는 exit code 2 (Phase 3 안내)."""
    rc = load.main([
        "--source", "synthetic",
        "--to", "s3",
        "--bucket", "test-bucket",
    ])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Phase 3" in captured.err


def test_cli_s3_without_bucket_errors(capsys):
    """--to s3 + --bucket 누락 시 exit code 1."""
    rc = load.main(["--source", "synthetic", "--to", "s3"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "--bucket" in captured.err


def test_cli_help_does_not_fail():
    """--help는 SystemExit(0)으로 종료."""
    with pytest.raises(SystemExit) as exc:
        load.main(["--help"])
    assert exc.value.code == 0


# ─── 통합 (subprocess) ─────────────────────────────────────────────────────

def test_cli_via_module_invocation(tmp_path: Path):
    """`python -m data.load ...`이 실제로 동작."""
    result = subprocess.run(
        [
            sys.executable, "-m", "data.load",
            "--source", "synthetic",
            "--out-dir", str(tmp_path),
            "--article-count", "5",
            "--reader-count", "10",
            "--ad-count", "3",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,  # repo root
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_path / "topics.ndjson").exists()
