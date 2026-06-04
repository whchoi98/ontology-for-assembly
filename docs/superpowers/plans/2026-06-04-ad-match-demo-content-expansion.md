# ad-match 시연 콘텐츠 확대 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시나리오 L(`/ad-match`)의 데모 샘플 기사를 2개 → 6개로 확대 (skip 3종: scandal/tragedy/minor_victim + safe 3종) 하고, 백엔드 단일 카탈로그 + `GET /api/ad-match/samples`로 노출해 웹 셀렉터가 동적 구성하도록 한다.

**Architecture:** 데모 기사 텍스트·메타를 `data/synthetic/seeds.py:DEMO_AD_ARTICLES`(plain dict, 레이어 경계상 ArticleSummary 미의존)에 단일 정의. 라우터 `_load_article`이 이 카탈로그에서 `ad_matcher.ArticleSummary`를 빌드하고, 신규 `GET /api/ad-match/samples`가 셀렉터 메타를 반환. 웹은 하드코딩 목록 대신 이 엔드포인트를 fetch.

**Tech Stack:** Python 3.12 / FastAPI / pytest (백엔드), Next.js 14 / TypeScript (웹, 검증은 `tsc --noEmit`).

---

### Task 1: 백엔드 데모 기사 카탈로그 (`data/synthetic/seeds.py`)

**Files:**
- Modify: `data/synthetic/seeds.py`
- Test: `tests/test_ad_match.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_ad_match.py` 끝에 추가:

```python
from data.synthetic.seeds import DEMO_AD_ARTICLES, list_demo_ad_articles

_SKIP_IDS = [aid for aid, a in DEMO_AD_ARTICLES.items() if a["expected_governance"].startswith("skip")]
_SAFE_IDS = [aid for aid, a in DEMO_AD_ARTICLES.items() if a["expected_governance"] == "match"]


def test_catalog_has_six_three_skip_three_safe():
    assert len(DEMO_AD_ARTICLES) == 6
    assert len(_SKIP_IDS) == 3
    assert len(_SAFE_IDS) == 3


def test_skip_articles_trigger_their_sensitive_pattern():
    from api.services.ad_matcher import _detect_sensitive, ArticleSummary
    expect = {"skip:scandal": "scandal", "skip:tragedy": "tragedy", "skip:minor_victim": "minor_victim"}
    for aid in _SKIP_IDS:
        a = DEMO_AD_ARTICLES[aid]
        art = ArticleSummary(article_id=aid, title=a["title"], content=a["content"], topic_ids=list(a["topic_ids"]))
        cats = _detect_sensitive(art)
        assert expect[a["expected_governance"]] in cats, f"{aid}: {cats}"


def test_safe_articles_have_no_sensitive_words():
    from api.services.ad_matcher import _detect_sensitive, ArticleSummary
    for aid in _SAFE_IDS:
        a = DEMO_AD_ARTICLES[aid]
        art = ArticleSummary(article_id=aid, title=a["title"], content=a["content"], topic_ids=list(a["topic_ids"]))
        assert _detect_sensitive(art) == set(), f"{aid} unexpectedly sensitive"


def test_skip_articles_anonymized_no_real_party():
    parties = ["더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "기본소득당", "진보당"]
    for aid in _SKIP_IDS:
        text = DEMO_AD_ARTICLES[aid]["title"] + DEMO_AD_ARTICLES[aid]["content"]
        assert not any(p in text for p in parties), f"{aid} names a real party"


def test_list_demo_ad_articles_shape():
    rows = list_demo_ad_articles()
    assert len(rows) == 6
    for r in rows:
        assert set(r) >= {"article_id", "title", "topic_ids", "expected_governance"}
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_ad_match.py -k "catalog or skip_articles or safe_articles or list_demo" -q`
Expected: FAIL — `ImportError: cannot import name 'DEMO_AD_ARTICLES'`

- [ ] **Step 3: 카탈로그 구현** — `data/synthetic/seeds.py`에서 기존 `DEMO_TRAGIC_ARTICLE_ID = "art_DEMO_TRAGIC_001"` 정의 아래에 추가:

```python
# ─── 시나리오 L (광고 매칭) 데모 기사 카탈로그 ────────────────────────────────
# Agent 모드만 민감 콘텐츠(scandal/tragedy/minor_victim)에서 광고 노출 생략(skip);
# keyword/embedding은 항상 매칭 → 3-way 대비. 트리거는 ad_matcher.SENSITIVE_PATTERNS 정규식.
# ADR-0004: skip 케이스 주체는 ○○○ 익명, 가치판단·실존 정당 귀속 없음.
DEMO_TRAGEDY_ARTICLE_ID = "art_DEMO_TRAGEDY_001"
DEMO_MINOR_ARTICLE_ID = "art_DEMO_MINOR_001"
DEMO_SAFE_AI_ARTICLE_ID = "art_safe_AI"
DEMO_SAFE_FINTECH_ARTICLE_ID = "art_safe_FINTECH_001"
DEMO_SAFE_GREEN_ARTICLE_ID = "art_safe_GREEN_001"

DEMO_AD_ARTICLES: dict[str, dict] = {
    DEMO_TRAGIC_ARTICLE_ID: {
        "title": "○○○ 의원 위증 의혹 - 검찰 수사 진행 중",
        "content": (
            "○○○ 의원에 대한 위증 의혹이 제기된 가운데 검찰 수사가 진행 중이다. "
            "관련 사실관계는 아직 확정되지 않았으며 의혹 단계임을 명시한다."
        ),
        "topic_ids": ["topic_judicial"],
        "expected_governance": "skip:scandal",
    },
    DEMO_TRAGEDY_ARTICLE_ID: {
        "title": "○○ 산업단지 폭발 참사 - 피해 규모 조사",
        "content": (
            "○○ 산업단지에서 발생한 폭발 참사로 다수의 사망·피해자가 확인됐다. "
            "당국이 희생 규모와 원인을 조사하고 있다."
        ),
        "topic_ids": ["topic_safety"],
        "expected_governance": "skip:tragedy",
    },
    DEMO_MINOR_ARTICLE_ID: {
        "title": "미성년 대상 사건 후속 - 청소년 보호 강화 입법 논의",
        "content": (
            "미성년 대상 사건을 계기로 청소년 보호를 강화하는 입법이 논의되고 있다. "
            "보호 절차 개선이 핵심 쟁점이다."
        ),
        "topic_ids": ["topic_welfare"],
        "expected_governance": "skip:minor_victim",
    },
    DEMO_SAFE_AI_ARTICLE_ID: {
        "title": "AI 산업 진흥 종합 대책 - 22대 국회 1분기 분석",
        "content": (
            "22대 국회 첫 분기 AI 관련 의안 10건이 발의됐다. "
            "더불어민주당 5건, 국민의힘 3건 등 양당 협력적 의제로 정착."
        ),
        "topic_ids": ["topic_ai", "topic_data"],
        "expected_governance": "match",
    },
    DEMO_SAFE_FINTECH_ARTICLE_ID: {
        "title": "핀테크 규제 샌드박스 확대 - 금융 혁신 입법 동향",
        "content": (
            "핀테크 규제 샌드박스 확대와 금융 혁신 관련 입법 동향을 정리한다. "
            "디지털 금융 인프라 투자가 확대되고 있다."
        ),
        "topic_ids": ["topic_finance"],
        "expected_governance": "match",
    },
    DEMO_SAFE_GREEN_ARTICLE_ID: {
        "title": "탄소중립 산업 전환 로드맵 - 친환경 투자 분석",
        "content": (
            "탄소중립 산업 전환 로드맵과 친환경 투자 흐름을 분석한다. "
            "재생에너지 확대가 핵심 동력으로 꼽힌다."
        ),
        "topic_ids": ["topic_environment"],
        "expected_governance": "match",
    },
}


def list_demo_ad_articles() -> list[dict]:
    """샘플 셀렉터 메타 (GET /api/ad-match/samples가 사용)."""
    return [
        {
            "article_id": aid,
            "title": a["title"],
            "topic_ids": list(a["topic_ids"]),
            "expected_governance": a["expected_governance"],
        }
        for aid, a in DEMO_AD_ARTICLES.items()
    ]
```

또한 파일 상단 `__all__` 리스트에 다음을 추가: `"DEMO_AD_ARTICLES"`, `"list_demo_ad_articles"`, `"DEMO_TRAGEDY_ARTICLE_ID"`, `"DEMO_MINOR_ARTICLE_ID"`.

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_ad_match.py -k "catalog or skip_articles or safe_articles or list_demo" -q`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add data/synthetic/seeds.py tests/test_ad_match.py
git commit -m "feat(data): add 6-article ad-match demo catalog (3 skip + 3 safe)"
```

---

### Task 2: 라우터 — `_load_article` 카탈로그화 + `GET /api/ad-match/samples` (`api/routers/ad_match.py`)

**Files:**
- Modify: `api/routers/ad_match.py` (`_load_article` ~125-151, import, 신규 endpoint)
- Test: `tests/test_ad_match.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_ad_match.py`에 추가:

```python
import pytest as _pytest


@_pytest.mark.parametrize("aid", _SKIP_IDS)
def test_agent_skips_keyword_embedding_match(client, aid):
    body = client.post("/api/ad-match", json={"article_id": aid, "mode": "compare"}).json()
    res = body["results"]
    assert res["agent"]["chosen_ad_id"] is None
    assert res["agent"]["reason_text"].startswith("skip")
    assert res["keyword"]["chosen_ad_id"] is not None
    assert res["embedding"]["chosen_ad_id"] is not None


@_pytest.mark.parametrize("aid", _SAFE_IDS)
def test_agent_matches_safe_articles(client, aid):
    body = client.post("/api/ad-match", json={"article_id": aid, "mode": "compare"}).json()
    assert body["results"]["agent"]["chosen_ad_id"] is not None


def test_samples_endpoint_returns_six(client):
    body = client.get("/api/ad-match/samples").json()
    samples = body["samples"]
    assert len(samples) == 6
    gov = [s["expected_governance"] for s in samples]
    assert sum(g.startswith("skip") for g in gov) == 3
    assert gov.count("match") == 3
    for s in samples:
        assert set(s) >= {"article_id", "title", "category_hint", "expected_governance"}
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_ad_match.py -k "samples_endpoint or agent_skips_keyword or agent_matches_safe" -q`
Expected: FAIL — `/api/ad-match/samples` → 404; tragedy/minor ids → 현재 generic fallback이라 agent가 skip 안 함

- [ ] **Step 3: 라우터 수정** — `api/routers/ad_match.py`:

(a) import 교체 — 기존 `from data.synthetic.seeds import DEMO_TRAGIC_ARTICLE_ID` 를:

```python
from data.synthetic.seeds import DEMO_TRAGIC_ARTICLE_ID, DEMO_AD_ARTICLES, list_demo_ad_articles
```

(b) `_load_article` 함수 본문(현재 125-151) 전체 교체:

```python
def _load_article(article_id: str) -> ad_matcher.ArticleSummary:
    """데모 기사 카탈로그(DEMO_AD_ARTICLES) 조회. 미등록 id는 generic 정책 콘텐츠 fallback."""
    a = DEMO_AD_ARTICLES.get(article_id)
    if a is not None:
        return ad_matcher.ArticleSummary(
            article_id=article_id,
            title=a["title"],
            content=a["content"],
            topic_ids=list(a["topic_ids"]),
        )
    return ad_matcher.ArticleSummary(
        article_id=article_id,
        title="AI 산업 진흥 종합 대책 - 22대 국회 1분기 분석",
        content="22대 국회 첫 분기 AI 관련 의안 10건이 발의됐다. 양당 협력적 의제로 정착.",
        topic_ids=["topic_ai", "topic_data"],
    )
```

(c) 신규 endpoint — 기존 `@router.get("/modes")` 정의 바로 위 또는 아래에 추가:

```python
@router.get("/samples")
def list_samples() -> dict:
    """시연 콘텐츠 셀렉터 메타 (단일 진실원). 웹이 fetch해 동적 구성."""
    from api.services.ad_matcher import TOPIC_TO_CATEGORY_HINTS
    out = []
    for a in list_demo_ad_articles():
        category_hint = None
        if a["expected_governance"] == "match":
            for tid in a["topic_ids"]:
                cats = TOPIC_TO_CATEGORY_HINTS.get(tid)
                if cats:
                    category_hint = cats[0]
                    break
        out.append({
            "article_id": a["article_id"],
            "title": a["title"],
            "category_hint": category_hint,
            "expected_governance": a["expected_governance"],
        })
    return {"samples": out}
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_ad_match.py -q`
Expected: PASS (기존 + 신규 전부; 기존 `art_safe`/`art_DEMO_TRAGIC_001` 테스트도 fallback·카탈로그로 유지)

- [ ] **Step 5: 커밋**

```bash
git add api/routers/ad_match.py tests/test_ad_match.py
git commit -m "feat(api): ad-match _load_article uses demo catalog + GET /api/ad-match/samples"
```

---

### Task 3: 웹 API 클라이언트 — `fetchAdMatchSamples()` (`web/lib/api-client.ts`)

**Files:**
- Modify: `web/lib/api-client.ts` (기존 `adMatch` 함수 ~273 근처)
- Verify: `cd web && npx tsc --noEmit`

- [ ] **Step 1: 타입 + 함수 추가** — `web/lib/api-client.ts`의 `adMatch` 함수 정의 바로 아래에 추가 (파일 상단 `PUBLIC_BASE` 상수 사용):

```typescript
export interface AdMatchSample {
  article_id: string;
  title: string;
  category_hint: string | null;
  expected_governance: 'skip:scandal' | 'skip:tragedy' | 'skip:minor_victim' | 'match';
}

export async function fetchAdMatchSamples(): Promise<AdMatchSample[]> {
  const res = await fetch(`${PUBLIC_BASE}/api/ad-match/samples`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`ad-match samples ${res.status}`);
  const data = (await res.json()) as { samples: AdMatchSample[] };
  return data.samples;
}
```

- [ ] **Step 2: 타입 체크 통과 확인**

Run: `cd web && npx tsc --noEmit`
Expected: PASS (에러 0)

- [ ] **Step 3: 커밋**

```bash
git add web/lib/api-client.ts
git commit -m "feat(web): add fetchAdMatchSamples API client"
```

---

### Task 4: 웹 셀렉터 동적화 + 거버넌스 배지 (`web/app/ad-match/page.tsx`)

**Files:**
- Modify: `web/app/ad-match/page.tsx`
- Verify: `cd web && npx tsc --noEmit`

- [ ] **Step 1: 하드코딩 SAMPLE_ARTICLES → fetch 기반 state로 교체**

`import` 에 `fetchAdMatchSamples`, `AdMatchSample` 추가 (from `'../../lib/api-client'`). 기존 `const SAMPLE_ARTICLES = [...]` 배열 정의를 삭제하고, 컴포넌트 본문에서:

```tsx
const [samples, setSamples] = useState<AdMatchSample[]>([]);
const [articleId, setArticleId] = useState<string>('');

useEffect(() => {
  fetchAdMatchSamples()
    .then((rows) => {
      setSamples(rows);
      // 기본 선택: 첫 skip 케이스 (Agent 거절 대비를 즉시 보여줌)
      const firstSkip = rows.find((r) => r.expected_governance.startsWith('skip'));
      setArticleId(firstSkip?.article_id ?? rows[0]?.article_id ?? '');
    })
    .catch(() => setSamples([]));
}, []);
```

(기존 `const [articleId, setArticleId] = useState(SAMPLE_ARTICLES[1].id);` 라인은 위 state 선언으로 대체된다 — 중복 선언 제거.)

- [ ] **Step 2: 셀렉터 렌더를 samples 기반으로 교체**

기존 `{SAMPLE_ARTICLES.map((a) => { ... })}` 블록을 다음으로 교체:

```tsx
{samples.map((a) => {
  const active = articleId === a.article_id;
  const willSkip = a.expected_governance.startsWith('skip');
  return (
    <button
      key={a.article_id}
      onClick={() => setArticleId(a.article_id)}
      className={active ? 'border-accent-400 bg-slate-800' : 'border-slate-700 bg-slate-900'}
    >
      <span className="block text-sm">{a.title}</span>
      <span className={willSkip ? 'text-amber-400 text-xs' : 'text-emerald-400 text-xs'}>
        {willSkip ? 'Agent 거절 예상' : '안전 매칭'}
      </span>
    </button>
  );
})}
```

(className 은 기존 페이지의 active/비active 스타일 관례를 따른다 — 위는 최소 형태이며, 기존 클래스 문자열이 있으면 그대로 재사용한다.)

- [ ] **Step 3: adMatch 호출 가드 추가** — `articleId`가 빈 문자열일 때 호출하지 않도록 기존 fetch effect/handler에 `if (!articleId) return;` 가드 추가.

- [ ] **Step 4: 타입 체크 통과 확인**

Run: `cd web && npx tsc --noEmit`
Expected: PASS (에러 0; `SAMPLE_ARTICLES` 참조 잔존 시 컴파일 에러로 드러남 → 모두 제거)

- [ ] **Step 5: 커밋**

```bash
git add web/app/ad-match/page.tsx
git commit -m "feat(web): ad-match selector fetches samples + governance badges"
```

---

### Task 5: CHANGELOG + 전체 검증

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: CHANGELOG `[Unreleased]` 최상단에 항목 추가**

```markdown
### Added — 시나리오 L 광고 매칭 시연 콘텐츠 확대 (2026-06-04)
- 데모 샘플 기사 2 → 6개: skip 3종(scandal·tragedy·minor_victim) + safe 3종(AI·핀테크·탄소중립). `data/synthetic/seeds.py:DEMO_AD_ARTICLES` 단일 카탈로그.
- 신규 `GET /api/ad-match/samples` — 셀렉터 단일 진실원. 웹 `ad-match/page.tsx`가 하드코딩 대신 fetch + 거버넌스 배지(Agent 거절 예상/안전 매칭).
- keyword/embedding은 광고 매칭, Agent만 민감 3종 skip하는 3-way 대비 완성. 전 기사 ADR-0004 준수(○○○ 익명).
```

- [ ] **Step 2: 전체 백엔드 테스트 + 타입 체크**

Run: `python3 -m pytest tests/test_ad_match.py -q && python3 -m compileall -q api data && cd web && npx tsc --noEmit`
Expected: pytest PASS, compile OK, tsc 에러 0

- [ ] **Step 3: 커밋**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): ad-match demo content expansion"
```

---

## Self-Review

**Spec coverage:** 6 기사(Task 1) ✓ / `/samples` 엔드포인트(Task 2) ✓ / `_load_article` 카탈로그화(Task 2) ✓ / 웹 동적 셀렉터(Task 4) ✓ / api-client(Task 3) ✓ / 테스트(Task 1·2) ✓ / CHANGELOG(Task 5) ✓ / 광고 인벤토리·민감 카테고리 변경 없음(YAGNI) ✓.

**Placeholder scan:** 모든 코드 step에 실제 코드 포함, ○○○는 의도된 콘텐츠. TBD 없음.

**Type consistency:** `DEMO_AD_ARTICLES`(dict), `list_demo_ad_articles()`(list[dict]), `ArticleSummary(article_id,title,content,topic_ids)`, `expected_governance` 문자열 enum, 응답 `body["results"][mode]["chosen_ad_id"|"reason_text"]`, `AdMatchSample` 필드 일관. `_detect_sensitive`/`TOPIC_TO_CATEGORY_HINTS`는 기존 코드 심볼.

**알려진 주의:** 웹 페이지의 정확한 className 관례는 구현 시 기존 코드를 확인해 재사용(최소 형태 제시). `art_safe_AI`는 균형 정당 언급 유지(ADR-0004상 허용); skip 케이스만 익명 단언.
