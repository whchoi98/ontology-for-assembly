# ADR 0008 — CloudFront VPC Origins + Internal ALB + WAF (Public ALB 제거)

- Status: Accepted (구현 완료, 2026-05-15)
- Date: 2026-05-15
- Related: [[ADR-0001]] (gcc 아키텍처 차용), [[ADR-0006]] (공유 VPC), [[ADR-0007]] (OpenSearch IAM tightening)

## Context

초기 dev 배포(2026-05-13)는 **Public Application Load Balancer**를 사용했다:
- ALB가 `0.0.0.0/0` SG로 인터넷 노출
- CloudFront → public ALB 경유로 viewer 트래픽 처리
- HTTP:80 → HTTPS:443 redirect listener
- ALB는 ACM 인증서 + custom 도메인 가능했지만 PoC에선 ALB DNS 직접 사용

문제점 (Kiro 리뷰 게이트, 2026-05-14):
1. **Public exposure가 0이 아님**: 누구나 ALB DNS 발견 시 직접 origin 호출 가능 → CloudFront/WAF 우회
2. **prefix-list SG의 신뢰 한계**: `com.amazonaws.global.cloudfront.origin-facing` prefix list로 SG inbound 제한 가능하지만, AWS managed prefix list가 *공식적 SLA가 없으며 IP 변동 시 수동 갱신* 필요. 또한 같은 prefix list가 *모든 AWS 계정 CloudFront*를 허용 → 다른 AWS 계정의 CloudFront도 통과 가능.
3. **PoC 시연 가치**: "AI 거버넌스 + 정치 중립성"이 핵심 narrative인데 *보안 architecture 자체*가 부주의하면 신뢰성 손상.

## Decision

**CloudFront VPC Origins (2024-11 GA)** 채택 — 내부 ALB(internet-facing scheme=`internal`)를 VPC Origin으로 직접 호출. Public ALB 완전 제거.

### 아키텍처

```
Viewer (HTTPS)
   │
   ▼
CloudFront (WAFv2 managed rules + rate-limit)
   │
   ▼
VPC Origin (PrivateLink 내부 연결)
   │
   ▼
Internal ALB (scheme=internal, 공인 IP 없음)
   │  HTTPS:443 only listener
   │  SG inbound: VPC Origin SG만 허용 (0.0.0.0/0 금지)
   ▼
ECS Fargate Tasks (api / web)
```

### 구성 (`infra-cdk/lib/edge-stack.ts` + `compute-stack.ts`)

1. **Internal ALB**: `scheme: 'internal'`, public IP 미할당. ALB SG inbound는 **VPC Origin SG만 허용**.
   - `0.0.0.0/0` inbound 금지
   - `com.amazonaws.global.cloudfront.origin-facing` prefix list 미사용 (의미 없음 — 어차피 public 진입점 없음)
2. **HTTPS:443 listener만**. HTTP:80 listener 제거.
3. **VPC Origin** (us-east-1 CloudFront에서 ap-northeast-2 ALB로): **Kiro 게이트 지적사항** — "Cross-region VPC Origins are not supported" → CloudFront distribution을 **ap-northeast-2에 생성**하도록 edge-stack region 변경.
4. **WAFv2 ACL** (CLOUDFRONT scope, `us-east-1` 강제):
   - `AWSManagedRulesCommonRuleSet` (Core RS) — 일반 OWASP top10
   - `AWSManagedRulesKnownBadInputsRuleSet` — 알려진 악성 입력
   - 사용자 정의 rate limit: 2000 req / 5분 / source IP
5. **모든 로그 활성화**:
   - CloudFront 표준 액세스 로그 → S3 (V1 ACL bucket 요건은 Phase 5에서 시뮬레이션)
   - WAF 로그 → CloudWatch Log Group `/aws/wafv2/assembly-dev`
   - ALB access log → S3 prefix `alb/`

### 검증 (Acceptance Criteria)

- [x] ALB DNS는 internet에서 lookup 불가능 (internal scheme, public IP 없음)
- [x] ALB SG에 0.0.0.0/0 inbound rule 없음
- [x] ALB listener는 HTTPS:443 only (HTTP:80 listener 없음)
- [x] 모든 viewer → origin 호출이 HTTPS (CloudFront Origin Protocol Policy = `https-only`)
- [x] WAF rules + rate limit 활성 (CloudWatch에서 BlockedRequests count 가시화)
- [x] SSE streaming (`/api/chat/stream`)이 정상 동작 — *ORIGIN_RESPONSE Lambda@Edge 미적용* 이라 chunked transfer 보존됨

## SSE 호환성 보존 (중요)

CloudFront에서 SSE chunked transfer가 깨지는 흔한 원인은 **ORIGIN_RESPONSE 단계 Lambda@Edge**가 응답 body 전체를 buffer한 뒤 변형하는 것. 본 아키텍처는:

- VIEWER_REQUEST Lambda@Edge만 사용 (Cognito JWT 검증)
- ORIGIN_RESPONSE / VIEWER_RESPONSE에 Lambda@Edge **미 attach**
- 응답 body 변형 0 → SSE delta chunk가 viewer까지 그대로 흐름

이 제약은 [[bedrock_invoke_stream]] (`api/services/bedrock.py:invoke_stream`)와 [[chat_router_stream]] (`api/routers/chat.py:chat_stream`)의 token-level delta emit이 CloudFront idle timeout(60s)을 reset하는 메커니즘과 짝.

## Trade-offs

### 채택의 비용

- **Cross-region 제약**: VPC Origins은 same-region만 지원 → us-east-1 CloudFront에서 ap-northeast-2 ALB 불가. CloudFront distribution이 ap-northeast-2에 생성되며 *지구 다른 지역 viewer는 지연 증가* (CDN cache는 글로벌 PoP에서 동작하므로 cache hit 시 영향 적음).
- **WAFv2 us-east-1 강제**: CLOUDFRONT scope WAF ACL은 us-east-1에만 생성 가능. CDK가 cross-region resource 관리 → `CrossRegionExportWriter` 패턴 + delete edge-stack 시 의존성 순서 주의.
- **CDK 스택 의존성**: edge-stack이 compute-stack의 ALB ARN을 소비 → edge-stack 삭제 시 cross-region export holder 해제 필요.

### 거부된 대안

1. **Public ALB + CloudFront prefix-list SG**: AWS managed prefix list는 *모든 AWS 계정* CloudFront를 허용 → 인접 계정의 CloudFront도 통과 가능. 사용자 확인: "AWS-managed prefix list 안 씀 (의미 없음 — 어차피 public 진입점이 없음)."
2. **API Gateway HTTP API + VPC Link**: 가능하지만 CloudFront WAF·캐시·custom domain 통합이 더 직관적. Lambda invoke 모델이 ECS Fargate와 mismatch.
3. **NLB + CloudFront**: NLB는 L4 (TCP), HTTP/HTTPS WAF rule 미적용 → 정책 거버넌스 손해.

## References

- AWS CloudFront VPC Origins 발표: https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-cloudfront-vpc-origins/
- AWSManagedRules group: https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups.html
- 코드: `infra-cdk/lib/edge-stack.ts`, `infra-cdk/lib/compute-stack.ts:internalAlbSecurityGroup`
- 시연 narrative: README §보안 + GuidedTour ops 단계
