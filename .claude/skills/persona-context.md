---
name: persona-context
description: How to apply the 6-persona system across routers, system prompts, UI sidebar/cards, and cohort filtering. Use when adding a new scenario, modifying persona-dependent behavior, or debugging persona-switching drift between backend and frontend.
---

# 6-Persona Context

이 프로젝트는 **6 페르소나** 시스템을 backend·frontend·LLM·UI 전체에 걸쳐 일관 적용한다. 페르소나가 한 곳에서만 바뀌면 정합성이 깨진다.

## 6 페르소나

| persona_id | 이름 | tier | 인증 |
|---|---|---|---|
| `editorial` | 편집국 | staff | Cognito staff 그룹 |
| `data_ai` | 데이터·AI | staff | Cognito staff 그룹 |
| `ad_sales` | 광고·세일즈 | staff | Cognito staff 그룹 |
| `general_reader` | 일반 독자 | b2c_free | Cognito Guest Identity Pool + 게스트 쿠키 |
| `paid_subscriber` | 유료 구독자 | b2c_paid | Cognito subscriber 그룹 |
| `b2b` | 기업/B2B 정책 인텔리전스 | b2b | API Gateway + API Key |

## SSOT — `api/services/persona.py:PERSONA_REGISTRY`

모든 페르소나 정보는 한 dict에서 시작. 절대 라우터·프론트에 페르소나 키 하드코드 금지.

```python
PERSONA_REGISTRY: dict[PersonaId, PersonaDef] = {
    "editorial": {
        "name_kr": "편집국",
        "tier": "staff",
        "kpi_focus": ["취재 신선도", "발굴 가능성", "출처 신뢰도"],
        "tone": "차분, 사실 중심",
        "scenario_priority": ["C", "B", "K", "M", "A", "D"],
        "default_cohort": ["real"],
        "system_prompt_suffix": "당신은 한국 언론사 편집국 기자의 분석 보조 도구입니다. ...",
        "ad_policy": "no_ads",
    },
    ...
}
```

## 라우터 패턴

```python
@router.post("/api/some-scenario")
async def some_scenario(req: SomeRequest, persona_id: PersonaId = Depends(get_persona)):
    persona = PERSONA_REGISTRY.get(persona_id) or PERSONA_REGISTRY["editorial"]  # fallback
    cohort = cohort_service.select(persona_id, scenario_code="X")
    sys_prompt = persona["system_prompt_suffix"] + NEUTRALITY_GUARD_SUFFIX
    # ... 라우터 로직
    response.tone = persona["tone"]
    response.bias_score = compute_bias(response.text)
    return response
```

## Frontend 패턴

- `web/components/PersonaSwitch.tsx` — 6개 페르소나 토글 (drop-down + 검색).
- 페르소나 전환 시 `localStorage.setItem('persona_id', ...)` + Context Provider 갱신.
- 모든 API client 호출에 `X-Persona-Id` header 자동 첨부.
- 사이드바·홈 카드는 `PERSONA_REGISTRY.scenario_priority` 순서로 자동 정렬.

## 페르소나별 광고 정책

`ad_policy ∈ {no_ads, full_ads_agent, no_ads_subscriber, api_only}`:
- `editorial`, `data_ai`, `ad_sales` → `no_ads` (내부)
- `general_reader` → `full_ads_agent` (Agent 판단 모드)
- `paid_subscriber` → `no_ads_subscriber` (구독 가치)
- `b2b` → `api_only` (광고 노출 없이 데이터 API)

## 페르소나별 응답 필드

```typescript
interface ScenarioResponse {
  // 공통
  data: ScenarioData
  data_source: 'real' | 'synthetic' | 'external' | 'mixed'
  bias_score: number  // 0-1

  // 페르소나별
  ad_decision?: AdMatchDecisionRef  // general_reader만
  pdf_export_url?: string  // paid_subscriber, b2b
  api_quota_remaining?: number  // b2b
  tour_step_hint?: string  // general_reader (가이드)
}
```

## 새 시나리오 추가 시 페르소나 적용 체크리스트

1. `PERSONA_REGISTRY` 6개 entry에 새 scenario_code를 priority list에 추가할지 결정.
2. 라우터에서 6 페르소나 모두에 대해 동작 확인 (각 페르소나 응답 모양 다를 수 있음).
3. UI 페르소나 카드에 시나리오 추가 (홈 페이지 + Sidebar + GuidedTour).
4. `tests/test_smoke.py`에 6 페르소나 × 새 시나리오 parametrize entry 6개 추가.
5. `scripts/eval_wow_queries.py`에 6개 wow query 추가 (페르소나별 1개씩).

## 디버깅 - 페르소나 drift

- backend에서 보낸 페르소나와 frontend가 표시하는 페르소나가 다르면 `localStorage` 캐시 stale 가능성.
- 시나리오 응답이 한 페르소나에서만 깨지면 `cohort.select()` 또는 `PERSONA_REGISTRY` 누락.
- `political_balance_score`가 페르소나마다 다르면 system prompt 가드 누락 가능.

## 정치 중립성과 페르소나

- **모든 페르소나** 공통으로 정치 중립성 가드레일이 LLM 호출에 적용된다 (B2B도 예외 없음).
- 페르소나는 `tone` (어조)와 `kpi_focus`만 다르고, 사실 분석 자체의 중립성은 동일.
- `paid_subscriber`도 "심층 분석"이지만 가치 판단 단정은 금지.
