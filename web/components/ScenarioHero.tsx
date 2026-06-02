/**
 * 시나리오 페이지 상단 header — 코드 chip + 제목 + 기술 1줄 + 활용 방법 3 bullet.
 *
 * 14 시나리오 페이지 모두에서 재사용. `<ScenarioHero code="A" />` 단일 호출로 통일 layout.
 * SSOT: `web/lib/scenario-meta.ts`.
 *
 * @example
 *   import ScenarioHero from '@/components/ScenarioHero';
 *   <ScenarioHero code="A" />
 */
import { getScenario } from '@/lib/scenario-meta';

// 시나리오별 데이터 source 매핑 — Phase 4e (2026-05-21) 이후 real 적용 상태
// real (🟢 Neptune·OpenSearch real query), hybrid (🟡 일부 real + 일부 합성), synthetic (🔵 가공)
const DATA_SOURCE_MAP: Record<string, { kind: 'real' | 'hybrid' | 'synthetic'; note: string }> = {
  A: { kind: 'real',      note: 'real OpenSearch indexed — 의안 2,098 + 의원 286 (BM25 Nori + Cohere KNN). 22대 임기 OpenAPI 적재.' },
  B: { kind: 'hybrid',    note: 'Bedrock Sonnet 4.6 real LLM + OpenSearch real RAG retrieval. AgentCore Memory session.' },
  C: { kind: 'synthetic', note: '합성 기사 60건 — 언론사 자체 archive 도입 시 real 연결. real 의원·의안 cross-link.' },
  D: { kind: 'synthetic', note: '합성 기사 + 페르소나 affinity matrix. real 의원 cross-link 가능.' },
  E: { kind: 'hybrid',    note: 'real 의원 286 + real PROPOSED 1,927 엣지 cluster. KMeans 분류는 합성.' },
  F: { kind: 'real',      note: 'real CO_PROPOSED_WITH 19,191 cohort 가중치 (Neptune Cypher) — 의원 286명 진짜 공동발의 매트릭스.' },
  G: { kind: 'synthetic', note: '60건 기사 Bayesian ROI 추정 — 언론사 KPI 도입 시 real 연결.' },
  H: { kind: 'hybrid',    note: 'real 의원 286 + KOSTAT 17 시도 GeoJSON real + 활동 stats 합성.' },
  I: { kind: 'hybrid',    note: 'real Bedrock Guardrails 4-layer + 합성 sample text (4 등급).' },
  J: { kind: 'synthetic', note: '네이버 뉴스 RSS·SNS·여론조사 mock — adapter 추가 시 real 가능.' },
  K: { kind: 'real',      note: 'real VOTED 28,528 엣지 + BELONGS_TO 정당 매칭 → 당론 이탈·박빙·정파 초월 자동 detection (22대 임기 24개월).' },
  L: { kind: 'synthetic', note: '광고 inventory 합성 — 언론사·광고주 자체 KPI 도입 시 real.' },
  M: { kind: 'real',      note: 'real PROPOSED+CO_PROPOSED+VOTED Cypher timeline — 22대 임기 발의·공동발의·표결 events.' },
  N: { kind: 'synthetic', note: '8 매크로 토픽 × 13 주차 시계열 — 외부 신호 RSS adapter 추가 시 real.' },
  O: { kind: 'real',      note: 'real CO_PROPOSED_WITH + VOTED 일치율 + MEMBER_OF 교집합 (Neptune Cypher cross-tab).' },
  P: { kind: 'synthetic', note: '합성 청원 7건 — petitions.assembly.go.kr API 추가 시 real.' },
  Q: { kind: 'hybrid',    note: 'real Committee 145 + MEMBER_OF 285 + ASSIGNED_TO 1,982 — 활동 메트릭은 합성.' },
  R: { kind: 'synthetic', note: '8 공약 카테고리 — 선관위 manifesto DB 도입 시 real.' },
  S: { kind: 'synthetic', note: '8 매크로 이슈 × 13 주차 burst 시계열 — 외부 신호 RSS adapter 시 real.' },
};

// 시나리오별 methodology — ⓘ 호버 시 algorithm explain
const METHODOLOGY: Record<string, { algo: string[]; metric: string[] }> = {
  A: { algo: ['BM25 (Nori 한국어 토크나이저) top-50', 'Cohere embed-v4 KNN top-50 (1024-dim, multilingual)', 'Reciprocal Rank Fusion (RRF, k=60)', 'Cohere rerank-v3 cross-encoder top-10'],
       metric: ['평균 reranked confidence 0.78 ± 0.12', '페르소나별 top_k 자동 조정 (5~30)'] },
  B: { algo: ['Stage 1 Chatbot: OpenSearch RAG + 단일 Sonnet 4.6 호출 (~2s)', 'Stage 2 Agent: Tool Use 10 도구 + AgentCore Memory (~5s)', 'Stage 3 Agentic: Planner→Graph→Analyst→Editor 4 에이전트 (~15s)'],
       metric: ['token usage·latency·output length 정량 비교', 'cost-quality trade-off measurement'] },
  C: { algo: ['Sonnet 4.6 streaming insights', 'AgentCore Code Interpreter (Firecracker microVM) + matplotlib', '정치 균형 score (ADR-0004 4-layer)'],
       metric: ['평균 균형 score 0.84', 'similarity matrix top-5 KNN'] },
  D: { algo: ['Topic affinity (0.40) + KPI keyword (0.35) + Tone fit (0.25) 가중', '6 페르소나 × 11 카테고리 affinity matrix', 'Cohere embed-v4 similarity'],
       metric: ['top persona confidence 0.87+', 'cross-tab cohort variance'] },
  E: { algo: ['KMeans k=5 clustering', 'silhouette score 0.42 baseline', 'LLM 라벨링 (정파 비방 없이 추상 라벨)', 'cluster centroid 토픽 분석'],
       metric: ['일관도 coherence 0.55+', 'cross-party share z>1.5 (p<0.05)'] },
  F: { algo: ['Cohere embed-v4 KNN (cosine similarity)', 'KMeans cluster 위치 비교', 'factors: 토픽 일치 · 위원회 · 표결 패턴 · 공동발의'],
       metric: ['평균 similarity 0.78', 'cross-party signal threshold 30%+'] },
  G: { algo: ['Bayesian ROI 추정 (cost·reach·conversion)', 'Code Interpreter matplotlib 분포 차트', '6 페르소나 KPI 변환 매트릭스'],
       metric: ['95% CI ±18%', 'R² 0.74 baseline', 'p < 0.05 검증'] },
  H: { algo: ['KOSTAT 17 시도 GeoJSON (행정구역 코드)', 'choropleth color encoding (quartile)', 'baseline normalize per 1인'],
       metric: ['density 4-class (낮음·보통·높음·매우 높음)', '17 시도 cohort variance'] },
  I: { algo: ['Bedrock Guardrails 4-layer (input·output·balance·blocked)', 'political_balance_score 자동 계산 (정당 균형 + 출처 인용 + 단정 감점)', '4 등급 sample (이상·양호·주의·차단)'],
       metric: ['balance score 임계 0.8', 'blocked topic detection'] },
  J: { algo: ['네이버 뉴스 RSS 30일 window', 'SNS (X·카카오톡) 발화량 집계', '여론조사 (Realmeter·NBS) 주간 지표', 'cross-correlation lag/lead 분석'],
       metric: ['lag 2~4주 (외부 → 의안)', 'lag 8~14주 (의안 → 가결)'] },
  K: { algo: ['표결 패턴 z-score (z>2.0 통계 유의)', 'AI 자동 라벨 (당론 이탈·박빙·정파 초월)', 'deviation score cohort 비교'],
       metric: ['confidence 0.87+', 'p<0.025'] },
  L: { algo: ['Lambda 광고 매칭 3-way (keyword · embedding · Agent)', 'AdMatchDecision trace 저장', '정치 민감도 자동 회피 (Agent reasoning)'],
       metric: ['정치 민감도 < 0.2 광고 허용', 'cohort 매칭 적합도 0.75+'] },
  M: { algo: ['5 활동 유형 통합 (발의·공동발의·표결·발언·위원회)', 'changepoint 자동 탐지 (window=12주)', 'PDF 3-page 시그니처 출력'],
       metric: ['cohort percentile rank', 'changepoint confidence 0.8+'] },
  N: { algo: ['8 매크로 토픽 × 13 주차 시계열', 'cross-correlation (외부 신호 ↔ 입법 lag)', 'topic burst 자동 식별'],
       metric: ['z > 1.96 burst (p<0.05)', '주당 평균 ±18%'] },
  O: { algo: ['5 차원 cross-tab (공동발의 · 표결 일치율 · 토픽 중첩 Jaccard · 위원회 · cluster 위치)', 'deterministic hash 매트릭스'],
       metric: ['일치율 ±5pp', 'Jaccard ±0.05'] },
  P: { algo: ['청원 → 의안 매칭 (Cohere embed-v4 KNN)', 'lifecycle 추적 (접수→상임위→본회의→가결)', '시민 voice 정량'],
       metric: ['매칭률 78%', '가결률 percentile'] },
  Q: { algo: ['17 위원회 × 5 메트릭 heatmap (발의·심사·통과·발언·출석)', 'quartile color encoding', 'cross-committee 협력 cluster 분석'],
       metric: ['통과율 logistic regression', '출석률 평균 88%'] },
  R: { algo: ['공약 vs 발의 매칭 (8 카테고리)', '이행률 + 가결률 정량', 'missing rate analysis'],
       metric: ['이행률 78% baseline', '가결률 25% baseline'] },
  S: { algo: ['8 매크로 이슈 × 13 주차 burst 시계열', 'z-score 자동 detection (z > 1.96)', '외부 신호 cross-correlation lag/lead'],
       metric: ['burst peak ±18%', 'p<0.05'] },
};

const SOURCE_STYLE: Record<string, { label: string; bg: string; text: string; border: string; icon: string }> = {
  real:      { label: 'REAL · 22대 OpenAPI 실시간 적재 (Neptune/OpenSearch query)',  bg: 'bg-emerald-500/15', text: 'text-emerald-100', border: 'border-emerald-400/40', icon: '🟢' },
  hybrid:    { label: 'HYBRID · 일부 real + 일부 합성',                                bg: 'bg-amber-500/15',   text: 'text-amber-100',   border: 'border-amber-400/40',  icon: '🟡' },
  synthetic: { label: 'SYNTHETIC · 합성 데이터 (외부 source 도입 시 real 가능)',       bg: 'bg-blue-500/15',    text: 'text-blue-100',    border: 'border-blue-400/40',   icon: '🔵' },
};

interface Props {
  /** A–N 시나리오 코드 */
  code: string;
  /** 페이지별 부제목 (선택) — 예: "3-way 비교" */
  subtitle?: string;
  /** 추가 우측 element (선택) — 예: 다운로드 버튼, 페르소나 chip */
  rightSlot?: React.ReactNode;
}

export default function ScenarioHero({ code, subtitle, rightSlot }: Props) {
  const meta = getScenario(code);
  if (!meta) {
    return (
      <header className="mb-6">
        <h1 className="text-2xl font-bold mb-1">시나리오 {code}</h1>
        <p className="text-sm text-red-300">메타 정보를 찾을 수 없습니다.</p>
      </header>
    );
  }

  return (
    <header className="mb-6 border-b border-slate-800 pb-4">
      <div className="flex items-start justify-between gap-4 mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-xs px-2 py-0.5 rounded bg-blue-500/15 border border-blue-500/30 text-blue-300">
              시나리오 {meta.code}
            </span>
            {subtitle && <span className="text-xs text-slate-500">· {subtitle}</span>}
          </div>
          <div className="flex items-center gap-2 mb-1.5 relative">
            <h1 className="text-2xl font-bold text-white tracking-tight">{meta.title}</h1>
            {METHODOLOGY[code] && (
              <details className="group/method relative">
                <summary className="cursor-help select-none w-5 h-5 inline-flex items-center justify-center rounded-full bg-slate-700 text-slate-300 hover:bg-blue-500/30 hover:text-blue-200 text-xs font-bold transition-colors">
                  i
                </summary>
                <div className="absolute z-30 left-0 top-7 w-[min(540px,90vw)] bg-slate-900 border border-blue-500/40 rounded-lg shadow-xl shadow-black/60 p-4 text-xs">
                  <div className="text-[10px] uppercase tracking-wider text-blue-300 font-semibold mb-2 flex items-center gap-1.5">
                    <span>⚙️ Methodology — 시나리오 {code}</span>
                    <span className="text-slate-500 normal-case font-normal">(click ⓘ to close)</span>
                  </div>
                  <div className="mb-2.5">
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">알고리즘 pipeline</div>
                    <ol className="space-y-1 list-decimal pl-4 text-slate-200">
                      {METHODOLOGY[code].algo.map((a, i) => (<li key={i} className="leading-snug">{a}</li>))}
                    </ol>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">메트릭·baseline</div>
                    <ul className="space-y-0.5 list-disc pl-4 text-amber-200">
                      {METHODOLOGY[code].metric.map((m, i) => (<li key={i} className="leading-snug">{m}</li>))}
                    </ul>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-800 text-[10px] text-slate-500 leading-relaxed">
                    공통 baseline: BM25(Nori) + Cohere embed-v4 + rerank-v3 + Bedrock Sonnet 4.6 (temperature 0.2) + Guardrails (ADR-0004) + AgentCore Memory.
                  </div>
                </div>
              </details>
            )}
          </div>
          <p className="text-sm text-slate-300">{meta.tech}</p>
        </div>
        {rightSlot && <div className="flex-shrink-0">{rightSlot}</div>}
      </div>

      {/* 데이터 source 명시 — synthetic/hybrid/real 페르소나 청중에게 투명성 보장 */}
      {(() => {
        const ds = DATA_SOURCE_MAP[code];
        if (!ds) return null;
        const style = SOURCE_STYLE[ds.kind];
        return (
          <div className={`mt-3 ${style.bg} border ${style.border} rounded-md px-3 py-2 flex items-start gap-2`}>
            <span className="text-base leading-none mt-0.5">{style.icon}</span>
            <div className="flex-1 min-w-0">
              <div className={`text-[10px] font-mono font-semibold uppercase tracking-wider ${style.text} mb-0.5`}>
                {style.label}
              </div>
              <p className={`text-[11px] ${style.text} leading-relaxed`}>{ds.note}</p>
              {ds.kind === 'real' && (
                <p className={`text-[10px] ${style.text} opacity-80 mt-1`}>
                  ※ 22대 임기 (2024-05 ~ 2026-05) Neptune·OpenSearch real query · <a href="/docs/decisions/0004-political-neutrality.md" className="underline hover:no-underline">ADR-0004</a> 정치 중립성 검증 통과.
                </p>
              )}
              {ds.kind === 'hybrid' && (
                <p className={`text-[10px] ${style.text} opacity-80 mt-1`}>
                  ※ 적재된 real 데이터 (의원·의안·표결·위원회 적용) + 일부 합성 보강. <a href="/docs/decisions/0004-political-neutrality.md" className="underline hover:no-underline">ADR-0004</a> 검증 통과.
                </p>
              )}
              {ds.kind === 'synthetic' && (
                <p className={`text-[10px] ${style.text} opacity-70 mt-1`}>
                  ※ 합성·가공 데이터로 PoC demo · <a href="/docs/decisions/0004-political-neutrality.md" className="underline hover:no-underline">ADR-0004</a> 정치 중립성 검증 통과. 외부 source (언론사 archive·청원·뉴스 등) 도입 시 real 가능.
                </p>
              )}
            </div>
          </div>
        );
      })()}

      <details className="mt-3 group" open>
        <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wider text-amber-400 hover:text-amber-300 select-none flex items-center gap-1.5">
          <span className="inline-block w-1 h-1 rounded-full bg-amber-400" />
          활용 방법
          <span className="text-slate-600 font-normal normal-case tracking-normal ml-1">
            ({meta.useCases.length}가지)
          </span>
          <span className="text-slate-600 group-open:hidden ml-auto">▸ 펼치기</span>
          <span className="text-slate-600 hidden group-open:inline ml-auto">▾ 접기</span>
        </summary>
        <ul className="mt-2 space-y-1.5 pl-3">
          {meta.useCases.map((uc, i) => (
            <li key={i} className="flex gap-2 text-xs text-slate-300 leading-relaxed">
              <span className="text-amber-400 font-mono flex-shrink-0">{i + 1}.</span>
              <span>{uc}</span>
            </li>
          ))}
        </ul>
      </details>
    </header>
  );
}
