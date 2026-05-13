# ADR 0003 — Customer-Facing Extension (B2C + B2B)

- Status: Accepted
- Date: 2026-05-13

## Context

ADR-0002에서 6 페르소나 중 3개를 대고객(B2C + B2B)으로 정함. 이는 gcc의 단일 Cognito + Lambda@Edge JWT 패턴만으로는 처리 불가능하다. 익명 일반 독자, 유료 구독자, B2B 기업 고객 3 tier가 동시 접근하므로 인증·요금제·rate limit·개인화 추적 4가지 신규 레이어가 필요하다.

## Decision

다음 4 레이어를 gcc 베이스에 추가:

### 1. 인증 다층화

| 페르소나 | 인증 메커니즘 |
|---|---|
| staff 3종 | Cognito user pool (`assembly-staff-pool`) + 그룹(`editorial`, `data_ai`, `ad_sales`) |
| `general_reader` | Cognito Guest Identity Pool (`assembly-guest-pool`) + 솔티드 해시 쿠키 |
| `paid_subscriber` | Cognito user pool (`assembly-subscriber-pool`) + tier 그룹(`free`, `standard`, `premium`) |
| `b2b` | API Gateway + API Key (DynamoDB `assembly-b2b-keys`) + Usage Plan |

Lambda@Edge에서 인증 분기:
- staff/subscriber → Cognito JWT 검증
- general_reader → 쿠키 검증 + 신규 쿠키 발급
- b2b → API Gateway 별도 도메인 (`api.assembly.example`)

### 2. 요금제·feature gate

`SubscriptionTier` 노드 (Neptune):
- `free` — 일반 독자, 일일 5개 인사이트, 광고 노출
- `standard` — 유료, 무제한 인사이트, 알림, 광고 미노출
- `premium` — 유료, + PDF 리포트, + 의원 비교 도구

Feature gate는 라우터 진입 시 `tier_required(scenario_code, persona_id)`로 체크. 부족 시 402 + upgrade CTA.

### 3. Rate limit

| Tier | Limit |
|---|---|
| Guest (general_reader) | 100 req/15min/IP |
| Subscriber free | 500 req/15min/user |
| Subscriber paid | 무제한 (가드만 1k/min) |
| B2B | API Gateway Usage Plan 별도 (키별 차등 - 기본 1000/min) |

### 4. 개인화 추적 — Reader 노드 + 그래프

`Reader` 노드를 Neptune에 적재. 익명성 보장:
- `reader_id` = 솔티드 SHA-256 해시 (쿠키 ID 원본 미저장)
- IP, UA 원본 미저장
- `political_leaning` 등 정치 성향 추론 필드 **절대 생성·저장 금지** (SECURITY.md §3 + ADR-0004)
- `interests` (관심 토픽), `region` (시도 단위만), `since` (시간만)

관계:
- `(Reader)-[:READ]->(ReadingEvent)-[:OF]->(Article)`
- `(Reader)-[:FOLLOWS]->(Person|Topic)`
- `(Reader)-[:BOOKMARKED]->(Article|Bill)`
- `(Reader)-[:HAS_TIER]->(SubscriptionTier)`

개인화는 Personalization Lambda가 `Reader` 그래프에서 추론. Bedrock 임베딩으로 reading_event vector 평균 → 추천 토픽.

## Consequences

**Positive**:
- 6 페르소나가 모두 적절한 인증·요금제·rate limit으로 분리.
- B2C 광고 노출과 B2B API 응답이 같은 코드 경로로 처리 가능 (Ad Matcher는 Lambda 분리).
- Reader 그래프가 시나리오 D(페르소나 매칭) / F(룩어라이크) / L(광고)에 데이터 제공.

**Negative / 비용**:
- Cognito 2개 + API Gateway 1개 = 인증 3개 시스템 운영 부담.
- Reader 노드가 ~50,000개 합성으로 늘어남 → Neptune 노드 총수 100만+ 도달.
- 익명성 가드(`Reader.political_leaning` 금지) 코드 리뷰 부담 증가.

**새 제약**:
- 모든 `Reader` 관련 PR은 security-auditor agent가 반드시 검토 (`Reader.political_leaning` 등 금지 필드 추가 감지).
- B2B API는 `api/b2b/` 별도 namespace로 분리 (응답 모양 다름).
- B2C와 internal API는 같은 Next.js + FastAPI를 공유하되, 페르소나별 응답 후처리로 분기.

## Alternatives Considered

1. **단일 Cognito user pool + 그룹만** — staff/subscriber 모두 한 풀에. 익명 일반 독자 처리 불가. **기각**.
2. **별도 도메인 4개** — B2B / 일반 독자 / 유료 구독자 / staff 각각 독립 도메인 + 독립 인증. 운영 복잡도 폭증. **기각**.
3. **요금제 없이 무료만** — 단순하지만 시연 메시지 "AI 미디어 수익화" 사라짐. **기각**.
4. **개인화 미적용** — Reader 그래프 없음. 시나리오 D/F/L 데이터 부족. **기각**.

## References

- ADR-0002 (6 페르소나 설계)
- ADR-0004 (정치 중립성 — Reader.political_leaning 금지의 근거)
- spec §1 인프라 토폴로지 (4 인증 분기)
- spec §4 클래스 — Reader, ReaderProfile, SubscriptionTier
- SECURITY.md §3 (독자 프라이버시)
