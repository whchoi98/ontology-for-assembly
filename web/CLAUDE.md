# web/ — Next.js 14 Frontend (TypeScript, ARM64)

`web/`은 14 시나리오 페이지 + 객체 탐색기 + 메타 페이지 + 운영 콘솔을 담은 프론트. 6 페르소나 컨텍스트가 모든 화면에 일관 적용된다.

## Structure

```
web/
├── app/                          App Router
│   ├── page.tsx                  # 홈 — 14 시나리오 카드 (페르소나별 색·정렬)
│   ├── search/page.tsx           # A
│   ├── chat/page.tsx             # B — 3 패널 사이드바이사이드 (ThreeStageCompare)
│   ├── insights/page.tsx         # C
│   ├── persona-match/page.tsx    # D
│   ├── cluster/page.tsx          # E
│   ├── lookalike/page.tsx        # F
│   ├── article-roi/page.tsx      # G
│   ├── district-map/page.tsx     # H
│   ├── neutrality/page.tsx       # I — political_balance_score 대시보드
│   ├── external-signal/page.tsx  # J
│   ├── outlier/page.tsx          # K
│   ├── ad-match/page.tsx         # L — 3-mode 토글 + AdMatchDecision trace
│   ├── journey/page.tsx          # M
│   ├── issue-legislation/page.tsx # N
│   ├── objects/[type]/page.tsx   # 25+ 클래스 객체 리스트
│   ├── objects/[type]/[id]/page.tsx # 1-hop subgraph 디테일
│   ├── meta/page.tsx             # 온톨로지 메타 (ER · 표준 · 검증 3 탭)
│   └── ops/page.tsx              # 운영 콘솔 5 패널
├── components/
│   ├── PersonaSwitch.tsx         # 6 페르소나 토글 (drop-down + 검색)
│   ├── GuidedTour.tsx            # 6 페르소나 × 14 시나리오 추천 카드
│   ├── CytoscapeView.tsx         # 1-hop subgraph 시각화
│   ├── KoreaChoropleth.tsx       # 17 시도 GeoJSON + 의원 분포
│   ├── JourneyTimeline.tsx       # 의원 정치 여정 timeline
│   ├── DataSourceBadge.tsx       # real/synthetic/external 배지 (모든 페이지 상단 필수)
│   ├── AdMatchSidebar.tsx        # 우측 위젯 — B2C 페르소나 필수
│   ├── ThreeStageCompare.tsx     # 시나리오 B 전용 3 패널
│   ├── BiasScoreIndicator.tsx    # political_balance_score 시각화 (<0.8 노란색)
│   └── Sidebar.tsx               # 좌측 — 페르소나 priority에 따라 자동 정렬
└── lib/
    ├── api-client.ts             # 타입 안전 SSE + REST 클라이언트
    ├── persona-context.tsx       # React Context Provider (X-Persona-Id 자동 첨부)
    └── streamSSE.ts              # SSE generic helper (`type: phase|delta|log|final|result`)
```

## Key Design Decisions

- **PersonaSwitch + persona-context**: 페르소나 토글 시 즉시 사이드바·홈 카드·SystemPrompt가 재구성. `localStorage` + Context.
- **DataSourceBadge 강제 노출**: 모든 시나리오 페이지 상단. real/synthetic/external 명시. 누락은 code-reviewer가 차단.
- **AdMatchSidebar**: `general_reader` 페르소나일 때만 표시. 다른 페르소나는 숨김(`ad_policy`에 따라).
- **BiasScoreIndicator**: LLM 응답마다 자동 첨부. `score < 0.8`이면 노란색 경고 + 운영 콘솔 알림.
- **ThreeStageCompare** (시나리오 B): 3 패널이 같은 SSE event를 동시 스트리밍. Chatbot/Agent/Agentic 비교.

## Conventions

- **API 호출**: 항상 `lib/api-client.ts` 경유. `fetch()` 직접 호출 금지 (X-Persona-Id 자동 첨부 누락 위험).
- **SSE 소비**: `streamSSE<T>()` helper. `phase`/`delta`/`log`/`final` 이벤트만 처리.
- **마크다운**: `react-markdown` v10 + `remark-gfm`, `.chat-markdown` 스타일. chat/insights 응답 일관.
- **반응형**: Tailwind 디자인 시스템. 모바일은 Phase 5 polish에서만 (PoC는 데스크탑 우선).
- **Cytoscape**: 1-hop subgraph 표준 layout = cose-bilkent. 노드 색은 클래스별로 고정 (`CLASS_COLOR` map).
- **KoreaChoropleth**: KOSTAT 행정구역 코드 기준 17 시도. `Person.district.sido_code`로 join.

## Adding a New Scenario (프론트 측 6곳)

1. `app/<slug>/page.tsx` 페이지 생성
2. `components/Sidebar.tsx` 사이드바 entry 추가
3. `app/page.tsx` 홈 카드 추가 (CARD_COLOR map에서 색 선택)
4. `lib/api-client.ts` 타입드 함수 + 응답 타입
5. `components/GuidedTour.tsx` step 추가
6. (필요 시) 시나리오 전용 컴포넌트 (예: `WeatherOverlay`, `JourneyTimeline`)

## Persona-Aware Rendering

페르소나에 따라 다음이 자동 변경:
- Sidebar 정렬 (`PERSONA_REGISTRY.scenario_priority`)
- 홈 카드 하이라이트 (페르소나별 1·2순위)
- 챗 system prompt 어조 (백엔드에서 처리, UI는 응답 그대로)
- AdMatchSidebar 표시 여부 (`ad_policy === "full_ads_agent"`만)
- PDF 다운로드 버튼 (`paid_subscriber`, `b2b`만)

## Tests

- `tsc --noEmit` (CI 게이트)
- 컴포넌트 테스트는 Phase 5 polish에서 추가 (PoC는 type check만 강제)
