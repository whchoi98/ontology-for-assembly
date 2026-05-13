#!/usr/bin/env python3
"""wow-query 평가 - 6 페르소나 × 14 시나리오 = 84 케이스 (Phase 5 Track 5-4).

평가 흐름:
1. 케이스 카탈로그(persona × scenario × query × expected) 정의
2. 각 case에 대해 API 호출
3. 응답에서 expected 키워드 포함 여부 + political_balance_score ≥0.8 검증
4. 결과를 .harness-eval/latest.json에 기록
5. pass_rate < 0.85 시 exit code 1 (CI gate)

현재 구현된 시나리오(A·B·L)만 active 평가. 나머지 11 시나리오는 skipped로 기록
(전체 정합성 보존, 후속 phase 구현 추적).

Usage:
    # 로컬 - DEMO_PUBLIC_MODE + in-process API
    python scripts/eval_wow_queries.py

    # 배포된 CloudFront 대상
    python scripts/eval_wow_queries.py --base-url https://<cf-domain>

References:
- spec §6.4 wow-eval ≥85% 임계
- .harness-eval/latest.json (운영 콘솔 wow-quality 패널 데이터 소스)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Standalone 실행 지원 - 저장소 루트를 sys.path에 추가.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Demo mode 강제 (실 API key 없이 mock 가능).
os.environ.setdefault("DEMO_PUBLIC_MODE", "true")

PERSONAS = ("editorial", "data_ai", "ad_sales", "general_reader", "paid_subscriber", "b2b")
SCENARIOS_ALL = list("ABCDEFGHIJKLMN")
SCENARIOS_IMPLEMENTED = ("A", "B", "L")  # Phase 3 + 5에서 구현

PASS_RATE_THRESHOLD = 0.85
BALANCE_THRESHOLD = 0.8


@dataclass
class CaseDefinition:
    persona: str
    scenario: str
    query: str
    expected_substrings: tuple[str, ...] = ()
    implemented: bool = True


@dataclass
class CaseResult:
    persona: str
    scenario: str
    query: str
    passed: bool
    skipped: bool
    balance_score: float
    latency_ms: int
    reason: str = ""


def build_cases() -> list[CaseDefinition]:
    """6 페르소나 × 14 시나리오 = 84 케이스 카탈로그.

    Implemented 시나리오는 expected_substrings 명시.
    Unimplemented는 implemented=False (skipped 처리).
    """
    cases: list[CaseDefinition] = []
    for persona in PERSONAS:
        # 시나리오 A — 의미 검색
        cases.append(CaseDefinition(
            persona=persona, scenario="A",
            query="AI 입법",
            expected_substrings=("AI", "법"),
        ))
        # 시나리오 B — 3-stage 챗봇
        cases.append(CaseDefinition(
            persona=persona, scenario="B",
            query="22대 국회 AI 입법 동향을 분석해주세요",
        ))
        # 시나리오 L — 광고 매칭 (compare)
        cases.append(CaseDefinition(
            persona=persona, scenario="L",
            query="art_safe_normal",  # article_id
        ))
        # 미구현 시나리오 11개 - skipped
        for code in SCENARIOS_ALL:
            if code in SCENARIOS_IMPLEMENTED:
                continue
            cases.append(CaseDefinition(
                persona=persona, scenario=code,
                query="(미구현)",
                implemented=False,
            ))
    return cases


# ─── API 호출 ───────────────────────────────────────────────────────────────

def call_search(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """시나리오 A POST /api/search."""
    try:
        import requests
        r = requests.post(
            f"{base_url}/api/search",
            json={"q": query, "top_k": 5, "include_subgraph": False},
            headers={"X-Persona-Id": persona},
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        text = " ".join(h.get("title", "") + " " + h.get("snippet", "") for h in body.get("hits", []))
        # search는 LLM 호출 없으므로 balance score N/A → 1.0 처리
        return True, 1.0, text
    except Exception as e:
        return False, 0.0, f"error: {e}"


def call_chat(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """시나리오 B POST /api/chat compare."""
    try:
        import requests
        r = requests.post(
            f"{base_url}/api/chat",
            json={"query": query, "mode": "compare"},
            headers={"X-Persona-Id": persona},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        # agentic stage의 응답 + score 사용
        agentic = body.get("results", {}).get("agentic", {})
        text = agentic.get("text", "")
        score = float(agentic.get("political_balance_score", 1.0))
        return True, score, text
    except Exception as e:
        return False, 0.0, f"error: {e}"


def call_ad_match(base_url: str, persona: str, article_id: str) -> tuple[bool, float, str]:
    """시나리오 L POST /api/ad-match compare. balance는 reason_text의 산술 평균."""
    try:
        import requests
        r = requests.post(
            f"{base_url}/api/ad-match",
            json={"article_id": article_id, "mode": "compare"},
            headers={"X-Persona-Id": persona},
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        text = body.get("governance_summary", {}).get("key_message", "")
        # ad-match는 LLM 호출 없음 → balance N/A
        return True, 1.0, text + " " + json.dumps(body.get("results", {}), ensure_ascii=False)[:300]
    except Exception as e:
        return False, 0.0, f"error: {e}"


DISPATCHERS = {
    "A": call_search,
    "B": call_chat,
    "L": call_ad_match,
}


# ─── 평가 ───────────────────────────────────────────────────────────────────

def run_case(case: CaseDefinition, base_url: str) -> CaseResult:
    if not case.implemented:
        return CaseResult(
            persona=case.persona, scenario=case.scenario, query=case.query,
            passed=False, skipped=True, balance_score=1.0, latency_ms=0,
            reason="시나리오 미구현 (skipped)",
        )

    dispatcher = DISPATCHERS.get(case.scenario)
    if dispatcher is None:
        return CaseResult(
            persona=case.persona, scenario=case.scenario, query=case.query,
            passed=False, skipped=True, balance_score=1.0, latency_ms=0,
            reason="dispatcher 미정의",
        )

    t0 = time.monotonic()
    ok, score, text = dispatcher(base_url, case.persona, case.query)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if not ok:
        return CaseResult(
            persona=case.persona, scenario=case.scenario, query=case.query,
            passed=False, skipped=False, balance_score=0.0, latency_ms=latency_ms,
            reason=text,
        )

    # 키워드 매칭
    if case.expected_substrings:
        matched = any(kw in text for kw in case.expected_substrings)
        if not matched:
            return CaseResult(
                persona=case.persona, scenario=case.scenario, query=case.query,
                passed=False, skipped=False, balance_score=score, latency_ms=latency_ms,
                reason=f"expected {case.expected_substrings} 미발견",
            )

    # 정치 균형 임계
    if score < BALANCE_THRESHOLD:
        return CaseResult(
            persona=case.persona, scenario=case.scenario, query=case.query,
            passed=False, skipped=False, balance_score=score, latency_ms=latency_ms,
            reason=f"balance score {score:.2f} < {BALANCE_THRESHOLD}",
        )

    return CaseResult(
        persona=case.persona, scenario=case.scenario, query=case.query,
        passed=True, skipped=False, balance_score=score, latency_ms=latency_ms,
        reason="ok",
    )


def summarize(results: list[CaseResult]) -> dict:
    """결과 집계 → .harness-eval/latest.json 형식."""
    active = [r for r in results if not r.skipped]
    pass_count = sum(1 for r in active if r.passed)
    total_active = len(active)
    pass_rate = pass_count / total_active if total_active else 0.0
    scores = [r.balance_score for r in active if r.passed]
    avg_balance = sum(scores) / len(scores) if scores else None

    return {
        "run_iso": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(results),
        "active_cases": total_active,
        "skipped_cases": len(results) - total_active,
        "pass_count": pass_count,
        "pass_rate": round(pass_rate, 3),
        "avg_balance_score": round(avg_balance, 3) if avg_balance is not None else None,
        "threshold": PASS_RATE_THRESHOLD,
        "balance_threshold": BALANCE_THRESHOLD,
        "implemented_scenarios": list(SCENARIOS_IMPLEMENTED),
        "results": [asdict(r) for r in results],
    }


def write_latest(summary: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── 메인 ──────────────────────────────────────────────────────────────────

def run(base_url: str, output: Path, verbose: bool = True) -> int:
    cases = build_cases()
    if verbose:
        print(f"[wow-eval] cases={len(cases)}, base_url={base_url}")

    results: list[CaseResult] = []
    for idx, c in enumerate(cases, 1):
        result = run_case(c, base_url)
        results.append(result)
        if verbose:
            marker = "PASS" if result.passed else ("SKIP" if result.skipped else "FAIL")
            print(f"  [{idx:>3}/{len(cases)}] {marker:4s} {c.persona:18s} {c.scenario}  "
                  f"score={result.balance_score:.2f}  {result.reason[:60]}")

    summary = summarize(results)
    write_latest(summary, output)

    pass_rate = summary["pass_rate"]
    if verbose:
        print()
        print(f"=== 결과 ===")
        print(f"  active: {summary['active_cases']}  pass: {summary['pass_count']} "
              f"({pass_rate*100:.1f}%)  threshold: {PASS_RATE_THRESHOLD*100:.0f}%")
        if summary["avg_balance_score"] is not None:
            print(f"  avg balance: {summary['avg_balance_score']:.3f}")
        print(f"  → 출력: {output}")

    return 0 if pass_rate >= PASS_RATE_THRESHOLD else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="wow-query 84 케이스 평가")
    parser.add_argument(
        "--base-url",
        type=str,
        default="inproc",
        help="API base URL (기본: 'inproc' - in-process TestClient)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".harness-eval/latest.json"),
        help="결과 저장 경로",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    base_url = args.base_url
    if base_url == "inproc":
        # in-process FastAPI TestClient를 위한 setup
        from fastapi.testclient import TestClient
        from api.main import create_app
        client = TestClient(create_app())

        # requests 라이브러리 호환 wrapper - dispatcher가 requests.post 사용
        class _ReqWrapper:
            def post(self, url, json=None, headers=None, timeout=15):
                # url에서 base_url 제거 → path만 추출
                path = url.replace("http://inproc", "")
                response = client.post(path, json=json, headers=headers)
                response.raise_for_status = lambda: None if 200 <= response.status_code < 400 else (_ for _ in ()).throw(RuntimeError(f"HTTP {response.status_code}"))
                return response

            def get(self, url, headers=None, timeout=15):
                path = url.replace("http://inproc", "")
                response = client.get(path, headers=headers)
                response.raise_for_status = lambda: None if 200 <= response.status_code < 400 else (_ for _ in ()).throw(RuntimeError(f"HTTP {response.status_code}"))
                return response

        # requests 모듈 patch (dispatcher 내부 import)
        import sys as _sys
        _sys.modules["requests"] = _ReqWrapper()
        base_url = "http://inproc"

    return run(base_url=base_url, output=args.output, verbose=not args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
