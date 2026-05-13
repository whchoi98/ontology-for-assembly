# SECURITY.md

이 문서는 `ontology-for-assembly` PoC 데모의 **보안·프라이버시·정치 중립성** 정책을 정리합니다. PoC 단계에서 의도적으로 완화된 항목과 production 이관 시 반드시 강화해야 할 항목을 명시합니다.

## 위협 모델 한 줄 요약

PoC 단계 청중: CxO·임원·아키텍트가 라이브 시연을 보는 환경. 시연 도중 ① 자격 증명 유출, ② 정치 편향·정당 비방·인신 공격 출력, ③ 개인 식별 가능 정보(독자) 노출, ④ 광고 매칭 부적절(정치 민감 콘텐츠에 무관·논쟁 유발 광고 노출) — 이 네 가지를 우선 차단합니다.

## 1. 자격 증명·비밀 관리

| 자산 | 보관 | 회전 정책 |
|---|---|---|
| Cognito client secret | Secrets Manager | 90일 |
| CloudFront ↔ ALB origin token | Secrets Manager + Lambda@Edge env (KMS) | 90일 |
| 국회 OpenAPI key | SSM Parameter Store (SecureString) | 발급 정책에 따름 |
| 네이버 뉴스 API client_id/secret | Secrets Manager | 30일 |
| B2B API keys | DynamoDB (KMS) + Secrets Manager 마스터 키 | 사용자별 회전 |
| Bedrock 인증 | IAM role (Fargate task) | 세션 토큰 자동 |

`.claude/hooks/scrub-secrets.sh`가 AKIA/ASIA/JWT/PGP/Slack/GitHub PAT 패턴을 **PreToolUse + PostToolUse** 모두에서 감지하여 차단합니다.

## 2. 정치 중립성 가드레일 (ADR-0004)

PoC 도메인 특성상 **반드시** 적용:

- **Bedrock Guardrails 입력 스크럽** (시나리오 B·C·I): 특정 정당명 비방, 정치인 모욕 표현, 종교·성별·지역 차별 어휘 차단.
- **출력 필터**: LLM 응답에서 "○○당이 잘못했다", "○○ 의원은 무능하다" 등 단정적 가치 판단 표현 변환 또는 차단.
- **사전 검증 시연 질문 풀**: `scripts/eval_wow_queries.py`에 등록된 5개 질문만 라이브 시연에 사용. 자유 입력은 사전 리허설된 백업 모드.
- **편향 메트릭 모니터링**: 시나리오 K(이상치)에서 한쪽 정당 의원만 부각되지 않도록 `political_balance_score` 자동 계산.

## 3. 독자(B2C) 프라이버시

| 페르소나 | 식별 | 저장 |
|---|---|---|
| 일반 독자 (Anonymous) | Cognito Guest Identity Pool, 게스트 쿠키 (해시) | Neptune `Reader` 노드 - 해시 ID만, IP·UA 미저장 |
| 유료 구독자 | Cognito user pool subscriber 그룹 | `Reader` 노드 + email (해시 검색) |
| 광고 노출 이벤트 | DynamoDB `AdImpression` | 14일 TTL, reader_id는 솔티드 해시 |

**저장 금지**: IP, User-Agent 원본, GPS, 광고 식별자(IDFA/AAID), 정치 성향 추론 결과(`Reader.political_leaning` 등의 필드 절대 생성·저장 금지).

## 4. 광고 매칭 윤리 (시나리오 L)

`api/services/ad_matcher.py`의 Agent 판단 모드는 다음 상황에서 광고 노출을 자동 생략합니다:

- 비극·재난·인명 피해 관련 콘텐츠
- 특정 정치인 비위·의혹 관련 콘텐츠
- 미성년자·범죄 피해자 관련 콘텐츠
- 광고주의 정치 성향이 콘텐츠와 정면 충돌하는 경우

Agent 판단 결과는 `AdMatchDecision` 노드에 reasoning trace로 저장하여 운영 콘솔에서 사후 감사 가능.

## 5. IAM least privilege

- ECS Fargate task role: Neptune `neptune-db:*` (해당 클러스터 ARN 한정), OpenSearch `aoss:APIAccessAll` (해당 컬렉션), Bedrock `bedrock:InvokeModel` (지정 model ARN), AgentCore `bedrock-agentcore:*` (지정 store)
- Lambda@Edge: Cognito JWKS read-only + Secrets Manager 해당 시크릿만 GetSecretValue
- Ad Matcher Lambda: Bedrock + DynamoDB AdInventory/AdImpression 한정
- 모든 IAM 정책은 `infra-cdk/lib/*-stack.ts`에서 ARN 범위로 좁힘. wildcard `*` Resource 금지.

## 6. 네트워크

- Neptune은 private subnet, ECS API 보안 그룹에서만 8182 ingress.
- OpenSearch Serverless는 VPC 엔드포인트 경유.
- ALB ingress는 `com.amazonaws.global.cloudfront.origin-facing` prefix list만 허용.
- CloudFront 다중 origin: web (B2C public), api/b2b (API key gated).

## 7. PoC 의도적 완화 사항 (production 이관 시 강화)

| 항목 | PoC | production |
|---|---|---|
| `DEMO_PUBLIC_MODE` | 시연용 true 옵션 존재 | 반드시 false, env 변수 자체 제거 권장 |
| 합성 독자 데이터 | 명시 합성, 출처 배지로 구분 | 미사용. 실 행동 데이터로 학습 |
| 광고 매칭 데이터 | 합성 광고 인벤토리 | 광고주 SSP 연동 |
| B2B API rate limit | 단일 키당 100 req/min | API Gateway Usage Plan, 키별 차등 |
| 백업 영상 | 시연 실패 대비 자동 녹화 | 미적용 |

## 8. 데이터 출처 투명성

모든 화면 상단의 `DataSourceBadge` 컴포넌트로 다음 3종을 명시:
- 🟢 **real** — 국회 OpenAPI 원본
- 🟡 **synthetic** — 독자·광고·기사 합성 (PoC 한정)
- 🔵 **external** — SNS·뉴스·여론조사 외부 시그널

## 9. 사고 대응

PoC 단계에서 시연 중 부적절한 출력이 감지되면:
1. 즉시 백업 영상으로 전환 (시연자 단축키)
2. 사후 `AdMatchDecision`/`Statement` 노드 검사
3. Guardrails 룰 보강 후 재배포

운영자 연락: whchoi98@gmail.com
