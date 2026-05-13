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


# ─── 국회 OpenAPI 어댑터 통합 ───────────────────────────────────────────────

def emit_real_local(
    out_dir: Path,
    *,
    max_bills: int | None = None,
    max_members: int | None = None,
    max_votes: int | None = None,
    max_committees: int | None = None,
    max_sessions: int | None = None,
    max_parties: int | None = None,
    max_agencies: int | None = None,
    verbose: bool = True,
) -> dict[str, int]:
    """data/real/ 어댑터 7종을 NDJSON으로 출력.

    Demo mode (DEMO_PUBLIC_MODE=true)면 mock fixture 사용.
    실 API key (ASSEMBLY_OPENAPI_KEY) 있으면 실 호출.

    Output 8 files: bills, members, votes, committees, sessions, statements, parties, agencies.
    Note: session 어댑터가 Session·Statement 두 노드 yield하므로 출력은 2 파일.
    """
    from data.real.agency import fetch_agencies
    from data.real.bill import fetch_bills
    from data.real.committee import fetch_committees
    from data.real.member import fetch_members
    from data.real.party import fetch_parties
    from data.real.session import fetch_sessions_and_statements
    from data.real.vote import fetch_votes
    from data.schemas import Session, Statement

    def _log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    _log(f"[bill]       fetching → {out_dir}/bills.ndjson")
    counts["bill"] = write_ndjson(
        fetch_bills(max_rows=max_bills), out_dir / "bills.ndjson",
    )

    _log(f"[member]     fetching → {out_dir}/members.ndjson")
    counts["member"] = write_ndjson(
        fetch_members(max_rows=max_members), out_dir / "members.ndjson",
    )

    _log(f"[vote]       fetching → {out_dir}/votes.ndjson")
    counts["vote"] = write_ndjson(
        fetch_votes(max_rows=max_votes), out_dir / "votes.ndjson",
    )

    _log(f"[committee]  fetching → {out_dir}/committees.ndjson")
    counts["committee"] = write_ndjson(
        fetch_committees(max_rows=max_committees), out_dir / "committees.ndjson",
    )

    _log(f"[party]      fetching → {out_dir}/parties.ndjson")
    counts["party"] = write_ndjson(
        fetch_parties(max_rows=max_parties), out_dir / "parties.ndjson",
    )

    _log(f"[agency]     fetching → {out_dir}/agencies.ndjson")
    counts["agency"] = write_ndjson(
        fetch_agencies(max_rows=max_agencies), out_dir / "agencies.ndjson",
    )

    # Session generator는 Session·Statement 둘 다 yield → 분리 적재.
    _log(f"[session+statement] fetching → sessions.ndjson + statements.ndjson")
    items = list(fetch_sessions_and_statements(max_sessions=max_sessions))
    sessions_only = [i for i in items if isinstance(i, Session)]
    statements_only = [i for i in items if isinstance(i, Statement)]
    counts["session"] = write_ndjson(sessions_only, out_dir / "sessions.ndjson")
    counts["statement"] = write_ndjson(statements_only, out_dir / "statements.ndjson")

    return counts


# ─── 미구현 stub (Phase 3) ──────────────────────────────────────────────────

def emit_synthetic_s3(bucket: str, prefix: str = "synthetic/", **kwargs) -> dict[str, int]:
    """S3 emit - Phase 3에서 구현."""
    raise NotImplementedError(
        "S3 emit은 Phase 3에서 구현. 임시로 로컬 emit 후 `aws s3 sync` 활용."
    )


def emit_external_local(
    out_dir: Path,
    *,
    news_query: str = "국회 입법",
    news_count: int = 30,
    poll_count: int = 50,
    seed: int = 20260513,
    verbose: bool = True,
) -> dict[str, int]:
    """data/external/ 어댑터를 NDJSON으로 출력 - 네이버 뉴스 + 합성 여론조사."""
    from data.external.naver_news import fetch_news
    from data.external.poll_result import generate_polls

    def _log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    _log(f"[social_signal] fetching '{news_query}' display={news_count} → social_signals.ndjson")
    counts["social_signal"] = write_ndjson(
        fetch_news(news_query, display=news_count),
        out_dir / "social_signals.ndjson",
    )

    _log(f"[poll_result]   generating {poll_count} → poll_results.ndjson")
    counts["poll_result"] = write_ndjson(
        generate_polls(count=poll_count, seed=seed),
        out_dir / "poll_results.ndjson",
    )

    return counts


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
        "--max-bills",
        type=int,
        default=None,
        help="--source real: 가져올 의안 최대 수 (기본 무제한)",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        default=None,
        help="--source real: 가져올 의원 최대 수",
    )
    parser.add_argument(
        "--max-votes",
        type=int,
        default=None,
        help="--source real: 가져올 표결 최대 수",
    )
    parser.add_argument(
        "--max-committees",
        type=int,
        default=None,
        help="--source real: 가져올 위원회 최대 수",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=None,
        help="--source real: 가져올 회의(+발언) 최대 수",
    )
    parser.add_argument(
        "--max-parties",
        type=int,
        default=None,
        help="--source real: 가져올 정당 최대 수",
    )
    parser.add_argument(
        "--max-agencies",
        type=int,
        default=None,
        help="--source real: 가져올 국정감사 기관 최대 수",
    )
    parser.add_argument(
        "--news-query",
        type=str,
        default="국회 입법",
        help="--source external: 네이버 뉴스 검색어",
    )
    parser.add_argument(
        "--news-count",
        type=int,
        default=30,
        help="--source external: 네이버 뉴스 결과 수 (1-100)",
    )
    parser.add_argument(
        "--poll-count",
        type=int,
        default=50,
        help="--source external: 합성 여론조사 수",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="DEMO_PUBLIC_MODE=true 설정 (실 API key 없이 mock fixture 사용)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="진행 메시지 출력 안 함",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. Exit code: 0=성공, 1=오류, 2=미구현."""
    import os
    args = _build_parser().parse_args(argv)
    verbose = not args.quiet

    # --demo 플래그 → DEMO_PUBLIC_MODE 활성화
    if args.demo:
        os.environ["DEMO_PUBLIC_MODE"] = "true"

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

    counts: dict[str, int] = {}

    if args.source in ("synthetic", "all"):
        synthetic_counts = emit_synthetic_local(
            out_dir=args.out_dir,
            article_count=args.article_count,
            reader_count=args.reader_count,
            ad_count=args.ad_count,
            seed=args.seed,
            verbose=verbose,
        )
        counts.update(synthetic_counts)

    if args.source in ("real", "all"):
        real_counts = emit_real_local(
            out_dir=args.out_dir,
            max_bills=args.max_bills,
            max_members=args.max_members,
            max_votes=args.max_votes,
            max_committees=args.max_committees,
            max_sessions=args.max_sessions,
            max_parties=args.max_parties,
            max_agencies=args.max_agencies,
            verbose=verbose,
        )
        counts.update(real_counts)

    if args.source in ("external", "all"):
        external_counts = emit_external_local(
            out_dir=args.out_dir,
            news_query=args.news_query,
            news_count=args.news_count,
            poll_count=args.poll_count,
            seed=args.seed,
            verbose=verbose,
        )
        counts.update(external_counts)

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
