# ADR 0004 — Political Neutrality Guardrails (multi-layer)

- Status: Accepted
- Date: 2026-05-13

## Context

본 PoC는 한국 정치(국회)를 데이터로 다룬다. CxO 대상 라이브 시연 중 ① 특정 정당 비방 출력, ② 정치인 모욕, ③ 정파 편향 어휘, ④ 정치 민감 콘텐츠에 부적절한 광고 노출이 발생하면 데모 자체가 실패할 뿐 아니라 회사·언론사 평판에도 손상을 줄 수 있다.

gcc는 화학·고객 분석 도메인이라 Bedrock Guardrails 적용이 형식적 안전장치였지만, assembly에서는 **데모 가능성의 전제 조건**이다.

## Decision

다층 방어(Defense in Depth) 6개 레이어 적용:

### Layer 1 — Bedrock Guardrails (시스템)

- 별도 Guardrail 리소스 생성 (`assembly-political-neutrality-guardrail`).
- 차단 토픽: 정당명 + 비방 표현 조합, 정치인 모욕, 종교·성별·지역 차별.
- 변환 규칙: 단정적 가치 판단 → 출처 인용 + 양측 의견 병기 형식.
- 입력 스크럽 + 출력 필터 양방향 적용.
- 시나리오 B·C·I·K 모두 자동 적용 (`api/services/guardrails.py:check`).

### Layer 2 — System Prompt Suffix (LLM)

모든 LLM 호출에 다음 suffix 자동 첨부:

```
당신은 한국 언론사의 사실 분석 도구입니다. 다음 원칙을 반드시 지키세요:
1. 특정 정당·정치인에 대한 단정적 가치 판단을 하지 마세요.
2. 항상 데이터 출처와 통계 근거를 함께 제시하세요.
3. 비판적 의견과 옹호 의견이 있는 사안은 양쪽 모두 짧게 언급하세요.
4. 정치인의 사적 영역(가족·개인 신념)에 대한 추론을 하지 마세요.
```

`api/services/persona.py:NEUTRALITY_GUARD_SUFFIX` 상수로 단일 진실원 유지.

### Layer 3 — political_balance_score 메트릭

응답마다 자동 계산되어 `final` SSE event에 첨부:

```python
def political_balance_score(response_text: str, bills_referenced: list[str]) -> float:
    """
    1. 정당별 언급 빈도의 표준편차 (작을수록 균형)
    2. 정당별 긍정·부정 표현 분포 (작을수록 균형)
    3. 출처 인용 유무 (있을수록 점수 상승)
    Returns score ∈ [0.0, 1.0], <0.8이면 UI 노란색 경고
    """
```

CloudWatch 메트릭으로 집계, 평균 < 0.8이면 알람.

### Layer 4 — Class-level field prohibition

다음 필드는 **절대 생성·저장·읽기 금지**:
- `Reader.political_leaning`
- `Person.political_loyalty_score`
- `Article.bias_label`
- `Statement.party_attack_intent`
- 기타 정치 성향 추론 결과 일반

security-auditor agent가 모든 PR에서 자동 검증.

### Layer 5 — 시연 질문 사전 검증

- `scripts/eval_wow_queries.py`에 사전 검증된 5개 핵심 + 30개 보조 질문 등록.
- 라이브 시연은 이 풀에서만 선택.
- 청중 자유 입력 시: ① guardrails 우선 적용 ② 백업 모드 옵션 ③ 발표자 단축키로 다음 슬라이드 전환.
- 모든 시연 시나리오는 **백업 영상 사전 녹화** (`docs/demo-recordings/`, gitignored - 별도 KMS S3 보관).

### Layer 6 — Ad Match governance (시나리오 L)

광고 매칭 Agent 모드는 다음 콘텐츠에 광고 노출 자동 생략:
- 비극·재난·인명 피해 (예: 자연재해 사망자 기사)
- 특정 정치인 비위·의혹 (예: 검찰 수사 진행 중)
- 미성년·범죄 피해자
- 광고주 명시 회피 토픽과 충돌

판단 결과는 `AdMatchDecision` 노드 reasoning trace로 저장. 운영 콘솔에서 사후 감사 가능.

## Consequences

**Positive**:
- 라이브 시연 중 부적절 출력 차단 다층화. 한 레이어가 뚫려도 나머지가 잡음.
- `political_balance_score` 메트릭이 청중에게 "AI가 자기 출력을 모니터링한다"는 직관적 메시지 전달.
- 시나리오 L의 Agent 광고 거절 trace가 데모의 핵심 차별점으로 살아남.

**Negative / 비용**:
- Bedrock Guardrails 호출이 LLM 응답 latency를 약 200–500ms 증가시킴.
- system prompt suffix가 모든 응답에 자동 첨부되므로 응답이 조금 더 보수적(중립적)으로 나옴 — 데모 임팩트 일부 감소.
- security-auditor agent 검토 빈도 증가 → PR 리뷰 시간 +5분/PR 추정.
- 백업 영상 사전 녹화 부담 (시연 시나리오 14개 × 6 페르소나 = 84 영상).

**새 제약**:
- 모든 LLM 호출 코드는 `services/bedrock.py:invoke()` 단일 진입점 경유. 직접 boto3 호출 금지.
- `services/guardrails.py:check()` 미호출 응답은 CI에서 차단(테스트로 검증).
- 새 시나리오 추가 시 Layer 2(prompt) + Layer 3(score) + Layer 5(eval) 3곳에 등록.

## Alternatives Considered

1. **Guardrails 한 레이어만** — 가장 단순. 그러나 라이브 시연 실패 시 복구 불가. 정치 도메인에 부적절. **기각**.
2. **출력만 필터링 (입력은 무방어)** — 시스템 프롬프트 우회 공격에 취약. **기각**.
3. **Reader/Person 모델에 political_leaning 필드 두되 노출만 금지** — 데이터 자체 위험. PIPA·언론 윤리 위배 가능. **기각**.
4. **사전 검증 질문 풀 없이 자유 입력** — 라이브 시연 사고 위험 큼. CxO 청중 환경 부적절. **기각**.

## References

- spec §6 정치 중립성 가드레일 (Critical)
- SECURITY.md §2 정치 중립성 가드레일
- SECURITY.md §4 광고 매칭 윤리
- `api/services/guardrails.py` (예정)
- `api/services/persona.py:NEUTRALITY_GUARD_SUFFIX` (예정)
- AWS Bedrock Guardrails: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html
