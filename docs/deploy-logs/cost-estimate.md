# 비용 추정 — Dev 환경 + 시연용 (2026-05-14)

`ontology-for-assembly` PoC의 dev 환경(`ontology-assembly-dev-*` 6 stack) AWS 월 비용 추정. us-east-1 기준, 30-60분 시연을 주 1-2회 가정.

이 문서는 *cdk synth*로 추출한 정의된 리소스를 기준으로 한 추정치이며, 실 청구는 사용 패턴에 따라 ±20% 변동 가능. 비용 모니터링은 *AWS Cost Explorer + 태그 `Project=ontology-assembly`*로 추적.

## 요약

| 카테고리 | 월 추정 | 비고 |
|---------|--------|------|
| Compute (Fargate ARM64 × 2 service) | $67 | Graviton 20% off, 24/7 항상-on |
| 네트워크 (VPC + 1 NAT + ALB) | $55 | NAT Gateway가 절반 (~$32) |
| **OpenSearch Serverless** | **$350** | 최소 OCU 0.5 × 2 (indexing + search). PoC의 가장 큰 항목 |
| Neptune (db.t3.medium 추정) | $105 | 24/7 가동. 정지 가능 시 절감 |
| Bedrock invocations (시연용) | $5-10 | Sonnet 4.6 + Cohere embed-v4 + rerank-v3 |
| CloudFront + Lambda@Edge | $5 | PoC 저트래픽 |
| Cognito + DynamoDB + S3 + KMS | $5 | free tier 대부분 |
| CloudWatch (Logs + Metrics + Alarms) | $5 | log retention 30일 가정 |
| **합계 (dev 항상-on)** | **~$600** | |

**핵심 절감 포인트**:
1. **OpenSearch Serverless가 60% 차지** — production 전 OCU 자동 스케일링 한계를 확인 후 dev에선 일반 OpenSearch (t3.small.search)로 대체하면 ~$70/월. 절감액 ~$280.
2. **Neptune은 일과 시간만 가동** — 야간·주말 정지로 약 60% 절감 가능 (~$40/월).
3. **NAT Gateway**는 인터넷-bound 트래픽이 적으면 *Instance NAT*로 대체 가능 (월 $32 → ~$5).

위 3 항목 모두 적용 시 dev 비용 **~$260/월**로 절감 가능.

## Compute (Fargate ARM64)

`infra-cdk/lib/compute-stack.ts`에서 정의된 두 서비스:

| 서비스 | CPU (vCPU) | Memory (MiB) | 복제본 | 월 비용 |
|--------|-----------|--------------|--------|---------|
| `assembly-dev-api` | 1024 (1.0) | 2048 | 2 | ~$45 |
| `assembly-dev-web` | 512 (0.5) | 1024 | 2 | ~$22 |

- Fargate ARM64 (Graviton) 단가: vCPU $0.0316/h, 메모리 $0.00347/GB-h (us-east-1).
- 계산: api = 1 vCPU × $0.0316 + 2 GiB × $0.00347 = $0.0385/h × 24 × 30 × 2 replicas = **$55.4/월** (단일) → 실제는 시간당 단가에 양 task 합산해서 산정해야 함.
- 정확 식 (per replica per hour): `0.0316 × cpu_vcpu + 0.00347 × mem_gb`.
  - api: $0.0316 × 1 + $0.00347 × 2 = $0.0386/h × 24 × 30 × 2 = **$55.6/월**
  - web: $0.0316 × 0.5 + $0.00347 × 1 = $0.0193/h × 24 × 30 × 2 = **$27.8/월**
  - 소계: **$83/월** (재추정)

ARM64 Graviton 20% discount 미적용 — Fargate ARM64는 동일 단가 (Graviton EC2와 다름). 실제 ~$83 예상.

**절감 옵션**:
- 비-시연 시간(야간·주말)에 desiredCount=0 — DesiredCount Scheduled Scaling 적용 시 ~50% 절감.
- web service는 sparse load — CloudFront 캐싱 충분하면 desiredCount=1로 ~25% 절감.

## 네트워크 (VPC + NAT + ALB)

`network-stack.ts`:
- VPC 10.30.0.0/16, 3 AZ public + private + isolated subnets.
- NAT Gateway × 1 (`natGateways: 1`).
- ALB × 1 (compute stack).

| 항목 | 단가 | 추정 |
|------|------|------|
| NAT Gateway | $0.045/h + $0.045/GB | ~$32/월 (24/7) + 트래픽 |
| ALB | $0.0225/h + $0.008/LCU | ~$16-23/월 |
| Data Transfer (CloudFront → ALB) | $0.02/GB | PoC ~$2/월 |

소계: **~$50/월**.

**절감**: NAT Gateway → t3.nano Instance NAT로 변경 시 ~$5/월. 단 운영 부담 증가.

## OpenSearch Serverless

`data-stack.ts` — 가장 큰 비용 항목.

- 최소 OCU: indexing 0.5 + search 0.5 = **1 OCU 합산**, 시간당 $0.24/OCU = $172/월 per OCU.
- 보장된 baseline: $172 × 2 OCU = **~$344/월** (idle 시에도 청구).
- 실제 호출 시 자동 스케일 — 시연 트래픽은 baseline 내에 수용.

**절감 옵션**:
1. dev는 일반 OpenSearch t3.small.search (~$25/월) + Nori 플러그인 수동 설치. Production은 Serverless 유지.
2. 또는 1 OCU(indexing only, search inline)로 축소 — $172/월.

PoC dev는 **현행 유지 (~$344)** 권장: spec §4의 hybrid BM25 + KNN + RRF 시연이 핵심 demo 가치이므로 trade-off 가치 있음.

## Neptune

`data-stack.ts` — `db.t3.medium` 가정.

- 단가: $0.144/h × 24 × 30 = **~$104/월**.
- 스토리지: 10 GB 시드 가정, $0.10/GB-월 → ~$1/월.

**절감 옵션**:
- AWS Lambda Scheduled로 야간·주말 정지 — `aws neptune stop-db-cluster`. ~60% 절감 ($40/월).
- Provisioned → Neptune Serverless (NCU 기반)로 변경. 최소 1 NCU($0.1764/h × baseline) — production scale 미지수.
- PoC만이면 정지 스케줄 권장.

## Bedrock invocations (시연용)

`api/services/bedrock.py` + `agent.py` 호출.

| 모델 | 단가 | 시연 예상 |
|------|------|----------|
| Sonnet 4.6 | $3/M input, $15/M output | 100 호출 × 2K input + 1K output = 0.2M in + 0.1M out = $0.60 + $1.50 = **$2.10/시연** |
| Cohere embed-v4 | $0.10/M tokens | 1K embed × 200 tokens = 0.2M = $0.02 |
| Cohere rerank-v3 | $1.00/M search units | 1K rerank = 1 SU = $1.00 |

월 4회 시연 가정 시 ~$13. 평소 dev 사용 + AgentCore Memory + Code Interpreter 호출 합산 **~$10-15/월**.

## CloudFront + Lambda@Edge

`edge-stack.ts`:
- CloudFront: 첫 1TB free, PoC 트래픽 < 10GB → **$0**.
- 요청 비용: 첫 10M free → **$0**.
- Lambda@Edge: 첫 1M free + $0.60/M, PoC 호출 1K = **$0**.

소계 ~**$2/월** (CloudWatch + 메타 비용).

## Cognito + DynamoDB + S3 + KMS

- Cognito: free tier 50K MAU 충분.
- DynamoDB (B2B API keys, on-demand): < $1.
- S3 (data S3, KMS 암호화): ~$2 (raw_data 10GB).
- KMS: $1/key/월 × 2 keys = $2.
- 소계 **~$5/월**.

## CloudWatch + Observability

`observability-stack.ts`:
- Logs (api + web + Lambda): 30일 retention, ~3GB/월 = $1.50.
- Metrics: 표준 메트릭 free + 커스텀 ~10개 = $3/월.
- Alarms (political_balance + 5xx + Bedrock latency): 5 alarm × $0.10 = $0.50.
- Dashboard: $3/월.
- 소계 **~$8/월**.

## Production 스케일링 추정 (참고)

본 PoC가 production 전환 시 비용 변동 요소 (사용자 1만 명 가정):

| 항목 | 변동 | 비고 |
|------|------|------|
| Fargate (api·web 4-8 replicas each, m6g.large 급 spec) | $83 → **~$500/월** | Auto-scaling 적용 |
| OpenSearch | $344 → **~$1,500/월** | 8-10 OCU scale |
| Neptune | $104 → **~$800/월** | r6g.large + Multi-AZ |
| Bedrock | $15 → **~$2,000/월** | 사용자당 일일 5 호출 가정 |
| CloudFront + ALB 트래픽 | $5 → **~$200/월** | |
| **합계** | **~$5,000/월** | dev 대비 약 8x |

## 비용 모니터링 권장

1. **태그 강제**: 모든 리소스에 `Project=ontology-assembly` + `Env=dev|prod`. CDK는 `cdk.tags.setTag()`로 자동.
2. **Budgets 알람**: 월 $700 임계 (dev), $6,000 임계 (production).
3. **Cost Anomaly Detection**: Bedrock 사용량 급증·OpenSearch OCU 스케일 트리거.
4. **운영 콘솔 비용 패널** (Phase 5 polish): `/api/ops/cost-summary` endpoint로 일별 추정 노출 가능 (별도 IAM `ce:GetCostAndUsage` 필요).

## References

- AWS Pricing API: 공식 단가는 시간 경과에 따라 변동. 본 추정치는 2026-05-14 us-east-1 단가 기준.
- spec §5: `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` 인프라 정의.
- CDK 정의: `infra-cdk/lib/*-stack.ts` (cdk synth 출력은 `cdk.out/`).
- 절감 옵션 상세: [[ADR-0001]] gcc 아키텍처 차용 + 본 PoC dev/prod 차별.
