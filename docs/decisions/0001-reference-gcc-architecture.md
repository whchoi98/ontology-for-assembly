# ADR 0001 — Adopt ontology-for-gcc as the reference architecture (full reuse)

- Status: Accepted
- Date: 2026-05-13

## Context

언론사 대상 Agentic 온톨로지 PoC를 처음부터 빌드할지, 검증된 패턴을 차용할지 결정해야 한다. 사용자(메인테이너)는 동일 청사진으로 `ontology-for-gcc` (GS칼텍스 고객분석), `ontology-for-retail` (리테일), `ontology-for-mfg`/`mfc` (제조) 시리즈를 이미 구축한 경험이 있다. 사용자가 명시적으로 "https://github.com/whchoi98/ontology-for-gcc를 최대한 참조"하라고 지시했다.

## Decision

`ontology-for-gcc` (plan1-foundation 브랜치, 2026-05-09 1.0.0 릴리스 상태) 를 **아키텍처 참조 원본**으로 채택한다. 다음 4가지를 거의 그대로 차용:

1. **디렉토리 구조** — `api/`, `web/`, `infra-cdk/`, `data/`, `ontology/`, `tests/`, `docs/`, `scripts/`, `.claude/`, `.harness-eval/`, `.github/workflows/` 100% 동일.
2. **6-stack CDK** — network, data, compute, ai, edge, observability. assembly 도메인에 맞춰 이름 prefix만 변경.
3. **기술 스택** — Python 3.12 FastAPI + Next.js 14 + AWS CDK TypeScript + Bedrock Sonnet 4.6 + Cohere embed-v4 / rerank-v3 + AgentCore + Neptune openCypher + OpenSearch Serverless + ECS Fargate ARM64 + CloudFront + Cognito + Lambda@Edge.
4. **하니스(.claude/) + 컨벤션** — scrub-secrets / changelog-reminder hooks, code-reviewer / security-auditor agents, wow-query-eval / cypher-conventions skills, deploy / review / test-all commands, settings.json deny list 60+ entries.

다음만 도메인에 맞게 교체:
- **도메인 클래스** — 25 GSC 고객분석 → 25+ 국회/언론 (의원·의안·표결·발언·기사·독자·광고·...).
- **페르소나** — gcc의 5 부서(GSC 임직원만) → 6 페르소나(내부 3 + 대고객 3). ADR-0002 참조.
- **데이터 소스** — GSC raw_data → 국회 OpenAPI + 합성 + 외부 시그널.
- **시나리오 의미** — 14개 시나리오 코드(A–N)는 유지, 의미만 도메인 재해석.

## Consequences

**Positive**:
- gcc에서 검증된 6-stack CDK·CI 4-job·테스트 패턴·하니스를 즉시 재활용. 첫 배포까지 약 1주 단축.
- 향후 디버깅·운영 시 gcc·retail·mfg와 동일 패턴이므로 컨텍스트 스위칭 최소.
- harness-eval rubric 12-dimension을 그대로 적용 가능.

**Negative / 비용**:
- 언론·정치 도메인 특유 요구(정치 중립성 가드레일, 광고 매칭 거버넌스, B2C 익명 독자)는 추가 작업 필요. ADR-0003·0004로 분리.
- gcc의 일부 디자인 결정(retail VPC import 등)은 assembly에 부적합하므로 의식적으로 분리(독립 VPC 채택).

**새 제약**:
- 모든 새 라우터·서비스·페이지는 gcc 패턴을 우선 참조. 새 발명 전에 `/tmp/ontology-for-gcc/`를 보고 같은 구조 가능 여부 확인.
- CLAUDE.md의 "Auto-Sync Rules" 9곳 동시 수정 체크리스트를 gcc에서 그대로 가져옴.

## Alternatives Considered

1. **Greenfield 새 빌드** — 가장 자유롭지만 시간·리스크 큼. gcc의 검증된 컨벤션을 잃음. **기각**.
2. **`ontology-for-retail` 참조** — gcc보다 단순하나 시나리오 8개, 페르소나 단순. 데모 풍부함 부족. **기각**.
3. **`ontology-for-mfg` 참조** — 22 클래스, 12 시나리오. 중간 복잡도이나 gcc가 14 시나리오 + 25 클래스로 더 풍부. **기각**.
4. **gcc + retail 하이브리드** — VPC 공유 등 매력적이나 assembly는 정치 도메인 격리가 더 중요. **기각**.

## References

- 차용 원본: https://github.com/whchoi98/ontology-for-gcc (plan1-foundation)
- 차용 분석 메모리: `~/.claude/projects/-home-ec2-user-my-project-ontology-for-assembly/memory/reference_gcc_architecture.md`
- spec §1.1 인프라 토폴로지
- ADR-0002 (6-페르소나 설계 — gcc 5 부서와의 차이)
- ADR-0003 (대고객 서비스 확장)
- ADR-0004 (정치 중립성 가드레일)
