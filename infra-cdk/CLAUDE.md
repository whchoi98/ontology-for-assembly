# infra-cdk/ — AWS CDK v2 (TypeScript) — 6 Stacks

`infra-cdk/`는 6 스택을 인스턴스화하는 모놀리식 CDK 앱. assembly 전용 리소스만 생성 (gcc와 달리 retail VPC import 없음 — ADR-0001).

## Stacks

```
infra-cdk/
├── bin/assembly.ts               # 엔트리포인트 — 6 스택 인스턴스화
└── lib/
    ├── network-stack.ts          # VPC (10.30.0.0/16, 3-AZ) + SGs
    ├── data-stack.ts             # Neptune cluster, OpenSearch Serverless, S3 4종,
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

- **신규 VPC** (ADR-0001 D7): assembly 독립 운영. gcc의 retail VPC import 패턴 미적용.
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
- 3-AZ, public + private(NAT) + isolated subnet.
- VPC CIDR `10.30.0.0/16` (gcc `10.10.x`, retail `10.20.x`와 분리).
- SG: `assembly-api-sg`, `assembly-neptune-sg`, `assembly-os-sg`, `assembly-lambda-edge-sg`.

### data-stack.ts
- Neptune: private isolated subnet, t3.medium(dev) / r6g.large(prod). Bulk Loader IAM role.
- OpenSearch Serverless: 컬렉션 `assembly-${env}-collection`, 인덱스 `assembly-${env}-kb-index`.
- S3 4종: raw-docs, uploads, synthetic-data, demo-recordings.
- DynamoDB 4종: 모두 PAY_PER_REQUEST, TTL 활성화(`AdImpression` 14일).

### compute-stack.ts
- ECS Fargate ARM64 (Graviton). api/web 각 2 replica. 
- Ad Matcher Lambda는 Python 3.12 ARM64.
- 로더용 task definition도 같은 이미지 다른 command.

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
- CloudWatch Dashboard: 시나리오 14개 × 페르소나 6개 latency, error rate.
- 알람: `political_balance_score` 평균 < 0.8 (Critical), 5xx > 1%, Neptune CPU > 80%.
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
