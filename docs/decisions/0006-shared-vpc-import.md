# ADR 0006 — Shared VPC Import (cc-on-bedrock-vpc)

- Status: Accepted
- Date: 2026-05-14
- Supersedes: [[ADR-0001]] D7 (assembly 독립 VPC 결정 부분만)

## Context

[[ADR-0001]] 차용 결정에서 *"gcc는 retail VPC import였지만 assembly는 독립 VPC"*로 명시했었다. 하지만 같은 AWS 계정(061525506239, ap-northeast-2)에서 다음 ontology 프로젝트들이 동시 운영 중이다:

- **ontology-for-gcc** (CloudFormation `ontology-gcc-dev-*`)
- **ontology-for-retail** (`OntologyRetail*`)
- **ontology-for-mfg** (`ontology-mfg-dev-*`)

세 프로젝트 모두 **`vpc-0dfa5610180dfa628` (cc-on-bedrock-vpc, 10.100.0.0/16)** 를 import하여 사용 중. NAT Gateway 2개(AZ-a·AZ-b) 공유, 서브넷 6개(public·private·isolated × 2 AZ) 공유.

assembly가 신규 VPC(10.30.0.0/16)를 생성하면:
- NAT GW 추가 비용: ~$32/월
- 외부 API rate-limit 추적 단편화 (4개 VPC에서 분산 호출)
- 비대칭적 인프라 운영 (gcc·retail·mfg는 공유, assembly만 독립)
- 동일 계정 내 VPC 한도(기본 5개) 압박

assembly가 다른 ontology 프로젝트와 cross-VPC 데이터 참조를 *하지 않는다*는 점에서, VPC 분리의 격리 가치는 0에 가깝다.

## Decision

assembly도 `cc-on-bedrock-vpc`를 **import**하여 사용. 새 VPC 생성 안 함.

### Import 대상 리소스

| 리소스 | ID | CIDR / 위치 |
|--------|-----|------------|
| VPC | `vpc-0dfa5610180dfa628` | 10.100.0.0/16 |
| Public Subnet AZ-a | `subnet-08486a1e618b1991e` | 10.100.0.0/24 (ALB) |
| Public Subnet AZ-b | `subnet-0c161777c4031c320` | 10.100.1.0/24 (ALB) |
| Private Subnet AZ-a | `subnet-07b1e65682847dce9` | 10.100.16.0/20 (ECS Fargate, Lambda) |
| Private Subnet AZ-b | `subnet-095297380cd45e1eb` | 10.100.32.0/20 (ECS Fargate, Lambda) |
| Isolated Subnet AZ-a | `subnet-022000a208af56aae` | 10.100.48.0/23 (Neptune) |
| Isolated Subnet AZ-b | `subnet-01b8fb3c462210113` | 10.100.50.0/23 (Neptune) |
| NAT Gateway AZ-a | `nat-00b8a70dc184a4d0c` | Public AZ-a 내 |
| NAT Gateway AZ-b | `nat-08379e076e2e6e234` | Public AZ-b 내 |

### Assembly 전용 신규 리소스 (격리)

| 리소스 | 이름 |
|--------|------|
| Security Group (ALB) | `assembly-alb-sg` |
| Security Group (ECS app) | `assembly-app-sg` |
| Security Group (Neptune) | `assembly-neptune-sg` |
| Security Group (OpenSearch) | `assembly-os-sg` |
| Security Group (Lambda) | `assembly-lambda-sg` |
| 모든 application 리소스 (ECS, Lambda, Neptune, OS Serverless, DynamoDB) | `assembly-${env}-*` |

### CDK 변경

`infra-cdk/lib/network-stack.ts`:
- `new ec2.Vpc()` → `ec2.Vpc.fromVpcAttributes()`로 변경
- 하드코딩된 subnet ID + AZ + CIDR 명시 (재현 가능성·감사 가능성)
- VPC 자체는 다른 프로젝트가 관리 → assembly는 *consumer* role

## Consequences

### Positive

- **NAT GW 공유로 ~$32/월 비용 절감**.
- 4개 ontology 프로젝트가 동일 VPC 운영 패턴 — 인프라 일관성 ↑.
- VPC 한도(5개) 압박 해소.
- 외부 API rate-limit 추적·캐싱이 단일 NAT GW 단위로 단순화.

### Negative / Trade-offs

- **assembly가 다른 프로젝트의 VPC 변경에 영향** — 다른 프로젝트가 subnet을 수정하면 assembly도 영향. mitigation: subnet ID를 코드에 하드코딩(`network-stack.ts`) + ADR-0006 검토 의무.
- **Cross-stack output 의존성 없음** — assembly가 다른 stack의 export를 참조하지 않으므로 cyclic dependency 위험 0. 단 다른 프로젝트가 VPC 자체를 delete하면 assembly 배포 실패.
- **subnet ID 코드 하드코딩** — VPC 마이그레이션 시 코드 수정 필요. 변경 시 [[ADR-0006]] 갱신.

### Neutral / 미해결

- 다른 ontology 프로젝트의 Security Group과 cross-SG 트래픽 허용 여부는 *별개 결정* — 기본은 격리(현재 ingress rule은 assembly SG 간만).
- VPC 자체의 ownership·관리 책임은 [[ADR-0006]] 범위 밖. 별도 IaC 관리(`CcOnBedrock-Network` CDK 스택으로 추정).

## Implementation Notes

`infra-cdk/lib/network-stack.ts`에 다음 상수 export:
```ts
export const SHARED_VPC_ID = 'vpc-0dfa5610180dfa628';
export const SHARED_PUBLIC_SUBNETS = [...];
export const SHARED_PRIVATE_SUBNETS = [...];
export const SHARED_ISOLATED_SUBNETS = [...];
```

다른 stack(`data-stack`, `compute-stack`)은 `network.vpc`를 props로 받으므로 변경 불필요. SG props도 동일하게 props 전달.

## References

- [[ADR-0001]] gcc 아키텍처 차용 (D7 부분 supersede)
- 시각화: AWS Console → VPC `cc-on-bedrock-vpc` → assembly 5 SG가 추가됨을 확인
- 비용 추정: `docs/deploy-logs/cost-estimate.md` (NAT GW 항목)
