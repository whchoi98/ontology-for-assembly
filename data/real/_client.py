"""국회 OpenAPI 공유 HTTP 클라이언트.

3 어댑터(bill, member, vote)의 공통 기반:
- API key 로딩 (env / Secrets Manager Phase 3)
- HTTP fetch + retry + timeout
- JSON 응답 파싱 (top-level wrapper 표준화)
- 페이징 (pIndex, pSize)
- Demo mode 분기

국회 OpenAPI 응답 형태 (예: 의안처리상황 nzmimeepazxkubdpn):
{
  "<endpoint_code>": [
    { "head": [{"list_total_count": 1234}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}] },
    { "row": [ {<entity_1>}, {<entity_2>}, ... ] }
  ]
}

References:
- 국회 열린데이터광장 https://open.assembly.go.kr/portal/openapi/main.do
- spec §5 데이터 파이프라인
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterator, Optional

__all__ = ["AssemblyApiError", "AssemblyClient", "demo_mode"]


class AssemblyApiError(RuntimeError):
    """국회 OpenAPI 호출 실패."""


@dataclass(frozen=True)
class ApiResponse:
    """국회 OpenAPI 응답 표준화 형식."""
    total_count: int
    result_code: str
    result_message: str
    rows: list[dict]


def demo_mode() -> bool:
    """DEMO_PUBLIC_MODE - 실 API 호출 우회 (테스트·로컬)."""
    return os.environ.get("DEMO_PUBLIC_MODE", "false").lower() == "true"


def _api_base_url() -> str:
    """기본 base URL. 환경별 override 가능."""
    return os.environ.get(
        "ASSEMBLY_API_BASE_URL",
        "https://open.assembly.go.kr/portal/openapi",
    )


def _resolve_api_key() -> str:
    """API key 로딩. Demo mode면 빈 문자열 허용."""
    key = os.environ.get("ASSEMBLY_OPENAPI_KEY", "")
    if not key and not demo_mode():
        raise AssemblyApiError(
            "ASSEMBLY_OPENAPI_KEY 환경변수 미설정. "
            "https://open.assembly.go.kr 활용신청 후 발급. "
            "테스트는 DEMO_PUBLIC_MODE=true."
        )
    return key


class AssemblyClient:
    """국회 OpenAPI 공유 HTTP 클라이언트.

    각 어댑터(BillAdapter 등)가 이 클라이언트를 사용해 페이징·재시도·파싱을
    위임. 직접 인스턴스화 가능하나 보통 어댑터 내부에서 사용.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or _resolve_api_key()
        self.base_url = base_url or _api_base_url()
        self.timeout = timeout

    def fetch_page(
        self,
        endpoint: str,
        *,
        p_index: int = 1,
        p_size: int = 100,
        params: Optional[dict[str, str]] = None,
    ) -> ApiResponse:
        """단일 페이지 fetch. Demo mode에서는 절대 호출되지 않음 (어댑터에서 분기)."""
        import requests  # lazy
        url = f"{self.base_url}/{endpoint}"
        query: dict[str, Any] = {
            "KEY": self.api_key,
            "Type": "json",
            "pIndex": p_index,
            "pSize": p_size,
        }
        if params:
            query.update(params)
        # 국회 OpenAPI는 User-Agent 헤더 누락 시 400 Bad Request 반환 (2026-05 확인).
        # 일반 브라우저 UA로 우회 - rate-limit 추적 가능하도록 식별자 포함.
        headers = {
            "User-Agent": (
                "ontology-for-assembly/0.1 "
                "(Mozilla/5.0 compatible; +https://github.com/whchoi98/ontology-for-assembly)"
            ),
            "Accept": "application/json",
        }
        try:
            response = requests.get(url, params=query, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as e:
            raise AssemblyApiError(f"HTTP error: {e}") from e

        return _parse_response(payload, endpoint)

    def iter_all_pages(
        self,
        endpoint: str,
        *,
        p_size: int = 100,
        params: Optional[dict[str, str]] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[dict]:
        """전체 페이지 순회. row 단위로 yield.

        Args:
            endpoint: API endpoint 코드.
            p_size: 페이지당 행 수.
            params: 추가 쿼리 파라미터.
            max_pages: 안전 상한 (None = 무제한).

        Yields:
            dict — 한 row.
        """
        p_index = 1
        total_seen = 0
        while True:
            if max_pages is not None and p_index > max_pages:
                break
            page = self.fetch_page(endpoint, p_index=p_index, p_size=p_size, params=params)
            if not page.rows:
                break
            yield from page.rows
            total_seen += len(page.rows)
            if total_seen >= page.total_count:
                break
            p_index += 1


# ─── 응답 파싱 ─────────────────────────────────────────────────────────────

def _parse_response(payload: dict, endpoint: str) -> ApiResponse:
    """국회 OpenAPI 응답 → ApiResponse 표준화.

    Defensive: empty body (페이지 범위 초과·해당 데이터 없음) → 빈 ApiResponse (no raise).
    또한 payload 전체가 RESULT만 있는 경우 (INFO-200, ERROR-300 등) → 정상 처리.
    """
    body = payload.get(endpoint, [])
    if not isinstance(body, list):
        raise AssemblyApiError(f"unexpected response shape for {endpoint}")
    if not body:
        # body가 비어있으면 payload top-level RESULT 시도 (INFO-200 또는 errored)
        top_result = payload.get("RESULT") or {}
        code = top_result.get("CODE", "INFO-200")
        msg = top_result.get("MESSAGE", "no data")
        # INFO-200 = "해당 데이터 없음" 정상; 그 외는 raise
        if code not in ("", "INFO-000", "INFO-200"):
            raise AssemblyApiError(f"{endpoint} 호출 실패: [{code}] {msg}")
        return ApiResponse(total_count=0, result_code=code, result_message=msg, rows=[])

    # body[0] = head 메타데이터, body[1] = row 리스트
    head_block = next((b.get("head") for b in body if isinstance(b, dict) and "head" in b), None)
    row_block = next((b.get("row") for b in body if isinstance(b, dict) and "row" in b), None)

    total_count = 0
    result_code = ""
    result_message = ""

    if head_block:
        for entry in head_block:
            if "list_total_count" in entry:
                total_count = int(entry["list_total_count"])
            if "RESULT" in entry:
                result_code = entry["RESULT"].get("CODE", "")
                result_message = entry["RESULT"].get("MESSAGE", "")

    rows = row_block or []

    # API 정상 코드: INFO-000 (정상), INFO-200 (해당 데이터 없음)
    if result_code not in ("", "INFO-000", "INFO-200"):
        raise AssemblyApiError(f"{endpoint} 호출 실패: [{result_code}] {result_message}")

    return ApiResponse(
        total_count=total_count,
        result_code=result_code,
        result_message=result_message,
        rows=rows,
    )
