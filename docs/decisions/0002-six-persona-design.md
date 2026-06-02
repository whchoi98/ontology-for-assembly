# ADR 0002 — Six-Persona Design (3 internal + 3 customer-facing)

- Status: Accepted
- Date: 2026-05-13

## Context

gcc는 5 부서 페르소나(마케팅·고객전략·데이터·AI·CRM·회원사업·리테일영업) 모두 GSC 임직원으로 구성. 언론사 데모도 같은 패턴(5개 내부 부서)으로 갈지, 대고객 페르소나를 포함시킬지 결정 필요.

사용자가 디자인 협의 과정에서 다음 두 가지를 명시:
1. "고객향으로 서비스 한다는 의미를 추가하는 것도 가능한가요?" (대고객 페르소나 포함 의향)
2. "B로 만들고, C의 일반 독자, 유료 구독자 포함" (하이브리드 + B2C 세분화)

언론사는 본질적으로 B2C 미디어 비즈니스 + B2B 정책 인텔리전스 매출원도 존재. 내부 페르소나만으로는 매출/고객가치 메시지를 시연에 담을 수 없다.

## Decision

**6 페르소나** 구성을 채택. 내부 3 + 대고객 3.

| persona_id | 이름 | tier | 인증 | 주력 시나리오 |
|---|---|---|---|---|
| `editorial` | 편집국 | staff | Cognito staff | C·B·K·M |
| `data_ai` | 데이터·AI | staff | Cognito staff | E·J·K·N |
| `ad_sales` | 광고·세일즈 | staff | Cognito staff | L·G·F |
| `general_reader` | 일반 독자 | b2c_free | Cognito Guest + 쿠키 | A·B·H·M |
| `paid_subscriber` | 유료 구독자 | b2c_paid | Cognito subscriber | C·K·M·D |
| `b2b` | 기업·B2B 정책 인텔리전스 | b2b | API Gateway + API Key | A·C·J·K |

SSOT는 `api/services/persona.py:PERSONA_REGISTRY`. ADR-0007(gcc)과 동일하게 dict 상수로 유지(persona DB 모델 도입은 보류).

각 페르소나는 `PersonaDef`(TypedDict) **8개 필드**로 정의된다:
- `name_kr` — 표시 이름 (응답 헤더·UI)
- `tier` — 인증·청중 그룹 (`staff` / `b2c_free` / `b2c_paid` / `b2b`)
- `kpi_focus` — KPI 우선순위 (system prompt + UI)
- `tone` — LLM 어조
- `scenario_priority` — 시나리오 정렬·홈 카드 하이라이트 (현재 A–N 14개만 — 아래 Implementation Notes 참조)
- `default_cohort` — data source 필터 (`real` / `synthetic` / `external` / `*`)
- `ad_policy` — 광고 노출 정책 (`no_ads` / `full_ads_agent` / `no_ads_subscriber` / `api_only`)
- `system_prompt_suffix` — 페르소나별 어조·관심사 지시 (프롬프트 4번째 레이어)

### 4-tier 프레젠테이션 그룹핑

페르소나는 4개 tier로 묶여 Sidebar·PersonaSwitch에서 헤더로 분리 노출된다 (`TIER_GROUP_KR` / `TIER_GROUP_ORDER`):

| tier | 그룹 라벨 | 페르소나 | ad_policy |
|---|---|---|---|
| `staff` | 미디어/신문사 내부용 | editorial · data_ai · ad_sales | no_ads |
| `b2c_free` | 구독자용 (무료) | general_reader | full_ads_agent |
| `b2c_paid` | 유료 구독자용 | paid_subscriber | no_ads_subscriber |
| `b2b` | B2B 정책 인텔리전스 | b2b | api_only |

### 5-layer system prompt 합성

`persona.system_prompt(persona_id, scenario_code)`는 5개 레이어를 순서대로 합성한다:

1. **base** — 시스템 정체성 + `name_kr`·tier·`tone`·`kpi_focus`·시나리오 코드
2. **tier_directive** (`_TIER_DIRECTIVE`) — tier별 청중 framing (응답 구조·전문 용어 수준·premium/광고 안내)
3. **response_header_directive** — `**[tier_group — name_kr]**` Markdown 헤더 강제 (cross-persona 비교 식별자)
4. **system_prompt_suffix** — 페르소나별 어조·관심사
5. **NEUTRALITY_GUARD_SUFFIX** — ADR-0004 Layer 2 정치 중립성 가드 (4원칙, 모든 페르소나 예외 없음)

헬퍼 함수: `get()`(editorial fallback + persona_id 주입) · `tier_directive()` · `response_header_directive()` · `system_prompt()` · `ad_policy_for()` · `scenario_order()` · `all_persona_ids()`.

### Web mirror (`web/lib/personas.ts`)

웹은 백엔드 SSOT를 미러하되 **UI 전용 필드**를 추가한다 (백엔드엔 없음):
- `emoji` (✍️ 📊 🎯 👤 ⭐ 🏢) · `PERSONA_ICON` (lucide: PenTool / LineChart / Megaphone / User / Crown / Building2) · `description`
- `PERSONA_PRIMARY_SCENARIOS` — 사이드바 하이라이트용 top 4–5 (백엔드 `scenario_priority` 상위 부분집합)
- `DEFAULT_PERSONA = 'editorial'`
- 변경 시 백엔드와 양쪽 동시 갱신 필요 (향후 `GET /api/personas` fetch로 단일화 가능).

## Consequences

**Positive**:
- B2C·B2B 매출 흐름까지 데모에 포함 → CxO 청중에 신규 매출원 메시지 직관 전달.
- 같은 14개 시나리오를 6 페르소나가 6가지 다른 화면으로 보는 풍부함.
- 시나리오 L(광고 매칭)이 `general_reader` 페르소나에 자연스럽게 연결되어 거버넌스 메시지가 살아남.

**Negative / 비용**:
- gcc 5 부서 대비 인증 다층화 필요 (Cognito user pool + Guest Identity Pool + API Gateway API Key 3개 인증 시스템).
- 페르소나마다 응답 모양(`ad_decision`, `pdf_export_url`, `api_quota_remaining`, `tour_step_hint`)이 약간 다름 → 타입 안전성 주의.
- 6 페르소나 × 14 시나리오 = 84 wow-query 케이스로 평가 케이스 증가.

**새 제약**:
- 모든 라우터는 `persona_id`를 받아 `PERSONA_REGISTRY` lookup. 누락 시 `editorial` fallback.
- 새 페르소나·시나리오 추가 시 `PERSONA_REGISTRY` 6개 entry 모두 갱신 + `scripts/eval_wow_queries.py` 6 케이스 추가.
- Cognito·API Gateway·DynamoDB(b2b-keys) IAM 권한이 페르소나별로 분리되어야 함.

## Alternatives Considered

1. **A. 내부 전용 5개 (gcc 원형)** — 광고/세일즈 + 편집국 + 데이터·AI + 독자CRM + 현장취재. 내부 효율 메시지만 전달. **기각** — 사용자 명시 대고객 의향.
2. **B. 하이브리드 3+2** — 내부 3 + 독자(B2C) + 기업(B2B). 5개 유지. 단순하지만 B2C 차별(무료/유료)이 사라짐. **기각** — 사용자가 C의 독자 세분화 명시.
3. **C. 고객 중심 5+** — 내부 2 + 일반 독자 + 유료 구독자 + B2B 3개. 광고/세일즈 부서가 빠짐. **기각** — 시나리오 L 운영 콘솔이 어색.
4. **확장 8개** — 6개 + 정치 입문자 + 학생/연구자. 너무 많아 시연 시간 부족. **기각**.

## Implementation Notes (2026-06-02)

원 결정(6 페르소나, 3+3)은 유지. 이 ADR을 실제 구현에 맞춰 동기화하며 다음을 확인:

- 구현된 페르소나 설계는 원 ADR의 "5요소"보다 넓음 — `PersonaDef` 8필드 + 4-tier 그룹핑 + 5-layer 프롬프트 합성 + web UI 전용 필드(emoji/icon/description). 위 Decision 섹션에 반영 완료.
- **알려진 갭 — `scenario_priority`는 A–N(14개)만 커버**. 앱은 이후 23 시나리오(A–W)로 확장됐으나(Phase 4f O–W), 각 페르소나의 `scenario_priority`와 web `PERSONA_PRIMARY_SCENARIOS`는 아직 O–W를 포함하지 않음. 사이드바에서 O–W는 페르소나 우선순위 밖(`otherScenarios`)으로 정렬됨. 페르소나별 O–W 우선순위 부여는 후속 작업.
- 페르소나 수는 6개로 고정 — backend `PersonaId` Literal, web `PersonaId` union, `PERSONA_REGISTRY`, `PERSONAS` 모두 정확히 6개로 일치(추가 페르소나 없음).

## References

- 차용 원본 gcc ADR-0007 (PERSONA_REGISTRY SSOT 패턴)
- spec §3.2 페르소나 × 시나리오 매트릭스
- spec §3.4 시나리오 L 광고 매칭 (페르소나별 ad_policy)
- ADR-0003 (대고객 서비스 확장 — 인증·요금제 다층화 상세)
