/**
 * 14 시나리오 SSOT — 코드/이름/기술 스택/활용 방법.
 *
 * 시나리오 페이지 상단 `<ScenarioHero>`에서 단일 source로 참조. 페이지마다 *기술 1줄*과
 * *활용 방법 3 bullet*을 동시 노출하여 사용자가 진입 직후 *이 시나리오로 무엇을 할 수 있는가*를
 * 즉시 이해.
 *
 * Auto-Sync: 새 시나리오 추가 시 이 파일 + Sidebar + 홈 카드 + GuidedTour 동시 갱신
 * (CLAUDE.md "Auto-Sync Rules" 참조).
 */

export interface ScenarioMeta {
  /** A-N */
  code: string;
  /** 한글 제목 */
  title: string;
  /** 1줄 기술 스택 (백엔드 동작 메커니즘) */
  tech: string;
  /** 활용 방법 3 bullet (이 시나리오로 *무엇을 어떻게* 할 수 있는가) */
  useCases: string[];
  /** 6 페르소나 중 *주력 사용자* (홈 카드 highlight와 동일) */
  primaryPersonas?: string[];
}

export const SCENARIO_META: Record<string, ScenarioMeta> = {
  A: {
    code: 'A',
    title: '의안·의원 의미 검색',
    tech: 'BM25(Nori) + Cohere embed-v4 KNN + RRF + rerank-v3. 페르소나에 따라 top_k 자동 조정.',
    useCases: [
      '자연어 키워드로 의안·의원 동시 검색 (예: "AI 입법", "청년 주거 지원")',
      '검색 결과 카드 → 1-hop 그래프 펼침으로 발의자·공동발의·소관위 직접 탐색',
      '편집국 취재 시작점 · 일반 독자 발견 진입점 · B2B 정책 키워드 모니터링',
    ],
    primaryPersonas: ['editorial', 'general_reader', 'b2b'],
  },
  B: {
    code: 'B',
    title: '데스크 챗봇',
    tech: 'Bedrock Sonnet 4.6 + AgentCore Memory + 10 도구. mode=agentic 단일 stream (phase ordered list).',
    useCases: [
      '자유 대화로 의원·의안·정책 trend 묻기 (예: "AI 입법 발의 많은 의원 3명")',
      '의원 2-3명 비교 또는 의안 변천사 추적 — Tool Use trace 우측 패널에 실시간',
      '후속 질문 click → 다음 단계 자동 dispatch + 답변 MD/PDF 저장',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'paid_subscriber'],
  },
  C: {
    code: 'C',
    title: '기사 인사이트',
    tech: 'Sonnet 4.6 스트리밍 + Code Interpreter 차트 + Bedrock Guardrails. 5-section gcc 패턴.',
    useCases: [
      '합성 기사 60건 풀에서 토픽 선택 → 헤드라인·발견·해석·함의·권고 자동 생성',
      'MD/PDF 다운로드로 데스크 회의 자료·기획 보고서 즉시 활용',
      '정치 균형 점수 자동 첨부 (ADR-0004) · 페르소나별 어조 자동 조정',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'paid_subscriber'],
  },
  D: {
    code: 'D',
    title: '페르소나 매칭',
    tech: '6 페르소나 KPI 가중치 그래프 워크 + reasons LLM 라벨링. Bedrock Sonnet 4.6.',
    useCases: [
      '콘텐츠 → 6 페르소나 적합도 매트릭스 + reasons 시각화',
      '광고·구독 타겟팅 + 콘텐츠 큐레이션 의사결정 정량 근거',
      'B2B 정책 인텔리전스 우선순위 조정 — 같은 기사 6 페르소나 다른 KPI',
    ],
    primaryPersonas: ['ad_sales', 'editorial', 'b2b'],
  },
  E: {
    code: 'E',
    title: '의원 클러스터링',
    tech: 'KMeans + Cohere embed-v4 활동 vector + Sonnet 4.6 cluster 라벨링. ADR-0004 (정당 무관).',
    useCases: [
      '5 thematic cluster 시각화 — 토픽 활동 vector 기반 (정당 색 미사용)',
      'cross-party 협력 그룹 발굴 + 의제별 핵심 의원 식별',
      '시나리오 K 이상치 + 시나리오 F 룩어라이크와 cross-reference',
    ],
    primaryPersonas: ['data_ai', 'editorial', 'b2b'],
  },
  F: {
    code: 'F',
    title: '의원 룩어라이크',
    tech: 'Cohere embed-v4 활동 vector + OpenSearch KNN + cluster proximity + cross-party bonus.',
    useCases: [
      'seed 의원 → top-K 유사 후보 자동 추천 (예: "이 의원 닮은꼴 3명")',
      '정책 동지·법안 공동발의 후보 발굴 + 정파 가로지르는 후보 가중치',
      '시나리오 G 기사 ROI와 결합 → 인물 기획 priority 계산',
    ],
    primaryPersonas: ['data_ai', 'editorial'],
  },
  G: {
    code: 'G',
    title: '기사 ROI 시뮬레이션',
    tech: 'Bayesian 비용·도달·전환 + Code Interpreter 분포 차트 + 6 페르소나 KPI 변환.',
    useCases: [
      '콘텐츠 비용·CTR·전환 Bayesian 추정 + 6 페르소나별 KPI 변환',
      '광고·구독 의사결정 정량 근거 + 후속 취재 priority 산정',
      '분포 차트 PDF 출력 → 매니지먼트·광고주 보고서',
    ],
    primaryPersonas: ['ad_sales', 'editorial', 'b2b'],
  },
  H: {
    code: 'H',
    title: '지역구 지도',
    tech: '17 KOSTAT 시도 GeoJSON + react-simple-maps + d3-geo + 22대 254 지역구 분포.',
    useCases: [
      '17 시도 choropleth + 22대 254 지역구 의원 분포 시각화',
      '지역 격차·활동 stats 분석 + 시도별 의원 drill-down',
      '지자체 협업·지역 기획기사 시작점 + B2C 독자 지역구 발견',
    ],
    primaryPersonas: ['editorial', 'general_reader', 'b2b'],
  },
  I: {
    code: 'I',
    title: '편향·중립성 가드레일',
    tech: 'Bedrock Guardrails 4-layer + political_balance_score 실시간 채점 + 4 등급 시각화.',
    useCases: [
      'ADR-0004 4-layer 가드레일 실시간 동작 시연 (입력·출력 양쪽)',
      'political_balance_score 4 등급 (excellent/good/warning/critical) 자동 분류',
      'AI 거버넌스 신뢰 메시지 — 대고객·B2B 차별화 narrative',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'b2b'],
  },
  J: {
    code: 'J',
    title: '외부 신호 융합',
    tech: '네이버 뉴스 + SNS + 여론조사 cross-source × 입법 활동 12주 시계열 + 3 패턴 자동 라벨.',
    useCases: [
      '뉴스·SNS·여론조사 시그널 × 입법 활동 12주 시계열 비교',
      'signal_leads / legislation_leads / decoupled 3 패턴 자동 라벨',
      '사회 이슈 ↔ 입법 lag time 분석 → 정책 의제 priority',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'b2b'],
  },
  K: {
    code: 'K',
    title: '표결 이상치 탐지',
    tech: 'pandas 윈도 + LLM 패턴 라벨 + deviation_score. PDF 3-page 시그니처 출력.',
    useCases: [
      '당론 이탈·박빙 표결·정파 초월 협력 3 유형 자동 라벨링',
      'deviation_score + AI 패턴 라벨 → 심층 취재·기획기사 단서',
      'PDF 3-page signature 출력 → 즉시 데스크 회의 자료',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'paid_subscriber'],
  },
  L: {
    code: 'L',
    title: '광고 매칭 매트릭스 (3-way)',
    tech: 'keyword / embedding / Agent 3-way 비교 + Ad Matcher Lambda + AdMatchDecision 그래프.',
    useCases: [
      '광고-콘텐츠 매칭 3 방식 (keyword/embedding/Agent) 동시 시연',
      'Agent만 비위 의혹·비극·미성년 피해 콘텐츠에서 자동 광고 거절',
      'AI 거버넌스 시연 핵심 카드 — reasoning trace AdMatchDecision 노드 저장',
    ],
    primaryPersonas: ['ad_sales', 'editorial', 'b2b'],
  },
  M: {
    code: 'M',
    title: '의원 정치 여정 Timeline',
    tech: '발의·공동발의·표결·발언·위원회 활동 시간순 통합. PDF 3-page 시그니처.',
    useCases: [
      '단일 의원 종합 활동 시간순 timeline (발의·표결·발언·위원회)',
      '인물 기획·기조 변화 추적 → PDF 3-page 시그니처 출력',
      '시나리오 F 룩어라이크와 결합 → 의원 비교 narrative 시작점',
    ],
    primaryPersonas: ['editorial', 'paid_subscriber', 'b2b'],
  },
  N: {
    code: 'N',
    title: '이슈 × 입법 상관',
    tech: '8 매크로 이슈 × 4 활동 결합 강도 8×4 heatmap + Top 5 강한 결합 인사이트 LLM 라벨링.',
    useCases: [
      '8 매크로 이슈 × 4 활동 결합 강도 8×4 heatmap 시각화',
      'Top 5 강한 결합 인사이트 자동 추출 + 사회 트렌드 ↔ 입법 상관',
      '정책 의제 priority 의사결정 + B2B 정책 모니터링 우선순위',
    ],
    primaryPersonas: ['data_ai', 'editorial', 'b2b'],
  },
  // ─── 확장 시나리오 (O–S) — 사용자 요청 기반 신규 ────────────────────────
  O: {
    code: 'O',
    title: '인물 관계 분석',
    tech: '두 의원 5 차원 cross-tab (공동발의·표결 일치율·토픽 중첩 Jaccard·timeline overlay·cluster 위치).',
    useCases: [
      '두 의원 선택 → 공동발의 횟수·표결 일치율 정량 비교',
      '토픽 중첩 Jaccard similarity + cluster 위치 비교 → 정책 친밀도',
      'cross-party 협력 narrative 정량 근거 + 후속 인터뷰 hook',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'paid_subscriber'],
  },
  P: {
    code: 'P',
    title: '시민 청원 → 입법 매핑',
    tech: '청원 카테고리 → 발의 의안 임베딩 매칭 + 이행 lifecycle 추적 (발의·심사·통과·시행).',
    useCases: [
      '시민 청원 토픽 → 발의 의안 매칭 (Cohere embed-v4 KNN)',
      '내 청원이 어떻게 입법으로 이어졌는지 lifecycle 추적',
      '카테고리별 청원-입법 매칭률 + 발의자 정량 분석',
    ],
    primaryPersonas: ['general_reader', 'paid_subscriber', 'editorial'],
  },
  Q: {
    code: 'Q',
    title: '위원회 영향력 heatmap',
    tech: '17 상임위 × 5 활동 메트릭 heatmap (발의·심사·통과·발언·출석) + cross-committee 협력 trace.',
    useCases: [
      '17 상임위원회 영향력 score cross-tab heatmap',
      '통과율 top 3 위원회 + cross-committee 협력 의안 발굴',
      '시행령 단계 추적 priority + 후속 취재 priority 산정',
    ],
    primaryPersonas: ['editorial', 'data_ai', 'b2b'],
  },
  R: {
    code: 'R',
    title: '선거 공약 이행 추적',
    tech: '22대 의원 당선 공약 vs 실제 발의 의안 cross-reference + 이행률 정량.',
    useCases: [
      '의원별 당선 공약 → 실제 발의 의안 매칭률',
      '이행률 + 미이행 분야 + 분기별 trend',
      '사회 신뢰·정치 책무 narrative — B2C·편집국 강력',
    ],
    primaryPersonas: ['editorial', 'general_reader', 'paid_subscriber'],
  },
  S: {
    code: 'S',
    title: '분기별 토픽 burst 시계열',
    tech: '8 매크로 이슈 × 13 주차 line chart + burst lag prediction (외부 신호 → 입법 시차 자동 추정).',
    useCases: [
      '8 매크로 이슈 분기별 burst 시각화 (line chart)',
      '외부 신호 → 입법 lag prediction (Granger causality)',
      '시나리오 N 확장 — 카테고리별 시계열 변화 추적',
    ],
    primaryPersonas: ['data_ai', 'editorial', 'b2b'],
  },
};

export function getScenario(code: string): ScenarioMeta | undefined {
  return SCENARIO_META[code.toUpperCase()];
}
