---
description: Deploy the full assembly stack (images + 6 CDK stacks + data load + ECS rollout)
---

Deploy in the following order, stopping at first failure:

1. **Build ARM64 images**:
   ```bash
   SHA=$(git rev-parse --short HEAD)
   docker build --platform linux/arm64 -f api/Dockerfile -t <ecr>/assembly-dev-api:$SHA -t <ecr>/assembly-dev-api:latest .
   docker build --platform linux/arm64 -f web/Dockerfile -t <ecr>/assembly-dev-web:$SHA -t <ecr>/assembly-dev-web:latest .
   docker push <ecr>/assembly-dev-api:$SHA
   docker push <ecr>/assembly-dev-api:latest
   docker push <ecr>/assembly-dev-web:$SHA
   docker push <ecr>/assembly-dev-web:latest
   ```

2. **Deploy 6-stack CDK**:
   ```bash
   cd infra-cdk
   npx cdk deploy --all --require-approval never
   ```

3. **Load data into Neptune + OpenSearch** (one-shot ECS task):
   ```bash
   aws ecs run-task \
     --cluster assembly-dev-cluster \
     --task-definition assembly-dev-api \
     --launch-type FARGATE \
     --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","data.load","--neptune","--opensearch","--from-s3"]}]}'
   ```

4. **Force ECS rollout** to pick up new image:
   ```bash
   aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-api --force-new-deployment
   aws ecs update-service --cluster assembly-dev-cluster --service assembly-dev-web --force-new-deployment
   ```

5. **Smoke test** the deployment:
   ```bash
   DOMAIN=$(aws cloudformation describe-stacks --stack-name assembly-edge \
     --query 'Stacks[0].Outputs[?OutputKey==`PublicDomain`].OutputValue' --output text)
   curl -fsS https://$DOMAIN/healthz
   curl -fsS https://$DOMAIN/api/healthz
   curl -fsS -X POST https://$DOMAIN/api/search \
     -H 'content-type: application/json' \
     -H 'X-Persona-Id: editorial' \
     -d '{"q":"AI 입법","top_k":5}' | jq '.hits | length'
   ```

Report each step's outcome. If anything fails, surface the exact error and propose a fix.

**Important**: `cdk destroy` is in the deny list. Tear-down is intentionally manual to prevent accidental data loss.
