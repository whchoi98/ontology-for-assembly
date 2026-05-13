# Runbook 01 — First Deployment

`ontology-for-assembly` 첫 배포 절차. Plan 1 (Foundation) 인수 기준에 사용.

## Prerequisites

- AWS 계정에 Bedrock·Neptune·OpenSearch Serverless·AgentCore 활성화 (ap-northeast-2)
- AWS CLI v2 + IAM Identity Center 또는 IAM 자격증명
- Node.js 20+, Python 3.12+, Docker linux/arm64
- AWS CDK v2.150+
- 국회 OpenAPI key (https://open.assembly.go.kr 활용신청)

## Step 1 — AWS account bootstrap

```bash
export AWS_REGION=ap-northeast-2
export AWS_PROFILE=<your-profile>

# CDK bootstrap (account별 1회)
cd infra-cdk
npx cdk bootstrap aws://<account>/ap-northeast-2

# us-east-1도 부트스트랩 (Lambda@Edge 배포 위치)
npx cdk bootstrap aws://<account>/us-east-1
```

## Step 2 — Secrets 등록

```bash
# 국회 OpenAPI key
aws secretsmanager create-secret \
  --name assembly-dev/assembly-openapi-key \
  --secret-string '{"key":"<your-key>"}'

# 네이버 뉴스 API
aws secretsmanager create-secret \
  --name assembly-dev/naver-news-api \
  --secret-string '{"client_id":"<id>","client_secret":"<secret>"}'

# CloudFront ↔ ALB origin token (CDK가 자동 생성하지만 미리 등록 가능)
```

## Step 3 — CDK deploy (6 스택)

```bash
cd infra-cdk
npx cdk deploy --all --require-approval never
```

스택 순서: network → data → ai → compute → edge → observability.
배포 시간 약 25–35분 (Neptune cluster 생성 가장 김).

## Step 4 — Cognito 사용자 프로비저닝

```bash
# staff 데모 계정 (편집국·데이터·AI·광고/세일즈)
./scripts/provision_demo_accounts.sh --staff

# subscriber 데모 계정
./scripts/provision_demo_accounts.sh --subscriber

# B2B API key 생성
./scripts/provision_b2b_key.sh --label "demo-b2b" --rate-limit 1000
```

## Step 5 — 컨테이너 이미지 빌드·푸시

```bash
SHA=$(git rev-parse --short HEAD)
ECR_BASE=$(aws ecr describe-repositories --repository-names assembly-dev-api --query 'repositories[0].repositoryUri' --output text | cut -d/ -f1)

# ECR login
aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_BASE"

# API 이미지
docker build --platform linux/arm64 -f api/Dockerfile \
  -t "$ECR_BASE/assembly-dev-api:$SHA" \
  -t "$ECR_BASE/assembly-dev-api:latest" .
docker push "$ECR_BASE/assembly-dev-api:$SHA"
docker push "$ECR_BASE/assembly-dev-api:latest"

# Web 이미지
docker build --platform linux/arm64 -f web/Dockerfile \
  -t "$ECR_BASE/assembly-dev-web:$SHA" \
  -t "$ECR_BASE/assembly-dev-web:latest" .
docker push "$ECR_BASE/assembly-dev-web:$SHA"
docker push "$ECR_BASE/assembly-dev-web:latest"
```

## Step 6 — 데이터 적재 (one-shot ECS task)

```bash
aws ecs run-task \
  --cluster assembly-dev-cluster \
  --task-definition assembly-dev-api \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<priv-subnet-id>],securityGroups=[<api-sg-id>],assignPublicIp=DISABLED}" \
  --overrides '{
    "containerOverrides":[{
      "name":"api",
      "command":["python","-m","data.load","--neptune","--opensearch","--from-s3"],
      "environment":[{"name":"DATA_SOURCE","value":"assembly_api"}]
    }]
  }'
```

적재 완료 확인 (CloudWatch logs):
```bash
aws logs tail /ecs/assembly-dev-api --since 30m --filter-pattern "load completed"
```

## Step 7 — ECS 서비스 롤아웃

```bash
aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-api --force-new-deployment
aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-web --force-new-deployment
```

## Step 8 — Smoke test

```bash
DOMAIN=$(aws cloudformation describe-stacks --stack-name assembly-edge \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicDomain`].OutputValue' --output text)

# Health checks
curl -fsS "https://$DOMAIN/healthz"
curl -fsS "https://$DOMAIN/api/healthz"

# 시나리오 A (검색)
curl -fsS -X POST "https://$DOMAIN/api/search" \
  -H 'content-type: application/json' \
  -H 'X-Persona-Id: editorial' \
  -d '{"q":"AI 관련 법안","top_k":5}' | jq '.hits | length'

# 시나리오 L (광고 매칭 - 일반 독자)
curl -fsS -X POST "https://$DOMAIN/api/ad-match" \
  -H 'content-type: application/json' \
  -H 'X-Persona-Id: general_reader' \
  -d '{"article_id":"demo_001","mode":"agent"}' | jq '.decision.allowed'
```

## Step 9 — Wow-query 평가

```bash
python3 scripts/eval_wow_queries.py --cf-domain "$DOMAIN"
```

Plan 1 인수 기준: 통과율 ≥85%, political_balance_score 평균 ≥0.8.

## Rollback

```bash
# 이전 SHA 태그로 task-def revision 등록 후 update-service
aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-api \
  --task-definition assembly-dev-api:<prev-revision>
```

## Teardown (개발 환경만)

`cdk destroy`는 `.claude/settings.json` deny list에 있어 차단됨. 수동 절차:

1. ECS 서비스 desired count 0
2. ECR 이미지 삭제 (`aws ecr batch-delete-image`)
3. S3 버킷 비우기 (versioned 객체 + delete markers)
4. CDK destroy 활성화 일시 (`.claude/settings.local.json`에 임시 allow)
5. `npx cdk destroy --all`
6. settings.local.json 원복

## 관련

- spec §1 인프라 토폴로지
- ADR-0001 (gcc 패턴 차용)
- `.claude/commands/deploy.md` (Claude Code에서 자동 실행)
