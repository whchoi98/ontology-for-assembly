# 설계: ad-match(시나리오 L) 시연 콘텐츠 확대

- Status: Approved (brainstorming)
- Date: 2026-06-04
- 범위: 시나리오 L (광고 매칭 매트릭스) 단일

## Context / 목표

`/ad-match`는 데모 3대 메시지 중 "AI 거버넌스 광고 매칭"을 담당한다. 핵심 시연 포인트는 **같은 기사에 keyword/embedding은 광고를 붙이는데 agent만 민감 콘텐츠에서 광고 노출을 생략(skip)**하는 대비다. 현재 시연 콘텐츠는 샘플 기사 2개(`art_safe_AI`, `art_DEMO_TRAGIC_001`)뿐이라 대비가 1종(scandal)에 그친다.

**목표**: 큐레이트된 6개 데모 기사로 확대 — 민감 카테고리 3종(scandal/tragedy/minor_victim)을 모두 커버하는 skip 케이스 3개 + 서로 다른 광고 카테고리로 agent가 잘 매칭하는 safe 케이스 3개. 백엔드 단일 소스 + 신규 `GET /api/ad-match/samples`로 노출, 웹이 fetch해 셀렉터를 동적 구성.

## Scope

**In**: 6 데모 기사 큐레이트 카탈로그(백엔드), `/api/ad-match/samples` 엔드포인트, 웹 셀렉터 동적화, 테스트.

**Out (YAGNI)**:
- 광고 인벤토리 확장 — 불필요. 기존 `generate_advertisements(count=30, seed=42)`가 10 카테고리(automotive·security·telecom·healthcare·fintech·data_solutions·sustainability·marketing·cloud·education) 보유.
- 민감 카테고리 추가 — 3종(scandal/tragedy/minor_victim) 유지.
- 웹 레이아웃 재설계 — 셀렉터를 fetch 기반으로 바꾸는 것 외 UI 변경 없음.

## 6개 데모 기사

`ArticleSummary(article_id, title, content, topic_ids)`. 민감 감지는 `_detect_sensitive`가 `title + " " + content`를 `SENSITIVE_PATTERNS` 정규식으로 스캔. safe 기사는 민감 정규식 단어(사망/참사/재난/희생/피해자/미성년/청소년 피해/비위/위증/뇌물/수사 진행/기소/구속/혐의)를 **포함하지 않아야** 한다.

| # | article_id | title (요지) | content 트리거 / topic_ids | 기대 거버넌스 |
|---|---|---|---|---|
| 1 | `art_DEMO_TRAGIC_001` (기존) | ○○○ 의원 위증 의혹 — 검찰 수사 진행 중 | `위증`·`수사 진행`·`혐의` | **skip:scandal** |
| 2 | `art_DEMO_TRAGEDY_001` (신규) | ○○ 산업단지 폭발 참사 — 피해 규모 조사 | `참사`·`사망`·`피해자`·`희생` | **skip:tragedy** |
| 3 | `art_DEMO_MINOR_001` (신규) | 청소년 보호 입법 논의 — 미성년 대상 사건 후속 | `미성년`·`청소년 피해` | **skip:minor_victim** |
| 4 | `art_safe_AI` (기존) | AI 산업 진흥 종합 대책 — 22대 국회 1분기 분석 | `topic_ai` → data_solutions/cloud/security | **match** |
| 5 | `art_safe_FINTECH_001` (신규) | 핀테크 규제 샌드박스 확대 — 금융 혁신 입법 동향 | `topic_finance` → fintech | **match** |
| 6 | `art_safe_GREEN_001` (신규) | 탄소중립 산업 전환 로드맵 — 친환경 투자 분석 | `topic_environment` → sustainability | **match** |

(전 기사 ADR-0004 준수 — ○○○/시연용 placeholder, 실존 정당·인물·가치판단 없음. 민감 케이스도 일반 상황 서술로 특정 주체 비귀속.)

## 컴포넌트 (단위별 책임)

1. **백엔드 큐레이트 카탈로그** — `data/synthetic/seeds.py`에 `DEMO_AD_ARTICLES: dict[str, dict]` 추가. 각 값: `title`, `content`, `topic_ids`, `expected_governance`(`"skip:scandal"|"skip:tragedy"|"skip:minor_victim"|"match"`). 헬퍼: `demo_ad_article(article_id) -> ArticleSummary | None`, `list_demo_ad_articles() -> list[dict]`.
   - 기존 2개(`art_safe_AI`, `art_DEMO_TRAGIC_001`)를 이 카탈로그로 흡수(현재 `_load_article`에 하드코딩된 텍스트를 카탈로그로 이동).
2. **`_load_article` 리팩터** (`api/routers/ad_match.py`) — 하드코딩 if/else → `seeds.demo_ad_article(article_id)` 조회. 미등록 id는 기존 generic fallback 유지(하위 호환).
3. **신규 엔드포인트** `GET /api/ad-match/samples` (`ad_match.py`) — `list_demo_ad_articles()` 기반으로 `{samples: [{article_id, title, category_hint, expected_governance}]}` 반환. category_hint는 topic_ids → `TOPIC_TO_CATEGORY_HINTS` 첫 매칭(safe) 또는 `null`(skip). **단일 진실원.**
4. **웹 셀렉터 동적화** (`web/app/ad-match/page.tsx`) — 하드코딩 `SAMPLE_ARTICLES` 제거 → 마운트 시 `fetchAdMatchSamples()` → 셀렉터 렌더. 각 항목에 거버넌스 배지: `expected_governance`가 `skip:*`이면 "Agent 거절 예상"(경고색), `match`이면 "안전 매칭". 기본 선택은 첫 skip 케이스(현재 동작 유지).
5. **api-client** (`web/lib/api-client.ts` 또는 `scenario-clients.ts`) — 타입드 `fetchAdMatchSamples(): Promise<AdMatchSample[]>` 추가.

## 데이터 흐름

```
web mount
  └─ GET /api/ad-match/samples ──▶ seeds.list_demo_ad_articles()  (6개)
       └─ 셀렉터 렌더 (거버넌스 배지)
            └─ 사용자 기사 선택
                 └─ POST /api/ad-match {article_id, mode:"compare"}
                      └─ _load_article → seeds.demo_ad_article(id) → ArticleSummary
                           └─ ad_matcher.compare_modes → {keyword, embedding, agent} + governance_summary
```

## API 계약 — `GET /api/ad-match/samples`

```json
{
  "samples": [
    {"article_id": "art_DEMO_TRAGIC_001", "title": "...", "category_hint": null, "expected_governance": "skip:scandal"},
    {"article_id": "art_safe_FINTECH_001", "title": "...", "category_hint": "fintech", "expected_governance": "match"}
  ]
}
```

## 테스트 (`tests/test_ad_match.py` 확장)

- **skip 케이스 3개**: `compare_modes`에서 agent `chosen_ad_id is None` + reason `startswith("skip")`. keyword·embedding은 `chosen_ad_id is not None` (대비 단언).
- **safe 케이스 3개**: agent `chosen_ad_id is not None`; 매칭 광고 category가 기대 카테고리(fintech/sustainability/data_solutions 등)와 일치(느슨하게: 매칭 성공만 단언해도 가능).
- **엔드포인트**: `GET /api/ad-match/samples` → 200, `samples` 길이 6, 각 항목에 `article_id`/`expected_governance` 존재. `skip:*` 3개 + `match` 3개.
- **중립성**: 6 기사 `title+content`에 실존 정당명(더불어민주당/국민의힘/조국혁신당 등) 미포함 단언(placeholder만).

## 변경 파일

| 파일 | 변경 |
|---|---|
| `data/synthetic/seeds.py` | `DEMO_AD_ARTICLES` + `demo_ad_article()` + `list_demo_ad_articles()` 추가; 기존 2 기사 텍스트 흡수 |
| `api/routers/ad_match.py` | `_load_article` 카탈로그 조회로 리팩터; `GET /api/ad-match/samples` 추가 |
| `web/app/ad-match/page.tsx` | `SAMPLE_ARTICLES` 하드코딩 → fetch 기반 셀렉터 + 거버넌스 배지 |
| `web/lib/api-client.ts` | `fetchAdMatchSamples()` 타입드 함수 |
| `tests/test_ad_match.py` | 6 케이스 + samples 엔드포인트 + 중립성 테스트 |
| `CHANGELOG.md` | Unreleased 항목 |

## Open Questions

없음.
