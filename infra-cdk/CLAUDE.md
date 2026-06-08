# infra-cdk/ — AWS CDK v2 (TypeScript) — 6 Stacks

`infra-cdk/`는 6 스택을 인스턴스화하는 모놀리식 CDK 앱. **공유 VPC를 import**하고 assembly 전용 리소스(SG 5개 + 모든 application 리소스)만 생성한다 (ADR-0006이 ADR-0001 D7의 전용 VPC 설계를 supersede).

## Stacks

```
infra-cdk/
├── bin/assembly.ts               # 엔트리포인트 — 6 스택 인스턴스화
└── lib/
    ├── network-stack.ts          # 공유 VPC import (10.100.0.0/16, 2-AZ) + SG 5개
    ├── data-stack.ts             # Neptune cluster, OpenSearch Serverless, S3 3종,
    │                             # DynamoDB 4종 (b2b-keys, ad-inventory, ad-impression, reader-profile)
    ├── compute-stack.ts          # ECS cluster, ALB, api+web Fargate (ARM64, 2/2),
    │                             # Ad Matcher Lambda (별도)
    ├── ai-stack.ts               # Bedrock KB, Guardrails (정치 중립성),
    │                             # AgentCore Memory store (3 namespaces)
    ├── edge-stack.ts             # CloudFront(B2C web) + CloudFront(B2B api),
    │                             # Lambda@Edge JWT, Cognito(3 pool: staff/subscriber/guest),
    │                             # API Gateway(B2B), Route53
    ├── observability-stack.ts    # CloudWatch dashboards, alarms,
    │                             # political_balance_score 메트릭
    └── lambda-edge/              # Lambda@Edge 함수 소스 (us-east-1 deploy)
```

## Stack Dependencies

```
network → data, compute, ai
data    → compute (Neptune endpoint), ai (KB 데이터 소스)
compute → edge (ALB origin)
ai      → compute (Guardrail ID env), edge (Bedrock 호출은 Lambda@Edge에서도)
edge    → (모든 user-facing)
observability → 모든 스택의 메트릭 구독
```

## Key Design Decisions

- **공유 VPC import** (ADR-0006, 2026-05-14): `vpc-0dfa5610180dfa628` (cc-on-bedrock-vpc, 10.100.0.0/16). gcc·retail·mfg와 동일 VPC + NAT GW 공유. assembly 전용 SG 5개만 신규. ADR-0001 D7 supersede.
- **3 Cognito 풀** (ADR-0003): staff, subscriber, guest 분리. Lambda@Edge에서 분기.
- **B2B API Gateway** (ADR-0003): 별도 도메인 (`api.assembly.example`). DynamoDB API Key store.
- **Ad Matcher Lambda 분리** (ADR-0004 Layer 6): API와 별도 Lambda. Bedrock 호출 + AdMatchDecision 저장.
- **Bedrock Guardrails 리소스** (ADR-0004 Layer 1): `assembly-political-neutrality-guardrail`. AI 스택에서 생성.
- **모든 Fargate ARM64**: `--platform linux/arm64`. x86 이미지는 ECS reject.

## Conventions

- **리소스 이름**: prefix `assembly-${env}-` (예: `assembly-dev-cluster`).
- **태깅**: 모든 리소스에 `Project=ontology-assembly`, `Env=${env}`, `ManagedBy=cdk` 태그.
- **IAM least privilege**: Resource는 ARN 범위 명시. wildcard `*` Resource 금지. security-auditor agent가 차단.
- **Secrets**: Secrets Manager + KMS. env에 평문 노출 금지.
- **스냅샷 테스트**: 모든 스택 `Template.fromStack().toJSON()` 비교 (CI 게이트).

## Stack-Specific Notes

### network-stack.ts
- **공유 VPC import** `vpc-0dfa5610180dfa628` (cc-on-bedrock-vpc, 10.100.0.0/16). 2-AZ (ap-northeast-2a, 2b), NAT GW 2개 공유 (ADR-0006).
- subnet ID 하드코딩: `SHARED_PUBLIC_SUBNETS` (2), `SHARED_PRIVATE_SUBNETS` (2 - ECS·Lambda 거주), `SHARED_ISOLATED_SUBNETS` (2 - Neptune 거주).
- SG 5개 신규: `assembly-alb-sg`, `assembly-app-sg`, `assembly-neptune-sg`, `assembly-os-sg`, `assembly-lambda-sg`.

### data-stack.ts
- Neptune: private isolated subnet, t3.medium(dev) / r6g.large(prod). Bulk Loader IAM role.
- OpenSearch Serverless: 컬렉션 `assembly-${env}-collection`, 인덱스 `assembly-${env}-kb-index`.
- S3 3종: raw-docs, uploads, synthetic-data.
- DynamoDB 4종: 모두 PAY_PER_REQUEST, TTL 활성화(`AdImpression` 14일).

### compute-stack.ts
- ECS Fargate ARM64 (Graviton). api/web 각 2 replica. 
- Ad Matcher Lambda는 Python 3.12 ARM64.
- 로더용 task definition도 같은 이미지 다른 command.
- 네이버 뉴스 시크릿 `assembly-dev/naver-news-api` → api task env `NAVER_NEWS_API_CLIENT_ID/SECRET` (`ecs.Secret.fromSecretsManager`, CDK가 실행역할 `GetSecretValue` 자동 grant). `members.py` 실 연관기사용 — 유효 키 주입 시 DEMO_PUBLIC_MODE와 독립 동작.

### ai-stack.ts
- Bedrock Guardrails: 차단 토픽 룰 인라인 정의.
- AgentCore Memory store: staff/subscriber/guest 3 namespaces.
- KB ingestion job 자동화는 Phase 5 polish.

### edge-stack.ts
- CloudFront 2개: B2C web, B2B api 분리.
- Lambda@Edge: JWKS 10-min TTL 캐시, 솔티드 쿠키 발급.
- Cognito 3개 pool: staff(`assembly-staff-pool`), subscriber(`assembly-subscriber-pool`), guest identity pool(`assembly-guest-pool`).
- API Gateway Usage Plan + API Key (DynamoDB).

### observability-stack.ts
- CloudWatch Dashboard: 위젯 2종 — ECS Service CPU/Memory + Ad Matcher Lambda invocations/errors.
- 알람 2종: `political_balance_score` 평균 < 0.8 (Critical, LowBalanceScoreAlarm), ALB 5xx > 1% (AlbHttp5xxAlarm). (Neptune CPU 알람은 미구현.)
- 로그 그룹 TTL 14일.

## Deployment

```bash
cd infra-cdk
npx cdk bootstrap aws://<account>/ap-northeast-2
npx cdk deploy --all --require-approval never
```

도메인 추가 (Phase 5):
```bash
npx cdk deploy assembly-edge -c domain=assembly.whchoi.net
scripts/cognito-update-callbacks.sh  # 안전한 full PUT
```

## Tests

```bash
npx cdk synth --quiet         # synth 무결성
npx jest --ci                 # 6 스택 스냅샷
```

스냅샷 갱신:
```bash
npx jest -u                   # CDK 변경 의도적일 때
```

`infra-cdk/test/__snapshots__/stacks.test.ts.snap`를 PR에 포함 (diff 리뷰).
