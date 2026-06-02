'use client';

/**
 * 시나리오 S — 분기별 토픽 burst 시계열.
 *
 * 8 매크로 이슈 × 13 주차 line chart.
 * 토픽 클릭 → 온톨로지 관계 그래프 (토픽 → burst 주차 의안 + 외부 신호) + AI 인사이트 (토픽 전체).
 */
import React, { useEffect, useMemo, useState } from 'react';
import ScenarioHero from '../../components/ScenarioHero';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import { CytoscapeView } from '../../components/CytoscapeView';
import type { Subgraph } from '../../lib/api-client';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface MemberLite {
  assembly_id: string;
  name: string;
  party: string;
  district: string;
  profile_image_url: string;
}

const TOPICS = [
  { key: 'ai',       label: 'AI·디지털',   color: '#3b82f6' },
  { key: 'housing',  label: '청년 주거',   color: '#f59e0b' },
  { key: 'env',      label: '환경·기후',   color: '#10b981' },
  { key: 'welfare',  label: '사회복지',    color: '#a78bfa' },
  { key: 'edu',      label: '교육',        color: '#22d3ee' },
  { key: 'econ',     label: '경제·재정',   color: '#fb923c' },
  { key: 'privacy',  label: '개인정보',    color: '#f472b6' },
  { key: 'foreign',  label: '외교·안보',   color: '#94a3b8' },
] as const;

type TopicKey = typeof TOPICS[number]['key'];

const SERIES: Record<TopicKey, number[]> = {
  ai:      [2, 3, 2, 4, 6, 8, 9, 7, 6, 5, 4, 4, 5],
  housing: [1, 2, 4, 7, 8, 6, 5, 3, 4, 6, 8, 9, 7],
  env:     [1, 1, 2, 3, 5, 7, 8, 6, 4, 3, 2, 2, 3],
  welfare: [3, 4, 4, 5, 6, 7, 8, 9, 8, 7, 6, 5, 5],
  edu:     [2, 2, 3, 4, 4, 5, 6, 5, 4, 5, 6, 7, 6],
  econ:    [4, 5, 5, 6, 6, 5, 5, 4, 4, 5, 6, 7, 8],
  privacy: [1, 1, 2, 2, 3, 4, 5, 6, 5, 4, 3, 3, 4],
  foreign: [3, 4, 5, 4, 3, 3, 4, 5, 6, 5, 4, 4, 5],
};

const TOPIC_BILLS: Record<TopicKey, string[]> = {
  ai:      ['AI 기본법', '알고리즘 투명성법', '디지털플랫폼 공정거래법', 'AI 학습데이터 보호법'],
  housing: ['청년 임대료 보조법', '전세사기 방지법', '주거 안정 특별법', '공공임대 확대법'],
  env:     ['재생에너지 가속법', '탄소중립 산업법', '에너지 전환법', '풍력·태양광 확대법'],
  welfare: ['노인 의료 보장법', '치매 국가책임법', '의료급여 확대법', '간병비 지원법'],
  edu:     ['사교육비 경감법', '초중등교육법 개정', '대학 등록금 안정법', '학생인권법'],
  econ:    ['세법 개정안', '소상공인 임대료법', '금융소비자보호법', '중소기업 지원법'],
  privacy: ['개인정보 보호 강화법', '디지털 인격권법', '사이버 안보법', '잊혀질 권리법'],
  foreign: ['해외동포 지원법', '외교통상 기본법', '남북교류협력법'],
};

const TOPIC_PROPOSERS: Record<TopicKey, string[]> = {
  ai:      ['고민정', '윤영찬'],
  housing: ['김민석', '박영선'],
  env:     ['우원식', '김태년', '정청래'],
  welfare: ['김태년', '서영교'],
  edu:     ['도종환', '김영호'],
  econ:    ['민형배', '이학영'],
  privacy: ['고민정', '윤영찬'],
  foreign: ['김도읍', '조정훈'],
};

const WEEKS = Array.from({ length: 13 }, (_, i) => `W${i + 1}`);

function buildTopicSubgraph(
  tKey: TopicKey, tLabel: string,
  burstWeek: number, burstValue: number,
  memberByName: Map<string, MemberLite>,
): Subgraph {
  const topicId = `Topic:${tKey}`;
  const bills = TOPIC_BILLS[tKey];
  const billIds = bills.map((_, i) => `Bill:${tKey}-B${i + 1}`);
  const burstNodeId = `Period:${tKey}-burst`;

  const proposers = TOPIC_PROPOSERS[tKey];
  const personNodes = proposers.map((name) => {
    const m = memberByName.get(name);
    return {
      id: `Person:${m?.assembly_id ?? name}`,
      label: 'Person' as const,
      data: {
        name,
        party: m?.party ?? '',
        district: m?.district ?? '',
        ...(m?.profile_image_url ? { profile_image_url: m.profile_image_url } : {}),
      },
    };
  });

  const nodes = [
    { id: topicId, label: 'Topic', data: { name: tLabel, burst_week: burstWeek, burst_value: burstValue } },
    { id: burstNodeId, label: 'Vote',
      data: { name: `W${burstWeek} burst — ${burstValue}건`, burst_week: burstWeek } },
    ...billIds.map((id, i) => ({ id, label: 'Bill', data: { name: bills[i] } })),
    ...personNodes,
  ];

  const edges = [
    { source: burstNodeId, target: topicId, type: 'ABOUT' },
    ...billIds.map((bid) => ({ source: bid, target: topicId, type: 'ABOUT' })),
    ...personNodes.flatMap((pn, pi) =>
      billIds.slice(0, 2).map((bid) => ({ source: pn.id, target: bid, type: pi === 0 ? 'PROPOSED' : 'CO_PROPOSED' })),
    ),
  ];

  return { root_id: topicId, nodes, edges };
}

export default function TopicBurstPage() {
  const [active, setActive] = useState<Set<TopicKey>>(new Set(TOPICS.map((t) => t.key)));
  const [selectedKey, setSelectedKey] = useState<TopicKey | null>(null);
  const [members, setMembers] = useState<MemberLite[]>([]);

  useEffect(() => {
    fetch(`${BASE}/api/members`)
      .then((r) => r.json())
      .then((d) => setMembers(d.members ?? []))
      .catch(() => setMembers([]));
  }, []);

  const memberByName = useMemo(() => {
    const m = new Map<string, MemberLite>();
    for (const x of members) m.set(x.name, x);
    return m;
  }, [members]);

  const maxVal = Math.max(...(Object.values(SERIES) as number[][]).flat());

  const toggle = (k: TopicKey) => {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  const bursts = useMemo(() =>
    TOPICS.map((t) => {
      const s = SERIES[t.key];
      const maxIdx = s.indexOf(Math.max(...s));
      return { ...t, burstWeek: maxIdx + 1, burstValue: s[maxIdx] };
    }), []);
  const topBursts = useMemo(() => [...bursts].sort((a, b) => b.burstValue - a.burstValue).slice(0, 3), [bursts]);

  const selectedBurst = selectedKey ? bursts.find((b) => b.key === selectedKey) : null;

  const subgraph = useMemo(() => {
    if (!selectedBurst) return null;
    return buildTopicSubgraph(
      selectedBurst.key, selectedBurst.label,
      selectedBurst.burstWeek, selectedBurst.burstValue,
      memberByName,
    );
  }, [selectedBurst, memberByName]);

  const insightContext = useMemo(() => {
    if (!selectedBurst) return null;
    const series = SERIES[selectedBurst.key];
    const total_filings = series.reduce((s, v) => s + v, 0);
    return {
      burst_id: `S-${selectedBurst.key.toUpperCase()}`,
      topic_key: selectedBurst.key,
      topic_label: selectedBurst.label,
      burst_week: selectedBurst.burstWeek,
      burst_value: selectedBurst.burstValue,
      total_filings_13w: total_filings,
      avg_per_week: (total_filings / 13).toFixed(1),
      topic_bills: TOPIC_BILLS[selectedBurst.key],
      topic_proposers: TOPIC_PROPOSERS[selectedBurst.key],
      series_13w: series,
    };
  }, [selectedBurst]);

  return (
    <div>
      <ScenarioHero code="S" subtitle="신규 ★" />

      {/* Top 3 burst — 클릭으로 select */}
      <section className="mb-6 grid grid-cols-3 gap-3">
        {topBursts.map((b) => {
          const isSelected = selectedKey === b.key;
          return (
            <button
              key={b.key}
              type="button"
              onClick={() => setSelectedKey(b.key)}
              className={
                'rounded-lg border p-3 text-left transition-colors ' +
                (isSelected
                  ? 'border-blue-500 bg-blue-500/15'
                  : 'border-slate-800 bg-slate-900/40 hover:border-slate-600')
              }
            >
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">burst top</div>
              <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: b.color }} />
                <span className="text-sm font-bold text-white">{b.label}</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                W{b.burstWeek} 주차 · <strong className="text-amber-300">{b.burstValue}건</strong>
              </div>
            </button>
          );
        })}
      </section>

      {/* 토픽 토글 — 더블 클릭으로 단일 토픽 focus */}
      <section className="mb-3">
        <div className="text-[10px] text-slate-500 mb-1.5">차트 표시 토글 · 단일 토픽 선택은 ↓ 아래 라벨 클릭</div>
        <div className="flex flex-wrap gap-1.5">
          {TOPICS.map((t) => {
            const isSelected = selectedKey === t.key;
            return (
              <div key={t.key} className="flex">
                <button
                  type="button"
                  onClick={() => toggle(t.key)}
                  className={
                    'text-[11px] px-2 py-1 rounded-l-full border-l border-y flex items-center gap-1 transition-opacity ' +
                    (active.has(t.key)
                      ? 'border-slate-600 bg-slate-800 text-slate-200'
                      : 'border-slate-800 bg-slate-900/40 text-slate-500 opacity-50')
                  }
                  aria-label={`차트 토글 ${t.label}`}
                >
                  <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: t.color }} />
                  {t.label}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedKey(t.key)}
                  className={
                    'text-[10px] px-1.5 py-1 rounded-r-full border-r border-y transition-colors ' +
                    (isSelected
                      ? 'border-blue-500 bg-blue-500/20 text-blue-200'
                      : 'border-slate-700 bg-slate-900 text-slate-400 hover:text-amber-200')
                  }
                  aria-label={`${t.label} 온톨로지 관계 그래프·인사이트`}
                  title="온톨로지 관계 그래프 + AI 인사이트"
                >★</button>
              </div>
            );
          })}
        </div>
      </section>

      {/* SVG line chart */}
      <section className="mb-6 border border-slate-800 bg-slate-900/40 rounded-lg p-4">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-3">13 주차 burst 시계열 (의안 발의 + 외부 신호)</div>
        <svg viewBox="0 0 700 300" className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
          {[0, 0.25, 0.5, 0.75, 1].map((r) => (
            <g key={r}>
              <line x1="40" y1={30 + r * 240} x2="680" y2={30 + r * 240} stroke="#1e293b" strokeDasharray="2,2" />
              <text x="35" y={35 + r * 240} textAnchor="end" className="text-[10px] fill-slate-500">
                {Math.round(maxVal * (1 - r))}
              </text>
            </g>
          ))}
          {WEEKS.map((w, i) => (
            <text key={w} x={40 + (i / 12) * 640} y="285" textAnchor="middle" className="text-[10px] fill-slate-500">{w}</text>
          ))}
          {TOPICS.filter((t) => active.has(t.key)).map((t) => {
            const series = SERIES[t.key];
            const isFocus = selectedKey === t.key;
            const points = series
              .map((v, i) => `${40 + (i / 12) * 640},${270 - (v / maxVal) * 240}`)
              .join(' ');
            return (
              <g key={t.key} opacity={selectedKey && !isFocus ? 0.25 : 1}>
                <polyline points={points} fill="none" stroke={t.color} strokeWidth={isFocus ? 3 : 2}
                          strokeLinejoin="round" strokeLinecap="round" />
                {series.map((v, i) => (
                  <circle key={i} cx={40 + (i / 12) * 640} cy={270 - (v / maxVal) * 240}
                          r={isFocus ? 3.5 : 2.5} fill={t.color} />
                ))}
              </g>
            );
          })}
        </svg>
      </section>

      {/* 온톨로지 관계 그래프 */}
      {selectedBurst && subgraph && (
        <section className="mb-6">
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            🕸️ 토픽 온톨로지 관계 그래프 — <span className="text-white">{selectedBurst.label}</span>
            <span className="ml-2 text-[10px] text-slate-500">
              W{selectedBurst.burstWeek} burst · 의안 {TOPIC_BILLS[selectedBurst.key].length}건 + 대표 발의 의원
            </span>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40">
            <CytoscapeView subgraph={subgraph} height={460} expandable={false} />
          </div>
        </section>
      )}

      {insightContext ? (
        <AIInsightPanel scenarioCode="S" context={insightContext} autoGenerate />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          토픽 (top burst 카드 또는 라벨의 ★)을 클릭하면 토픽 전체 온톨로지 관계 그래프 + AI 인사이트가 표시됩니다.
        </div>
      )}
    </div>
  );
}
