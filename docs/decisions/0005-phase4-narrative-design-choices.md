# ADR 0005 — Phase 4 Narrative Design Choices for ADR-0004 Enforcement

- Status: Accepted
- Date: 2026-05-14

## Context

[[ADR-0004]]은 4-layer 가드레일(Bedrock Guardrails + System Prompt Suffix + balance score + Forbidden Fields)을 정의했다. Phase 4에서 11개 시나리오(C·D·E·F·G·H·I·J·K·M·N)를 추가로 구현하면서, *가드레일을 어떻게 시나리오 내부에 노출할 것인가*가 반복되는 디자인 문제로 등장했다.

전통적 접근은 "가드레일 = 차단·실패"이지만, 본 PoC의 demo 가치 명제(*"3-단계 진화 + AI 거버넌스를 보이게 한다"*)에 따르면 **가드레일을 능동적 product feature**로 노출하는 것이 demo의 wow 모먼트를 만든다.

본 ADR은 Phase 4 시나리오 11개에 일관 적용된 5가지 narrative 디자인 패턴을 문서화한다. 향후 유사 정치·민감 도메인 PoC에서 재활용 가능한 reference.

## Decision

### Pattern 1 — Visible Governance (시나리오 I)

**문제**: 가드레일 4-layer가 코드 내부에만 존재하면 그 가치가 인지되지 않는다.

**선택**: 4-layer 자체를 *시각화 가능한 라우터*로 노출.

- `GET /api/neutrality/architecture` → 4-layer 메타 (이름·위치·동작 설명·활성 여부)
- `GET /api/neutrality/samples` → 4 등급 데모 텍스트 (낮음 0.3 → 우수 0.97)
- `POST /api/neutrality/score` → 실시간 채점 (라이브 입력)
- `GET /api/neutrality/recent` → ops_metrics trace + 누적 카운터

UI(`web/app/neutrality/page.tsx`)는 4-layer를 다이어그램 + 라이브 채점 폼 + 4 등급 카드로 시각화. 가드레일이 hidden 안전장치가 아닌 *demonstrable product feature*가 된다.

**효과**: 시연 시 청중이 가드레일의 작동을 직접 볼 수 있고, 미디어·B2B 고객에게 "AI 거버넌스 투명성"을 직접 보여줄 수 있는 입증 자료.

### Pattern 2 — Cross-party Clustering Inversion (시나리오 E·F)

**문제**: 의원 클러스터링의 가장 자연스러운 axis는 정당이지만, ADR-0004는 정당 기반 grouping을 금지.

**선택**: *토픽 활동 vector*만으로 cluster 구성. 결과적으로 모든 cluster가 *cross-party*가 됨.

```
cluster_ai_data:   더불어민주당 4명 + 국민의힘 2명 + 개혁신당 1명 (3 정당)
cluster_environment: 더불어민주당 2명 + 국민의힘 1명 + 정의당 1명 + 무소속 1명 (4 정당)
```

`cross_party_share` 필드로 정파 분산도 노출. 테스트로 모든 cluster가 2+ 정당 멤버를 가지도록 강제(`test_all_clusters_have_2plus_parties`). 시나리오 F(룩어라이크)는 *same cluster + 다른 정당* 후보에 `cross_party_signal=True` 태그 — cross-party 협력 잠재력 narrative.

**효과**: ADR-0004 제약이 demo 가치(*"기자가 cross-party 협력 의제를 발굴하는 도구"*)로 전환. "정당으로 묶지 않는다"는 제약이 "정파 가로지르는 협력 그룹 발굴"이라는 능동적 산출물로 inversion.

### Pattern 3 — Narrative Patterns over Statistics (시나리오 J)

**문제**: 외부 신호 × 입법 활동의 상관 분석은 추상 correlation 수치를 만들기 쉽지만, 기자가 한 줄로 인용할 수 없다.

**선택**: 3개 구체적 *narrative 패턴*만 노출.

- `signal_leads` — 외부 시그널이 입법보다 앞섬 (의제 → 입법 형성)
- `legislation_leads` — 입법이 시그널보다 앞섬 (입법 → 공론화)
- `decoupled` — 양자 무관 (시그널 강해도 입법 없음)

각 패턴은 단일 토픽 시드(AI / 환경 / 문화)로 12주 dual-time-series + lag_weeks + correlation_hint + 1문단 narrative + sources 첨부. correlation 수치는 정성 라벨로만 노출, *구체적 스토리가 demo의 표면*.

**효과**: 기자가 "AI 토픽은 외부 시그널이 입법보다 5주 앞섰다"라고 한 줄 인용. 추상 Pearson 0.78이 아닌 *narrative-first* 패턴.

### Pattern 4 — Density Labels without Color Ideology (시나리오 H)

**문제**: 지역구 지도 시각화에서 가장 흔한 색 매핑은 정당 색(파랑·빨강)이지만, ADR-0004는 정파 색 사용 금지.

**선택**: 정성 4-tier 라벨(*"매우 높음·높음·보통·낮음"*)만 사용. 색 스케일은 단조(blue gradient, density 비례)만. 17 시도 cell에 정당 카운트는 표시하되 *지도 색은 정파와 무관*.

테스트로 강제(`test_no_ideology_color_terms_in_density_labels`).

**효과**: 시각화의 *정보 축*(intensity vs. ideology)을 분리. 지도가 "정치 지도"가 아닌 *"의원 분포 지도"*가 됨 — ADR-0004의 letter는 지키되 정보 가치는 보존.

### Pattern 5 — Issue × Activity (NOT Issue × Party) (시나리오 N)

**문제**: 이슈×입법 매트릭스의 가장 자연스러운 3D 분해는 *이슈 × 정당 × 활동*이지만, ADR-0004는 이를 금지.

**선택**: 2D로 축약 — *이슈 × 활동*(8 × 4 매트릭스). 정당 분포는 별도 시나리오로 격리:

- 시나리오 D(페르소나 매칭): 콘텐츠 → 페르소나 affinity
- 시나리오 E(클러스터링): 의원 → 활동 vector cluster
- 시나리오 K(이상치): 표결 패턴 deviation

테스트로 매트릭스 cell에 정당 필드 미존재 강제(`test_no_party_count_in_matrix`).

**효과**: 매트릭스의 *axis 선택*이 ADR-0004 enforcement. 표면적 데이터 분해는 단순해지고, 정당 정보가 필요한 분석은 separation of concerns로 다른 시나리오에 격리.

## Cross-cutting Test Patterns

모든 11 Phase 4 시나리오는 4종 ADR-0004 정합성 테스트를 통과:

1. **Seed 텍스트 PARTY_ATTACK 미포함**: `guardrails.check_output(seed).passed`
2. **이념 라벨 substring 검사**: `"진보"·"보수"·"좌파"·"우파"·"극좌"·"극우" not in text`
3. **인과 단정 표현 금지**: `"때문이다"·"원인이다"·"확실히"·"반드시"·"절대로" not in narrative`
4. **출처 명시**: `"(출처: ...)" in narrative or len(sources) > 0`

이 4종 테스트는 [[ADR-0004]]의 코드 단 자동 차단 마지막 방벽. 11 시나리오 × 4 종 = ~44 테스트 추가됨 (총 pytest 975 통과).

## Consequences

### Positive

- 가드레일이 *demo의 weakness*에서 *demo의 strength*로 전환 (Pattern 1).
- ADR-0004 제약이 narrative 가치를 만드는 *능동적 디자인 도구*가 됨 (Pattern 2·3·5).
- 정보 시각화의 정치 중립성이 *시각적·구조적*으로 보장 (Pattern 4·5).
- 11 시나리오 모두 동일 패턴 적용 — 디자인 일관성이 산출물 신뢰성을 보강.

### Negative / Trade-offs

- 매트릭스·클러스터링·시각화의 *표면적 단순화* — 일부 분석 가치 손실 (정당별 stats 등). 보강은 별도 시나리오 분리(Pattern 5)로 mitigate.
- "보이는 거버넌스"는 시연자가 *적극적으로 가리키지 않으면* 청중이 인지하지 못할 수 있음. GuidedTour의 시연자 step에 명시 포함 필요.
- narrative-first 접근은 *데이터 분포가 패턴에 맞게 시드*되어야 함 — 합성 PoC는 통제 가능하지만 production에서는 통계 신뢰성과 narrative 가독성의 균형이 새 디자인 문제.

### Neutral / 미해결

- LLM이 결정적 시드 자리에서 동적 생성하게 되면 (production transition) 패턴 라벨(`signal_leads` 등)의 LLM 추출 정합성 검증이 새 과제.
- ADR-0005의 디자인 패턴이 정치 외 민감 도메인(의료·법무·세법)에서도 유효한지는 별도 사례 연구 필요.

## References

- [[ADR-0001]] gcc 아키텍처 차용
- [[ADR-0002]] 6 페르소나 설계
- [[ADR-0003]] 대고객 확장 인증
- [[ADR-0004]] 정치 중립성 가드레일 (4-layer)
- Phase 4 메모: `~/.claude/projects/-home-ec2-user-my-project-ontology-for-assembly/memory/feedback_demo_narrative_choices.md`
- spec §3.1 시나리오 정의: `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md`
