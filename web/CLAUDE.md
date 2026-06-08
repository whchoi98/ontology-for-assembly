# web/ — Next.js 14 Frontend (TypeScript, ARM64)

`web/`은 23 시나리오 페이지(A–W) + 의원 디렉토리 + 온톨로지 관계 그래프 + Object Explorer + 운영 콘솔 + 코드 지식 그래프(codegraph)를 담은 프론트. 6 페르소나 컨텍스트가 모든 화면에 일관 적용된다.

## Structure

```
web/
├── app/                          App Router
│   ├── page.tsx                  # 홈 — 23 시나리오 카드 (페르소나별 색·정렬)
│   ├── search/page.tsx           # A 의미 검색
│   ├── chat/page.tsx             # B 3-stage 비교 (+ chat/compare, chat/popup)
│   ├── insights/page.tsx         # C 기사 인사이트
│   ├── persona-match/page.tsx    # D 페르소나 매칭
│   ├── cluster/page.tsx          # E 의원 클러스터링
│   ├── lookalike/page.tsx        # F 룩어라이크
│   ├── article-roi/page.tsx      # G 기사 ROI
│   ├── district-map/page.tsx     # H 지역구 지도
│   ├── neutrality/page.tsx       # I political_balance_score 대시보드
│   ├── external-signal/page.tsx  # J 외부 신호 융합
│   ├── outlier/page.tsx          # K 표결 이상치
│   ├── ad-match/page.tsx         # L 3-mode 토글 + AdMatchDecision trace
│   ├── journey/page.tsx          # M 의원 정치 여정
│   ├── issue-legislation/page.tsx # N 이슈 × 입법 상관
│   ├── relations/page.tsx        # O 인물 관계
│   ├── petition-map/page.tsx     # P 청원 → 입법
│   ├── committee-heatmap/page.tsx # Q 위원회 영향력
│   ├── promise-tracker/page.tsx  # R 공약 이행
│   ├── topic-burst/page.tsx      # S 토픽 burst
│   ├── party-cohesion/page.tsx   # T 정당 응집도
│   ├── influence-rank/page.tsx   # U 의원 영향력
│   ├── voting-cluster/page.tsx   # V 표결 cluster
│   ├── swing-voters/page.tsx     # W swing voter
│   ├── mindmap/page.tsx          # 온톨로지 관계 그래프 (1–3 hop)
│   ├── members/page.tsx          # 의원 디렉토리 (286명 · 9 지표)
│   ├── objects/page.tsx          # Object Explorer 31 클래스 인덱스
│   ├── objects/[type]/page.tsx   # 클래스별 인스턴스 리스트
│   ├── objects/[type]/[id]/page.tsx # 1-hop subgraph 디테일
│   ├── ops/page.tsx              # 운영 콘솔 5 패널
│   └── codegraph/page.tsx        # 코드 지식 그래프 (graphify 정적 자산 임베드 — public/codegraph/, Sidebar OPS_LINKS, staff)
├── components/
│   ├── AppShell.tsx              # 레이아웃 셸 (Sidebar + TopBar)
│   ├── Sidebar.tsx               # 좌측 — 페르소나 priority 자동 정렬 (SCENARIOS SSOT)
│   ├── TopBar.tsx                # 상단 바
│   ├── PersonaSwitch.tsx         # 6 페르소나 토글
│   ├── GuidedTour.tsx            # 6 페르소나 × 시나리오 추천 카드
│   ├── ScenarioHero.tsx          # 시나리오 페이지 공통 헤더
│   ├── ChatThread.tsx            # 챗 스레드 렌더
│   ├── FloatingChat.tsx          # 플로팅 챗 위젯
│   ├── ToolCallPanel.tsx         # 도구/에이전트 호출 trace 패널
│   ├── AIInsightPanel.tsx        # LLM 인사이트 패널 (context trim — WAF 8KB)
│   ├── CytoscapeView.tsx         # subgraph 시각화 (fcose, 미등록 시 cose fallback)
│   ├── KoreaChoropleth.tsx       # 17 시도 GeoJSON + 의원 분포
│   ├── DataSourceBadge.tsx       # real/synthetic/external 배지 (현재 search 페이지에 적용; 전 페이지 확산 예정)
│   └── BiasScoreIndicator.tsx    # political_balance_score 시각화 (<0.8 노란색)
└── lib/
    ├── api-client.ts             # 타입 안전 SSE + REST 클라이언트 (X-Persona-Id 자동 첨부)
    ├── scenario-clients.ts       # 시나리오별 fetch 함수
    ├── scenario-meta.ts          # 시나리오 메타 (라벨·설명)
    ├── ops-client.ts             # 운영 콘솔 fetch
    └── personas.ts               # 페르소나 메타 + PERSONA_PRIMARY_SCENARIOS
```

## Key Design Decisions

- **PersonaSwitch + localStorage**: 페르소나 토글 시 `persona_id`를 `localStorage`에 저장 + `?p={id}` query로 재로드. 사이드바 정렬·홈 카드가 재구성. 페르소나 메타는 `lib/personas.ts`.
- **DataSourceBadge 노출 (목표)**: real/synthetic/external 출처를 페이지 상단에 명시하는 컨벤션. 현재는 `search/page.tsx`에 적용; 나머지 시나리오 페이지로 확산 예정 (code-reviewer 강제는 미도입).
- **BiasScoreIndicator**: LLM 응답마다 첨부. `score < 0.8`이면 노란색 경고 + 운영 콘솔 알림.
- **시나리오 B 3-stage**: `chat/page.tsx`가 Chatbot/Agent/Agentic 3 패널을 SSE로 스트리밍. `chat/compare`·`chat/popup` 변형 페이지 존재. 에이전트 호출 trace는 `ToolCallPanel`.
- **Sidebar SSOT**: 시나리오 목록·아이콘·배지는 `components/Sidebar.tsx:SCENARIOS` 배열이 단일 진실원.

## Conventions

- **API 호출**: 항상 `lib/api-client.ts` / `lib/scenario-clients.ts` 경유. `fetch()` 직접 호출 금지 (X-Persona-Id 자동 첨부 누락 위험).
- **SSE 소비**: `lib/api-client.ts`의 스트리밍 헬퍼 사용. `phase`/`delta`/`log`/`final`/`result`/`done` 이벤트 처리.
- **마크다운**: `react-markdown` v10 + `remark-gfm`, `.chat-markdown` 스타일. chat/insights 응답 일관.
- **반응형**: Tailwind 디자인 시스템. 모바일은 Phase 5 polish에서만 (PoC는 데스크탑 우선).
- **Cytoscape**: subgraph layout = `fcose`(force-directed; 등록 시), 미등록 시 `cose` fallback. 노드 색은 클래스별로 고정 (`CLASS_COLOR` map).
- **KoreaChoropleth**: KOSTAT 행정구역 코드 기준 17 시도. `Person.district.sido_code`로 join.

## Adding a New Scenario (프론트 측 6곳)

1. `app/<slug>/page.tsx` 페이지 생성
2. `components/Sidebar.tsx:SCENARIOS` 배열에 entry 추가 (code·icon·name·href·badge)
3. `app/page.tsx` 홈 카드 추가 (CARD_COLOR map에서 색 선택)
4. `lib/api-client.ts` / `lib/scenario-clients.ts` 타입드 함수 + 응답 타입
5. `components/GuidedTour.tsx` step 추가
6. (필요 시) 시나리오 전용 컴포넌트 (예: `CytoscapeView`, `KoreaChoropleth`)

## Persona-Aware Rendering

페르소나에 따라 다음이 자동 변경:
- Sidebar 정렬 (`PERSONA_REGISTRY.scenario_priority`)
- 홈 카드 하이라이트 (페르소나별 1·2순위)
- 챗 system prompt 어조 (백엔드에서 처리, UI는 응답 그대로)
- 광고 노출 정책 (`ad_policy` — `general_reader`만 광고 노출)
- PDF 다운로드 버튼 (`paid_subscriber`, `b2b`만)

## Tests

- `tsc --noEmit` (CI 게이트)
- 컴포넌트 테스트는 Phase 5 polish에서 추가 (PoC는 type check만 강제)
