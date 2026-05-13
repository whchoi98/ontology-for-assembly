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


# ─── 미구현 stub ────────────────────────────────────────────────────────────

def test_emit_synthetic_s3_not_implemented():
    """S3 emit은 Phase 3."""
    with pytest.raises(NotImplementedError, match="Phase 3"):
        load.emit_synthetic_s3(bucket="fake-bucket")


# external 어댑터는 Phase 2 Track 2-3 완료 (emit_external_local 함수로 대체).


def test_emit_external_local_writes_two_files(tmp_path: Path):
    counts = load.emit_external_local(out_dir=tmp_path, news_count=5, poll_count=10, verbose=False)
    actual = {p.name for p in tmp_path.iterdir() if p.suffix == ".ndjson"}
    assert actual == {"social_signals.ndjson", "poll_results.ndjson"}
    assert counts["social_signal"] >= 1
    assert counts["poll_result"] == 10


def test_cli_external_source_runs(tmp_path: Path):
    """--source external 정상 동작 (Track 2-3 완료 후)."""
    rc = load.main([
        "--source", "external",
        "--demo",
        "--out-dir", str(tmp_path),
        "--news-count", "5",
        "--poll-count", "10",
        "--quiet",
    ])
    assert rc == 0
    assert (tmp_path / "social_signals.ndjson").exists()
    assert (tmp_path / "poll_results.ndjson").exists()


# ─── emit_real_local (Phase 2 Track 2-2 신규) ──────────────────────────────

def test_emit_real_local_writes_eight_files(tmp_path: Path):
    """8 NDJSON: bills, members, votes, committees, sessions, statements, parties, agencies."""
    counts = load.emit_real_local(out_dir=tmp_path, verbose=False)
    expected = {
        "bills.ndjson", "members.ndjson", "votes.ndjson",
        "committees.ndjson", "sessions.ndjson", "statements.ndjson",
        "parties.ndjson", "agencies.ndjson",
    }
    actual = {p.name for p in tmp_path.iterdir() if p.suffix == ".ndjson"}
    assert expected == actual


def test_emit_real_local_counts_returned(tmp_path: Path):
    counts = load.emit_real_local(out_dir=tmp_path, verbose=False)
    for key in ("bill", "member", "vote", "committee", "session", "statement",
                "party", "agency"):
        assert key in counts
        assert counts[key] >= 1


def test_emit_real_local_max_rows_limit(tmp_path: Path):
    counts = load.emit_real_local(
        out_dir=tmp_path,
        max_bills=3,
        max_members=4,
        max_votes=5,
        verbose=False,
    )
    assert counts["bill"] == 3
    assert counts["member"] == 4
    assert counts["vote"] == 5


def test_emit_real_local_ndjson_round_trip(tmp_path: Path):
    """real 어댑터 NDJSON → Pydantic round-trip."""
    from data.schemas import Bill, Person, Vote
    load.emit_real_local(out_dir=tmp_path, max_bills=2, max_members=2, max_votes=2, verbose=False)
    bills = [
        Bill.model_validate_json(line)
        for line in (tmp_path / "bills.ndjson").read_text().splitlines()
    ]
    members = [
        Person.model_validate_json(line)
        for line in (tmp_path / "members.ndjson").read_text().splitlines()
    ]
    votes = [
        Vote.model_validate_json(line)
        for line in (tmp_path / "votes.ndjson").read_text().splitlines()
    ]
    assert all(b.source == "real" for b in bills)
    assert all(m.source == "real" for m in members)
    assert all(v.source == "real" for v in votes)


def test_cli_real_source_runs(tmp_path: Path):
    """`--source real` 정상 동작 (Phase 2 Track 2-2 완료 후)."""
    rc = load.main([
        "--source", "real",
        "--out-dir", str(tmp_path),
        "--max-bills", "3",
        "--max-members", "3",
        "--max-votes", "3",
        "--quiet",
    ])
    assert rc == 0
    assert (tmp_path / "bills.ndjson").exists()
    assert (tmp_path / "members.ndjson").exists()
    assert (tmp_path / "votes.ndjson").exists()


def test_cli_all_source_runs(tmp_path: Path):
    """`--source all` synthetic + real + external 모두 출력 (15 NDJSON 파일)."""
    rc = load.main([
        "--source", "all",
        "--demo",
        "--out-dir", str(tmp_path),
        "--article-count", "5",
        "--reader-count", "10",
        "--ad-count", "3",
        "--news-count", "5",
        "--poll-count", "10",
        "--quiet",
    ])
    assert rc == 0
    # synthetic 5 + real 8 + external 2 = 15 files
    expected_files = {
        "topics.ndjson", "articles.ndjson", "readers.ndjson",
        "advertisements.ndjson", "ad_inventories.ndjson",
        "bills.ndjson", "members.ndjson", "votes.ndjson",
        "committees.ndjson", "sessions.ndjson", "statements.ndjson",
        "parties.ndjson", "agencies.ndjson",
        "social_signals.ndjson", "poll_results.ndjson",
    }
    actual_files = {p.name for p in tmp_path.iterdir() if p.suffix == ".ndjson"}
    assert expected_files == actual_files




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
