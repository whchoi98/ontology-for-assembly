"""data 적재 CLI - 합성·실·외부 데이터를 통합 출력.

Phase 2 (현재): synthetic generators + local NDJSON 출력.
Phase 3 (예정): real OpenAPI 어댑터 + S3 upload + Neptune Bulk Loader.

Usage:
    # 합성 데이터 → 로컬 NDJSON
    python -m data.load --source synthetic --to local --out-dir ./data/output

    # 작은 데모용 (1k 독자, 100 기사)
    python -m data.load --source synthetic --reader-count 1000 --article-count 100

    # 일회성 ECS 태스크 (Phase 3)
    python -m data.load --source all --to s3 --bucket assembly-dev-synthetic-data

각 entity는 별도 NDJSON 파일 (Neptune Bulk Loader 호환):
    topics.ndjson · articles.ndjson · readers.ndjson · advertisements.ndjson · ad_inventories.ndjson

References:
- spec §5 데이터 파이프라인
- ADR-0001 D10 Neptune Bulk Loader 패턴
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

__all__ = ["emit_synthetic_local", "write_ndjson", "main"]


# ─── NDJSON 직렬화 ───────────────────────────────────────────────────────────

def write_ndjson(items: Iterable[BaseModel], path: Path) -> int:
    """Pydantic 모델 iterator를 NDJSON 파일로 저장.

    Returns: 기록 행 수.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")
            count += 1
    return count


# ─── 합성 데이터 통합 출력 ─────────────────────────────────────────────────

def emit_synthetic_local(
    out_dir: Path,
    *,
    article_count: int = 2000,
    reader_count: int = 50_000,
    ad_count: int = 500,
    seed: int = 20260513,
    verbose: bool = True,
) -> dict[str, int]:
    """4 generator를 NDJSON 5개 파일로 출력.

    Args:
        out_dir: 출력 디렉토리.
        article_count, reader_count, ad_count: 각 entity 개수.
        seed: 결정성 보장 seed.
        verbose: 진행 메시지 출력.

    Returns:
        {<entity_name>: count} dict.
    """
    # Lazy imports to keep CLI startup fast for --help
    from data.synthetic.advertisement import generate_ads_with_inventory
    from data.synthetic.article import generate_articles
    from data.synthetic.reader import generate_readers
    from data.synthetic.topics import to_graph_nodes as topic_nodes

    def _log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    _log(f"[topic]         writing → {out_dir}/topics.ndjson")
    counts["topic"] = write_ndjson(topic_nodes(), out_dir / "topics.ndjson")

    _log(f"[article]       generating {article_count:,} ...")
    counts["article"] = write_ndjson(
        generate_articles(count=article_count, seed=seed),
        out_dir / "articles.ndjson",
    )

    _log(f"[reader]        generating {reader_count:,} ... (this may take ~5s for 50k)")
    counts["reader"] = write_ndjson(
        generate_readers(count=reader_count, seed=seed),
        out_dir / "readers.ndjson",
    )

    _log(f"[advertisement] generating {ad_count:,} + inventory ...")
    ads, invs = generate_ads_with_inventory(count=ad_count, seed=seed)
    counts["advertisement"] = write_ndjson(ads, out_dir / "advertisements.ndjson")
    counts["ad_inventory"] = write_ndjson(invs, out_dir / "ad_inventories.ndjson")

    return counts


# ─── 미구현 stub (Phase 3) ──────────────────────────────────────────────────

def emit_synthetic_s3(bucket: str, prefix: str = "synthetic/", **kwargs) -> dict[str, int]:
    """S3 emit - Phase 3에서 구현."""
    raise NotImplementedError(
        "S3 emit은 Phase 3에서 구현. 임시로 로컬 emit 후 `aws s3 sync` 활용."
    )


def emit_real(**kwargs) -> dict[str, int]:
    """국회 OpenAPI 어댑터 - Phase 3에서 구현."""
    raise NotImplementedError(
        "real OpenAPI 어댑터는 Phase 3 (data/real/bill,member,vote)에서 구현."
    )


def emit_external(**kwargs) -> dict[str, int]:
    """네이버 뉴스·SNS·여론조사 ETL - Phase 3에서 구현."""
    raise NotImplementedError(
        "external 어댑터는 Phase 3 (data/external/naver_news 등)에서 구현."
    )


# ─── CLI ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data.load",
        description="ontology-for-assembly 데이터 적재 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[-1] if __doc__ else "",
    )
    parser.add_argument(
        "--source",
        choices=["synthetic", "real", "external", "all"],
        default="synthetic",
        help="데이터 소스 (Phase 2 = synthetic만 구현)",
    )
    parser.add_argument(
        "--to",
        choices=["local", "s3"],
        default="local",
        help="출력 대상 (Phase 2 = local만 구현)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/output"),
        help="--to local 출력 디렉토리 (기본: data/output)",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        help="--to s3 버킷명",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260513,
        help="결정성 보장 RNG seed",
    )
    parser.add_argument(
        "--article-count",
        type=int,
        default=2000,
    )
    parser.add_argument(
        "--reader-count",
        type=int,
        default=50_000,
    )
    parser.add_argument(
        "--ad-count",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="진행 메시지 출력 안 함",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. Exit code: 0=성공, 1=오류, 2=미구현."""
    args = _build_parser().parse_args(argv)
    verbose = not args.quiet

    # Phase 3 트랙 안내
    if args.source not in ("synthetic", "all"):
        print(
            f"[load] '--source {args.source}'는 Phase 3에서 구현됩니다 "
            "(data/real/, data/external/).",
            file=sys.stderr,
        )
        return 2

    if args.to == "s3":
        if not args.bucket:
            print("[load] ERROR: --to s3 requires --bucket", file=sys.stderr)
            return 1
        print(
            "[load] '--to s3'는 Phase 3에서 구현됩니다. "
            "임시로 `--to local`로 출력 후 `aws s3 sync`를 사용하세요.",
            file=sys.stderr,
        )
        return 2

    # synthetic + local
    counts = emit_synthetic_local(
        out_dir=args.out_dir,
        article_count=args.article_count,
        reader_count=args.reader_count,
        ad_count=args.ad_count,
        seed=args.seed,
        verbose=verbose,
    )

    if verbose:
        print("\n=== 적재 완료 ===")
        total = 0
        for entity, n in counts.items():
            print(f"  {entity:20s}: {n:>7,}")
            total += n
        print(f"  {'TOTAL':20s}: {total:>7,}")
        print(f"\n출력 위치: {args.out_dir.absolute()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
