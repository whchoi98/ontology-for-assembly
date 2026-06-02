'use client';

import Link from 'next/link';
import React, { useEffect, useState } from 'react';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

/**
 * 홈 페이지 - 14 시나리오 카드 그리드.
 *
 * Phase 4 완료 - 14개 시나리오 모두 implemented. 각 카드 description은 실제 구현된
 * narrative를 반영 (시나리오별 핵심 메커니즘 1줄). 배지는 Sidebar와 통일.
 */

interface CardDef {
  code: string;
  name: string;
  description: string;
  href: string;
  highlight?: string;
  category: '핵심' | '거버넌스' | '데이터·AI' | 'B2C·B2B';
}

const CARDS: CardDef[] = [
  // ─── 핵심 wow 시나리오 (PDF 시그니처) ───────────────────────────
  {
    code: 'A',
    name: '의미 검색',
    description: 'BM25(Nori) + Cohere KNN + RRF + rerank-v3로 의안·의원 검색. 1-hop subgraph.',
    href: '/search',
    category: '핵심',
  },
  {
    code: 'B',
    name: '3-stage 챗봇',
    description: 'Chatbot(RAG) / Agent(Tool Use) / Agentic AI(4 에이전트) 사이드바이사이드 비교 시연.',
    href: '/chat',
    highlight: '데모 메인',
    category: '핵심',
  },
  {
    code: 'K',
    name: '표결 이상치',
    description: '당론 이탈·박빙 표결·정파 초월 협력 3 유형. deviation_score + AI 패턴 라벨.',
    href: '/outlier',
    highlight: 'PDF ★',
    category: '핵심',
  },
  {
    code: 'M',
    name: '의원 정치 여정',
    description: '단일 의원의 발의·공동발의·표결·발언·위원회 활동을 시간순 통합 timeline.',
    href: '/journey',
    highlight: 'PDF ★',
    category: '핵심',
  },

  // ─── AI 거버넌스 ───────────────────────────────────────────────
  {
    code: 'L',
    name: '광고 매칭 매트릭스',
    description: 'keyword / embedding / Agent 3-way 비교. Agent만 비위 의혹·비극 콘텐츠에서 광고 거절.',
    href: '/ad-match',
    highlight: 'AI 거버넌스',
    category: '거버넌스',
  },
  {
    code: 'I',
    name: '편향·중립성',
    description: 'ADR-0004 4-layer 가드레일 + political_balance_score 실시간 채점 4 등급 시연.',
    href: '/neutrality',
    highlight: 'AI 거버넌스',
    category: '거버넌스',
  },

  // ─── 데이터·AI 분석 ────────────────────────────────────────────
  {
    code: 'E',
    name: '의원 클러스터링',
    description: '5 thematic cluster. 토픽 활동 vector 기반 → 정파 가로지르는 cross-party 협력 그룹.',
    href: '/cluster',
    highlight: '5 cluster',
    category: '데이터·AI',
  },
  {
    code: 'F',
    name: '룩어라이크',
    description: 'seed 의원 → top-K 유사 후보. cluster + activity proximity + cross-party bonus.',
    href: '/lookalike',
    category: '데이터·AI',
  },
  {
    code: 'J',
    name: '외부 신호 융합',
    description: '뉴스·SNS·여론조사 시그널 × 입법 활동 12주 시계열. signal_leads / legislation_leads / decoupled.',
    href: '/external-signal',
    highlight: '3 패턴',
    category: '데이터·AI',
  },
  {
    code: 'N',
    name: '이슈 × 입법',
    description: '8 매크로 이슈 × 4 활동 결합 강도 heatmap + Top 5 강한 결합 인사이트.',
    href: '/issue-legislation',
    highlight: '8×4 heatmap',
    category: '데이터·AI',
  },

  // ─── B2C·B2B 시연 ──────────────────────────────────────────────
  {
    code: 'C',
    name: '기사 인사이트',
    description: '합성 기사 60건 풀 + 토픽 필터 + 정치 균형 점수 + 참조 의안·의원 인사이트.',
    href: '/insights',
    category: 'B2C·B2B',
  },
  {
    code: 'D',
    name: '페르소나 매칭',
    description: '기사·콘텐츠 → 6 페르소나 적합도 매트릭스 + reasons + 권장 사유.',
    href: '/persona-match',
    highlight: '6 페르소나',
    category: 'B2C·B2B',
  },
  {
    code: 'G',
    name: '기사 ROI',
    description: '비용·도달·전환 + 6 페르소나별 KPI 변환 (편집국 후속 취재 ~ B2B API 가치).',
    href: '/article-roi',
    category: 'B2C·B2B',
  },
  {
    code: 'H',
    name: '지역구 지도',
    description: '17 KOSTAT 시도 choropleth. 22대 254 지역구 분포 + 시도별 활동 stats.',
    href: '/district-map',
    highlight: '17 시도',
    category: 'B2C·B2B',
  },
];

const CATEGORY_ORDER: CardDef['category'][] = ['핵심', '거버넌스', '데이터·AI', 'B2C·B2B'];

const CATEGORY_META: Record<CardDef['category'], { name: string; color: string }> = {
  '핵심':         { name: '핵심 wow 시나리오',         color: 'border-blue-200 bg-blue-500/15' },
  '거버넌스':     { name: 'AI 거버넌스',              color: 'border-purple-200 bg-purple-500/15' },
  '데이터·AI':    { name: '데이터·AI 분석',           color: 'border-cyan-200 bg-cyan-50' },
  'B2C·B2B':      { name: 'B2C·B2B 시연',            color: 'border-emerald-200 bg-emerald-50' },
};


interface MemberInfo {
  assembly_id: string;
  name: string;
  party: string;
  district: string;
  profile_image_url: string;
  analytics: { composite_score: number; bills_proposed: number; media_mentions_30d: number };
}

export default function HomePage() {
  const [members, setMembers] = useState<MemberInfo[]>([]);

  useEffect(() => {
    fetch(`${BASE}/api/members`, { cache: 'no-store' })
      .then((r) => r.json()).then((d) => setMembers(d.members ?? []))
      .catch(() => setMembers([]));
  }, []);

  // KPI 계산
  const totalMembers = members.length || 286;
  const totalBills = members.reduce((sum, m) => sum + (m.analytics?.bills_proposed ?? 0), 0);
  const avgComposite = members.length > 0
    ? members.reduce((s, m) => s + m.analytics.composite_score, 0) / members.length
    : 70;
  const topActive = [...members].sort((a, b) => b.analytics.composite_score - a.analytics.composite_score).slice(0, 5);
  const totalMedia = members.reduce((s, m) => s + (m.analytics?.media_mentions_30d ?? 0), 0);
  // 정당 분포 (top 5)
  const partyCount = members.reduce<Record<string, number>>((acc, m) => {
    acc[m.party] = (acc[m.party] ?? 0) + 1; return acc;
  }, {});
  const topParties = Object.entries(partyCount).sort((a, b) => b[1] - a[1]).slice(0, 5);

  return (
    <div>
      {/* ─── Header ─── */}
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-white tracking-tight mb-1">Assembly Insight Hub</h1>
        <div className="text-xs text-slate-500 mb-2">국회 인사이트 허브</div>
        <p className="text-sm text-slate-400">
          22대 국회 활동 분석 · 6 페르소나 × 14 시나리오. 좌측 페르소나 토글로 어조·정렬·hint가 즉시 재구성 ·
          Sonnet 4.6 + Neptune + OpenSearch + AgentCore.
        </p>
      </header>

      {/* ─── KPI Hero (6 카드) ─── */}
      <section className="mb-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard label="전체 의원" value={totalMembers} suffix="명"
                 sparklineData={[270, 275, 280, 282, 284, 285, totalMembers]}
                 trend="+1.4%" />
        <KpiCard label="발의 의안 (누적)" value={totalBills} suffix="건"
                 sparklineData={[800, 820, 850, 880, 920, 950, totalBills || 1000]}
                 trend="+5.3%" />
        <KpiCard label="평균 활동 점수" value={Number(avgComposite.toFixed(1))} suffix="/100"
                 sparklineData={[65, 67, 68, 69, 70, 70, avgComposite || 70]}
                 trend="+2.1%" accent />
        <KpiCard label="언론 노출 (30일)" value={totalMedia} suffix="회"
                 sparklineData={[3200, 3500, 3800, 4100, 4500, 4800, totalMedia || 5000]}
                 trend="+8.9%" />
        <KpiCard label="시나리오 활성" value={14} suffix="/14"
                 sparklineData={[8, 10, 11, 13, 14, 14, 14]} trend="100%" />
        <KpiCard label="페르소나" value={6} suffix="유형"
                 sparklineData={[3, 4, 5, 6, 6, 6, 6]} trend="4 tier" />
      </section>

      {/* ─── 상위 활동 의원 + 정당 분포 ─── */}
      <section className="mb-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 상위 활동 의원 5명 */}
        <div className="lg:col-span-2 bg-slate-900/40 border border-slate-800 rounded-lg p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-sm font-bold text-white tracking-tight">📊 상위 활동 의원</h2>
            <Link href="/members" className="text-[11px] text-blue-300 hover:underline">디렉토리 →</Link>
          </div>
          {topActive.length === 0 ? (
            <p className="text-xs text-slate-500 italic">데이터 로드 중...</p>
          ) : (
            <ul className="space-y-2">
              {topActive.map((m, i) => (
                <li key={m.assembly_id}>
                  <Link href={`/objects/Person/${encodeURIComponent(m.assembly_id)}`}
                        className="flex items-center gap-3 p-2 rounded hover:bg-slate-800/60 transition-colors">
                    <span className="text-amber-400 font-mono text-xs w-5 text-right">#{i + 1}</span>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={m.profile_image_url} alt={m.name}
                         className="w-9 h-9 rounded-full bg-slate-800 object-cover" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold text-slate-100 truncate">{m.name}</div>
                      <div className="text-[10px] text-slate-500 truncate">{m.party} · {m.district}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-base font-bold text-amber-300">{m.analytics.composite_score.toFixed(1)}</div>
                      <div className="text-[9px] text-slate-500">composite</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 정당 분포 */}
        <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-4">
          <h2 className="text-sm font-bold text-white tracking-tight mb-3">🏛️ 정당 분포</h2>
          {topParties.length === 0 ? (
            <p className="text-xs text-slate-500 italic">데이터 로드 중...</p>
          ) : (
            <ul className="space-y-2">
              {topParties.map(([party, count]) => {
                const pct = (count / totalMembers) * 100;
                return (
                  <li key={party}>
                    <div className="flex items-baseline justify-between text-xs mb-0.5">
                      <span className="text-slate-200 truncate">{party}</span>
                      <span className="font-mono text-slate-400">{count}명 · {pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div className="h-1.5 bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="mt-3 pt-3 border-t border-slate-800 text-[10px] text-slate-500">
            22대 국회 286 의원 · ADR-0004 정파 색 미사용
          </div>
        </div>
      </section>

      {/* ─── 추천 시나리오 (페르소나별 자동) ─── */}
      <section className="mb-8 bg-gradient-to-br from-slate-900/80 to-slate-900/40 border border-slate-800 rounded-lg p-4">
        <h2 className="text-sm font-bold text-white tracking-tight mb-3">💡 빠른 시작</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Link href="/chat" className="p-3 bg-slate-800/60 border border-slate-700 rounded hover:border-amber-500/50 transition-colors">
            <div className="text-xs text-amber-300 font-semibold mb-1">데스크 챗봇</div>
            <div className="text-[11px] text-slate-400">Sonnet 4.6 대화</div>
          </Link>
          <Link href="/mindmap" className="p-3 bg-slate-800/60 border border-slate-700 rounded hover:border-blue-500/50 transition-colors">
            <div className="text-xs text-blue-300 font-semibold mb-1">온톨로지 관계 그래프</div>
            <div className="text-[11px] text-slate-400">1-3 hop Neptune</div>
          </Link>
          <Link href="/members" className="p-3 bg-slate-800/60 border border-slate-700 rounded hover:border-emerald-500/50 transition-colors">
            <div className="text-xs text-emerald-300 font-semibold mb-1">의원 디렉토리</div>
            <div className="text-[11px] text-slate-400">286명 · 9 지표</div>
          </Link>
          <Link href="/district-map" className="p-3 bg-slate-800/60 border border-slate-700 rounded hover:border-purple-500/50 transition-colors">
            <div className="text-xs text-purple-300 font-semibold mb-1">지역구 지도</div>
            <div className="text-[11px] text-slate-400">17 시도 SVG</div>
          </Link>
        </div>
      </section>

      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-lg font-bold text-white">14 시나리오 (A–N)</h2>
        <span className="text-xs text-slate-500">상세 시연 진입</span>
      </div>

      {CATEGORY_ORDER.map((cat) => {
        const cards = CARDS.filter((c) => c.category === cat);
        const meta = CATEGORY_META[cat];
        return (
          <section key={cat} className="mb-8">
            <div className="flex items-baseline gap-2 mb-3">
              <h2 className="text-lg font-bold text-white">{meta.name}</h2>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${meta.color}`}>
                {cards.length} 시나리오
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {cards.map((card) => (
                <Link key={card.code} href={card.href} className="block">
                  <article className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 transition-shadow hover:shadow-md hover:border-blue-300">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-sm text-slate-500">시나리오 {card.code}</span>
                      {card.highlight && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 font-medium">
                          {card.highlight}
                        </span>
                      )}
                    </div>
                    <h3 className="text-lg font-semibold mb-1.5 text-white">{card.name}</h3>
                    <p className="text-sm text-slate-300 leading-relaxed">{card.description}</p>
                  </article>
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}


function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-800 text-slate-200">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono font-semibold text-white">{value}</span>
    </span>
  );
}


function KpiCard({
  label, value, suffix = '', sparklineData, trend, accent = false,
}: {
  label: string; value: number; suffix?: string; sparklineData: number[];
  trend: string; accent?: boolean;
}) {
  return (
    <div className={
      'rounded-lg border p-3 transition-colors ' +
      (accent ? 'bg-slate-900/60 border-amber-500/30' : 'bg-slate-900/40 border-slate-800 hover:border-slate-600')
    }>
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{label}</div>
      <div className="flex items-baseline gap-1 mb-1.5">
        <span className={`text-2xl font-bold ${accent ? 'text-amber-300' : 'text-white'} tracking-tight`}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </span>
        <span className="text-xs text-slate-500">{suffix}</span>
      </div>
      <Sparkline data={sparklineData} color={accent ? '#fbbf24' : '#60a5fa'} />
      <div className="text-[10px] text-emerald-400 mt-1 font-mono">{trend}</div>
    </div>
  );
}


function Sparkline({ data, color = '#60a5fa' }: { data: number[]; color?: string }) {
  if (data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const W = 100, H = 24;
  const step = W / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * step;
    const y = H - ((v - min) / range) * (H - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-6">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5"
                strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={(data.length - 1) * step} cy={H - ((data[data.length - 1] - min) / range) * (H - 2) - 1}
              r="2" fill={color} />
    </svg>
  );
}
