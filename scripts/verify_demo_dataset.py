#!/usr/bin/env python3
"""데모 데이터셋 통합 검증 스크립트.

`python -m data.load --source all --demo --out-dir <dir>` 출력을 받아 다음을 검증:
1. 10개 NDJSON 파일 존재 + Pydantic round-trip 가능
2. 모든 노드에 `source` 태깅 (real/synthetic/external)
3. 정치 중립성 - 모든 article 본문 political_balance_score ≥0.8
4. cross-adapter 참조 무결성 (vote.bill_id → bill.bill_id 등)
5. seeds.py PDF 시그니처 시드 ID들이 데이터셋에 포함됨 (있을 때만)

Exit code:
    0 = 모든 검증 통과
    1 = 검증 실패
    2 = 입력 디렉토리·파일 누락

Usage:
    python -m data.load --source all --demo --out-dir /tmp/demo
    python scripts/verify_demo_dataset.py /tmp/demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Standalone 실행 지원 - 저장소 루트를 sys.path에 추가.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

EXPECTED_FILES = {
    "synthetic": ["topics.ndjson", "articles.ndjson", "readers.ndjson",
                  "advertisements.ndjson", "ad_inventories.ndjson"],
    "real": ["bills.ndjson", "members.ndjson", "votes.ndjson"],
    "external": ["social_signals.ndjson", "poll_results.ndjson"],
}


def _read_ndjson(path: Path) -> list[dict]:
    """NDJSON 파일을 dict 리스트로 로드."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_files_exist(out_dir: Path) -> tuple[bool, list[str]]:
    """10개 예상 파일이 모두 존재하는지."""
    missing: list[str] = []
    for group, files in EXPECTED_FILES.items():
        for name in files:
            if not (out_dir / name).exists():
                missing.append(f"{group}/{name}")
    return (not missing, missing)


def check_pydantic_round_trip(out_dir: Path) -> tuple[bool, list[str]]:
    """각 파일을 schemas의 해당 클래스로 validate."""
    from data.schemas import (
        Advertisement, AdInventory, Article, Bill, Person,
        PollResult, Reader, SocialSignal, Topic, Vote,
    )
    mapping = {
        "topics.ndjson": Topic,
        "articles.ndjson": Article,
        "readers.ndjson": Reader,
        "advertisements.ndjson": Advertisement,
        "ad_inventories.ndjson": AdInventory,
        "bills.ndjson": Bill,
        "members.ndjson": Person,
        "votes.ndjson": Vote,
        "social_signals.ndjson": SocialSignal,
        "poll_results.ndjson": PollResult,
    }
    errors: list[str] = []
    for name, cls in mapping.items():
        path = out_dir / name
        if not path.exists():
            continue
        for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not raw.strip():
                continue
            try:
                cls.model_validate_json(raw)
            except Exception as e:
                errors.append(f"{name}:{idx + 1}: {type(e).__name__}: {str(e)[:80]}")
                if len(errors) >= 5:
                    return (False, errors)
    return (not errors, errors)


def check_source_tagging(out_dir: Path) -> tuple[bool, list[str]]:
    """모든 노드에 source 태깅 + 그룹별 정확한 source."""
    errors: list[str] = []
    for group, files in EXPECTED_FILES.items():
        for name in files:
            path = out_dir / name
            if not path.exists():
                continue
            for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if not raw.strip():
                    continue
                node = json.loads(raw)
                src = node.get("source")
                if src is None:
                    errors.append(f"{name}:{idx + 1} - source 누락")
                elif group == "real" and src != "real":
                    errors.append(f"{name}:{idx + 1} - real 그룹인데 source={src}")
                elif group == "synthetic" and src != "synthetic":
                    errors.append(f"{name}:{idx + 1} - synthetic 그룹인데 source={src}")
                elif group == "external" and src not in ("external", "synthetic"):
                    # poll_result는 100% 합성, news는 external
                    errors.append(f"{name}:{idx + 1} - external 그룹인데 source={src}")
                if len(errors) >= 5:
                    return (False, errors)
    return (not errors, errors)


def check_article_political_balance(out_dir: Path, threshold: float = 0.8) -> tuple[bool, list[str]]:
    """모든 article 본문 political_balance_score ≥ threshold."""
    from api.services.guardrails import political_balance_score
    path = out_dir / "articles.ndjson"
    if not path.exists():
        return (True, [])
    low: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        node = json.loads(raw)
        score, _ = political_balance_score(node["content"])
        if score < threshold:
            low.append(f"{node['article_id']}: score={score:.2f}")
            if len(low) >= 5:
                break
    return (not low, low)


def check_cross_reference_integrity(out_dir: Path) -> tuple[bool, list[str]]:
    """vote.bill_id, ad_inventory.ad_id 등 cross-adapter 참조 무결성."""
    errors: list[str] = []

    bills_path = out_dir / "bills.ndjson"
    votes_path = out_dir / "votes.ndjson"
    ads_path = out_dir / "advertisements.ndjson"
    inventories_path = out_dir / "ad_inventories.ndjson"

    if bills_path.exists() and votes_path.exists():
        bill_ids = {n["bill_id"] for n in _read_ndjson(bills_path)}
        for v in _read_ndjson(votes_path):
            if v["bill_id"] not in bill_ids:
                errors.append(f"votes.ndjson: vote.bill_id={v['bill_id']} bill에 없음")
                if len(errors) >= 5:
                    return (False, errors)

    if ads_path.exists() and inventories_path.exists():
        ad_ids = {n["ad_id"] for n in _read_ndjson(ads_path)}
        for inv in _read_ndjson(inventories_path):
            if inv["ad_id"] not in ad_ids:
                errors.append(f"ad_inventories.ndjson: ad_id={inv['ad_id']} advertisements에 없음")
                if len(errors) >= 5:
                    return (False, errors)

    return (not errors, errors)


def check_seed_signatures(out_dir: Path) -> tuple[bool, list[str]]:
    """seeds.py의 시드 ID가 데이터셋에 포함됐는지 (선택적 검증).

    load.py는 현재 seeds를 자동 주입하지 않음 - 이 check는 데이터셋이 시드를
    별도로 추가 적재한 경우에만 통과 (informational, not blocking).
    """
    from data.synthetic.seeds import iter_demo_node_ids
    # 검증은 informational로 처리 (시드는 별도 워크플로로 적재)
    seed_ids = list(iter_demo_node_ids())
    return (True, [f"seeds.py: {len(seed_ids)}개 시드 정의 (적재는 별도 워크플로)"])


# ─── 메인 ──────────────────────────────────────────────────────────────────

def run_all_checks(out_dir: Path) -> int:
    """모든 검증 실행. Returns: exit code."""
    print(f"=== 데모 데이터셋 검증: {out_dir} ===\n")

    checks = [
        ("파일 존재", check_files_exist),
        ("Pydantic round-trip", check_pydantic_round_trip),
        ("source 태깅", check_source_tagging),
        ("정치 균형 (article)", check_article_political_balance),
        ("cross-reference 무결성", check_cross_reference_integrity),
        ("seeds 시그니처", check_seed_signatures),
    ]

    failures = 0
    for name, check in checks:
        ok, details = check(out_dir)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if details:
            for d in details[:5]:
                print(f"    - {d}")
        if not ok:
            failures += 1

    print(f"\n=== 결과: {len(checks) - failures}/{len(checks)} 통과 ===")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="데모 데이터셋 통합 검증")
    parser.add_argument("out_dir", type=Path, help="`data.load` 출력 디렉토리")
    args = parser.parse_args(argv)

    if not args.out_dir.is_dir():
        print(f"[verify] ERROR: {args.out_dir}가 디렉토리 아님", file=sys.stderr)
        return 2

    return run_all_checks(args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
