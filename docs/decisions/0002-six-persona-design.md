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

페르소나마다 다음 5요소가 결정된다:
- `tier` (인증 그룹)
- `kpi_focus` (KPI 우선순위)
- `tone` (LLM 시스템 프롬프트 어조)
- `scenario_priority` (시나리오 정렬·홈 카드 하이라이트)
- `default_cohort` (data source 필터)
- `ad_policy` (광고 노출 정책: no_ads / full_ads_agent / no_ads_subscriber / api_only)

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

## References

- 차용 원본 gcc ADR-0007 (PERSONA_REGISTRY SSOT 패턴)
- spec §3.2 페르소나 × 시나리오 매트릭스
- spec §3.4 시나리오 L 광고 매칭 (페르소나별 ad_policy)
- ADR-0003 (대고객 서비스 확장 — 인증·요금제 다층화 상세)
