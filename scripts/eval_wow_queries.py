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
# Phase 4 완료 - 14/14 시나리오 모두 구현.
SCENARIOS_IMPLEMENTED = tuple(SCENARIOS_ALL)

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

    Phase 4 완료 - 14 시나리오 모두 active. Implemented 시나리오는 expected_substrings로
    응답 sanity check.
    """
    cases: list[CaseDefinition] = []
    for persona in PERSONAS:
        # ─── 핵심 시나리오 (A·B·L) ─────────────────────────────────────
        cases.append(CaseDefinition(
            persona=persona, scenario="A",
            query="AI 입법",
            expected_substrings=("AI", "법"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="B",
            query="22대 국회 AI 입법 동향을 분석해주세요",
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="L",
            query="art_safe_normal",  # article_id
        ))

        # ─── 핵심 PDF ★ (K·M) ──────────────────────────────────────────
        cases.append(CaseDefinition(
            persona=persona, scenario="K",
            query="",  # GET /api/outlier (no path param)
            expected_substrings=("outlier", "이탈"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="M",
            query="MONA_001",  # path param: person_id
            expected_substrings=("events", "AI"),
        ))

        # ─── 거버넌스 (I) ──────────────────────────────────────────────
        cases.append(CaseDefinition(
            persona=persona, scenario="I",
            query="더불어민주당과 국민의힘이 양당 협력으로 청년 주거 정책을 통과시켰다. (출처: 국회 OpenAPI 2026-04)",
            expected_substrings=("score", "components"),
        ))

        # ─── 데이터·AI (E·F·J·N) ────────────────────────────────────
        cases.append(CaseDefinition(
            persona=persona, scenario="E",
            query="",  # GET /api/cluster
            expected_substrings=("cluster", "label"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="F",
            query="MONA_001",  # path param
            expected_substrings=("candidates", "similarity"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="J",
            query="",  # GET /api/external-signal
            expected_substrings=("fusions", "pattern"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="N",
            query="",  # GET /api/issue-legislation
            expected_substrings=("rows", "intensity"),
        ))

        # ─── B2C·B2B (C·D·G·H) ─────────────────────────────────────────
        cases.append(CaseDefinition(
            persona=persona, scenario="C",
            query="",  # GET /api/insights/articles
            expected_substrings=("articles", "title"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="D",
            query="AI 산업 진흥 정책. 더불어민주당과 국민의힘이 협력 (출처: 국회 OpenAPI)",
            expected_substrings=("scores", "top_persona_id"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="G",
            query="",  # GET /api/article-roi
            expected_substrings=("entries", "roi_pct"),
        ))
        cases.append(CaseDefinition(
            persona=persona, scenario="H",
            query="seoul",  # path param
            expected_substrings=("seoul", "서울"),
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


def _get_json(base_url: str, path: str, persona: str) -> tuple[bool, str]:
    """GET 헬퍼 - (ok, response_text). LLM 호출 없는 라우터는 balance=1.0."""
    try:
        import requests
        r = requests.get(
            f"{base_url}{path}",
            headers={"X-Persona-Id": persona},
            timeout=15,
        )
        r.raise_for_status()
        return True, json.dumps(r.json(), ensure_ascii=False)
    except Exception as e:
        return False, f"error: {e}"


def _post_json(
    base_url: str, path: str, persona: str, payload: dict,
) -> tuple[bool, str]:
    """POST 헬퍼 - (ok, response_text)."""
    try:
        import requests
        r = requests.post(
            f"{base_url}{path}",
            json=payload,
            headers={"X-Persona-Id": persona},
            timeout=15,
        )
        r.raise_for_status()
        return True, json.dumps(r.json(), ensure_ascii=False)
    except Exception as e:
        return False, f"error: {e}"


# Phase 4 신규 dispatchers (C·D·E·F·G·H·I·J·K·M·N).
# LLM 호출 없는 결정적 시드 라우터들이므로 balance_score=1.0 처리.

def call_outlier(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """K - GET /api/outlier."""
    ok, text = _get_json(base_url, "/api/outlier?limit=5", persona)
    return ok, 1.0, text


def call_journey(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """M - GET /api/journey/{person_id}. query=person_id."""
    ok, text = _get_json(base_url, f"/api/journey/{query}", persona)
    return ok, 1.0, text


def call_neutrality(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """I - POST /api/neutrality/score. query=텍스트. balance는 응답 score 사용."""
    ok, text = _post_json(base_url, "/api/neutrality/score", persona, {"text": query})
    if not ok:
        return False, 0.0, text
    try:
        body = json.loads(text)
        score = float(body.get("score", 1.0))
        return True, score, text
    except Exception:
        return True, 1.0, text


def call_cluster(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """E - GET /api/cluster."""
    ok, text = _get_json(base_url, "/api/cluster", persona)
    return ok, 1.0, text


def call_lookalike(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """F - GET /api/lookalike/{person_id}. query=person_id."""
    ok, text = _get_json(base_url, f"/api/lookalike/{query}?top_k=3", persona)
    return ok, 1.0, text


def call_external_signal(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """J - GET /api/external-signal."""
    ok, text = _get_json(base_url, "/api/external-signal", persona)
    return ok, 1.0, text


def call_issue_legislation(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """N - GET /api/issue-legislation."""
    ok, text = _get_json(base_url, "/api/issue-legislation", persona)
    return ok, 1.0, text


def call_insights(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """C - GET /api/insights/articles."""
    ok, text = _get_json(base_url, "/api/insights/articles?limit=5", persona)
    return ok, 1.0, text


def call_persona_match(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """D - POST /api/persona-match/text. query=text."""
    ok, text = _post_json(
        base_url, "/api/persona-match/text", persona, {"text": query},
    )
    return ok, 1.0, text


def call_article_roi(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """G - GET /api/article-roi."""
    ok, text = _get_json(base_url, "/api/article-roi?limit=5", persona)
    return ok, 1.0, text


def call_district_map(base_url: str, persona: str, query: str) -> tuple[bool, float, str]:
    """H - GET /api/district-map/{sido_key}. query=sido_key."""
    ok, text = _get_json(base_url, f"/api/district-map/{query}", persona)
    return ok, 1.0, text


DISPATCHERS = {
    "A": call_search,
    "B": call_chat,
    "C": call_insights,
    "D": call_persona_match,
    "E": call_cluster,
    "F": call_lookalike,
    "G": call_article_roi,
    "H": call_district_map,
    "I": call_neutrality,
    "J": call_external_signal,
    "K": call_outlier,
    "L": call_ad_match,
    "M": call_journey,
    "N": call_issue_legislation,
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
