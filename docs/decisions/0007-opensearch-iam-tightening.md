# ADR 0007 — OpenSearch Serverless IAM Tightening (Phase 5 Polish)

- Status: Accepted (action plan)
- Date: 2026-05-15
- Related: [[ADR-0006]] 공유 VPC, ADR-0004 ADR-0001 IAM least privilege

## Context

dev 배포 단계에서 OpenSearch Serverless Collection의 *data access policy*는 다음 Principal로 운영 중:

```json
{
  "Principal": [
    "arn:aws:iam::061525506239:root",
    "arn:aws:iam::061525506239:role/ontology-assembly-dev-compute-ApiTaskRole...",
    "arn:aws:iam::061525506239:role/ontology-assembly-dev-compute-AdMatcherRole..."
  ]
}
```

`account:root`는 *현재 계정의 IAM root user* 만 의미하지만, dev 환경에서 디버깅·관리 편의를 위해 의도적으로 포함. Kiro 리뷰 게이트 (2026-05-14)에서 "production에선 너무 광범위" 지적.

## Constraints (해결책에 영향)

1. **OpenSearch Serverless `Principal`은 와일드카드 미지원** (확인됨, 2026-05-14 deploy 시도 시 InvalidRequest):
   - `arn:aws:iam::ACCOUNT:role/prefix-*` 패턴 미허용
   - 명시적 IAM ARN만 받음
2. **CDK cyclic dependency**: data stack이 compute stack의 task role을 직접 import하면 양 stack 간 circular (data → compute → data via SG).
3. **Production transition** 시 `account:root` 유지 불가 — audit·compliance 위반.

## Decision

### Phase 1 — 현재 (dev) 상태 유지

- `account:root` + 2 task role (Api, AdMatcher) Principal 유지
- 코드 주석에 dev-only 명시 (`data/stack.ts:96` 인접)

### Phase 2 — Production transition 시 (Phase 5 polish)

**옵션 A (권장): IamStack 분리**
- 신규 stack `infra-cdk/lib/iam-stack.ts` 도입
- ECS task role, Lambda role, Bedrock KB role 등 *모든 service role* 을 한 곳에서 생성
- data stack은 iam stack의 role ARN을 props로 받아 access policy Principal에 정확히 명시
- 의존성: iam → data, iam → compute (모두 단방향, 순환 없음)

**옵션 B (대안): cross-stack export → boto3 post-deploy patch**
- CDK는 access policy를 `account:root`로 두고
- compute stack export로 task role ARN을 us-east-1 SSM 또는 ap-northeast-2 SSM에 저장
- `scripts/tighten-aoss-policy.py` post-deploy 단계로 boto3 호출
- 비-IaC drift 생성 (단점). repeatable script로 mitigate.

옵션 A 채택 권장 — 단방향 의존성·IaC 단일 진실원·CDK 표준 패턴.

### Phase 3 — 운영 검증

- Production 배포 후 `account:root` 제거 확인
- AWS Config rule: `opensearch-serverless-no-root-principal` (Custom rule 작성)
- Trail audit: `aoss:CreateAccessPolicy` / `UpdateAccessPolicy` 모두 CloudTrail 기록

## Consequences

### Positive
- Production에서 최소 권한 원칙 준수
- Audit·compliance 통과 가능
- IAM 변경 시 단일 stack 책임 (IamStack)

### Negative / Trade-offs
- **dev 디버깅 편의 감소**: 로컬에서 OpenSearch query 시 별도 admin role assume 필요
- IamStack 추가로 CDK app dependency tree 1단계 증가
- iam-stack synth 시간 +~30s

### Neutral
- Phase 2 마이그레이션 시 *기존* access policy update는 zero-downtime (data plane 영향 없음)

## Implementation Checklist (Phase 5 polish)

- [ ] `infra-cdk/lib/iam-stack.ts` 신규 - ECS·Lambda role 이전
- [ ] `compute-stack.ts` task role import (cross-stack ref)
- [ ] `data-stack.ts` OpenSearch access policy Principal 명시
- [ ] `tests/stacks.test.ts` snapshot 갱신
- [ ] AWS Config custom rule: `assembly-aoss-no-root`
- [ ] CloudTrail data event - `opensearchserverless.amazonaws.com` 활성화
- [ ] Migration runbook: `docs/runbooks/03-aoss-iam-tightening.md`

## References

- [AWS Docs - Data access policies](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-data-access.html)
- [ADR-0006] 공유 VPC import (CDK cross-stack reference 패턴 참고)
- [ADR-0001] gcc 차용 + IAM least privilege 원칙
- Kiro review gate (2026-05-14, account:root 지적)
