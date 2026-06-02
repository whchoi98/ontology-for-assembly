'use client';

/**
 * 시나리오 R — 선거 공약 이행 추적.
 *
 * 22대 의원 당선 공약 vs 실제 발의 의안 이행률.
 * 카테고리 클릭 → 온톨로지 관계 그래프 (공약 → 발의·가결 의안 → 대표 의원) + AI 인사이트 specific.
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

interface PromiseItem {
  promise_id: string;
  category: string;
  promised: number;
  filed: number;
  passed: number;
}

const PROMISES: PromiseItem[] = [
  { promise_id: 'R-AI',  category: 'AI·디지털 전환',  promised: 12, filed: 8,  passed: 2 },
  { promise_id: 'R-HSE', category: '청년 주거',       promised: 15, filed: 12, passed: 3 },
  { promise_id: 'R-WLF', category: '사회복지',        promised: 18, filed: 15, passed: 5 },
  { promise_id: 'R-ENV', category: '환경·기후',       promised: 10, filed: 7,  passed: 2 },
  { promise_id: 'R-ECN', category: '경제·재정',       promised: 14, filed: 11, passed: 2 },
  { promise_id: 'R-EDU', category: '교육',            promised: 9,  filed: 6,  passed: 3 },
  { promise_id: 'R-PVY', category: '개인정보·보안',   promised: 7,  filed: 5,  passed: 2 },
  { promise_id: 'R-FOR', category: '외교·안보',       promised: 6,  filed: 3,  passed: 1 },
];

const CATEGORY_BILLS: Record<string, { filed: string[]; passed: string[] }> = {
  'R-AI':  { filed: ['AI 기본법', 'AI 윤리 가이드라인법', '디지털플랫폼 공정거래법'], passed: ['AI 학습데이터 보호법', '알고리즘 투명성법'] },
  'R-HSE': { filed: ['청년 임대료 보조법', '전세사기 방지법', '주거 안정 특별법'],   passed: ['청년 주거 지원법', '주거취약계층 보호법', '공공임대 확대법'] },
  'R-WLF': { filed: ['노인 의료 보장법', '요양보호사 처우법', '치매 국가책임법'],   passed: ['기초연금 인상법', '의료급여 확대법', '아동수당 확대법', '돌봄 통합지원법', '장애인 자립지원법'] },
  'R-ENV': { filed: ['재생에너지 가속법', '탄소중립 산업법', '에너지 전환법'],       passed: ['풍력·태양광 확대법', '대기환경보전법 개정안'] },
  'R-ECN': { filed: ['세법 개정안', '소상공인 임대료법', '예산결산 특별법'],         passed: ['금융소비자보호법', '중소기업 지원법'] },
  'R-EDU': { filed: ['사교육비 경감법', '공교육 정상화법', '대학 등록금 안정법'],   passed: ['초중등교육법 개정', '학교폭력 예방법', '학생인권법'] },
  'R-PVY': { filed: ['개인정보 보호 강화법', '디지털 인격권법', '사이버 안보법'],   passed: ['데이터 거버넌스법', '잊혀질 권리법'] },
  'R-FOR': { filed: ['해외동포 지원법', '외교통상 기본법'],                          passed: ['남북교류협력법'] },
};

const CATEGORY_PROPOSERS: Record<string, string[]> = {
  'R-AI':  ['고민정', '윤영찬'],
  'R-HSE': ['김민석', '박영선'],
  'R-WLF': ['김태년', '서영교'],
  'R-ENV': ['우원식', '정청래'],
  'R-ECN': ['민형배', '이학영'],
  'R-EDU': ['도종환', '김영호'],
  'R-PVY': ['고민정', '윤영찬'],
  'R-FOR': ['김도읍', '조정훈'],
};

function buildPromiseSubgraph(p: PromiseItem, memberByName: Map<string, MemberLite>): Subgraph {
  const promiseId = `Promise:${p.promise_id}`;
  const billsMeta = CATEGORY_BILLS[p.promise_id] ?? { filed: [], passed: [] };
  const filedIds = billsMeta.filed.map((_, i) => `Bill:${p.promise_id}-F${i + 1}`);
  const passedIds = billsMeta.passed.map((_, i) => `Bill:${p.promise_id}-P${i + 1}`);

  const proposers = CATEGORY_PROPOSERS[p.promise_id] ?? [];
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
    { id: promiseId, label: 'Topic',
      data: { name: `공약 — ${p.category}`, promised: p.promised, filed: p.filed, passed: p.passed } },
    ...filedIds.map((id, i) => ({ id, label: 'Bill', data: { name: billsMeta.filed[i] } })),
    ...passedIds.map((id, i) => ({ id, label: 'Bill', data: { name: billsMeta.passed[i] + ' (가결)' } })),
    ...personNodes,
  ];

  const edges = [
    ...filedIds.map((bid) => ({ source: promiseId, target: bid, type: 'REFERENCES' })),
    ...passedIds.map((bid) => ({ source: promiseId, target: bid, type: 'ABOUT' })),
    // 첫 발의자 + 가결 의안 매핑
    ...personNodes.flatMap((pn, pi) =>
      [...filedIds.slice(0, 2), ...passedIds.slice(0, 1)].map((bid) => ({
        source: pn.id, target: bid, type: pi === 0 ? 'PROPOSED' : 'CO_PROPOSED',
      })),
    ),
  ];

  return { root_id: promiseId, nodes, edges };
}

export default function PromiseTrackerPage() {
  const [sortKey, setSortKey] = useState<'category' | 'rate'>('rate');
  const [selected, setSelected] = useState<PromiseItem | null>(null);
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

  const enriched = PROMISES.map((p) => ({
    ...p,
    file_rate: p.promised > 0 ? p.filed / p.promised : 0,
    pass_rate: p.promised > 0 ? p.passed / p.promised : 0,
  }));
  const sorted = sortKey === 'rate'
    ? [...enriched].sort((a, b) => b.file_rate - a.file_rate)
    : [...enriched].sort((a, b) => a.category.localeCompare(b.category));

  const totals = {
    promised: PROMISES.reduce((s, p) => s + p.promised, 0),
    filed: PROMISES.reduce((s, p) => s + p.filed, 0),
    passed: PROMISES.reduce((s, p) => s + p.passed, 0),
  };
  const overall_file_rate = totals.filed / totals.promised;

  const subgraph = useMemo(
    () => (selected ? buildPromiseSubgraph(selected, memberByName) : null),
    [selected, memberByName],
  );

  const insightContext = useMemo(() => {
    if (!selected) return null;
    const billsMeta = CATEGORY_BILLS[selected.promise_id] ?? { filed: [], passed: [] };
    return {
      promise_id: selected.promise_id,
      promise_category: selected.category,
      promised: selected.promised,
      filed: selected.filed,
      passed: selected.passed,
      file_rate: ((selected.filed / selected.promised) * 100).toFixed(0),
      pass_rate: ((selected.passed / selected.promised) * 100).toFixed(0),
      filed_bills: billsMeta.filed,
      passed_bills: billsMeta.passed,
      proposers: CATEGORY_PROPOSERS[selected.promise_id] ?? [],
    };
  }, [selected]);

  return (
    <div>
      <ScenarioHero code="R" subtitle="신규 ★" />

      {/* 전체 통계 */}
      <section className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="총 공약" value={`${totals.promised}건`} color="text-slate-300" />
        <Stat label="발의 (이행)" value={`${totals.filed}건`} color="text-blue-300" />
        <Stat label="가결" value={`${totals.passed}건`} color="text-emerald-300" />
        <Stat label="전체 이행률" value={`${(overall_file_rate * 100).toFixed(0)}%`} color="text-amber-300" big />
      </section>

      {/* sort toggle */}
      <div className="mb-3 flex gap-2 text-xs">
        <button
          onClick={() => setSortKey('rate')}
          className={`px-3 py-1 rounded ${sortKey === 'rate' ? 'bg-blue-500/20 border border-blue-500/50 text-blue-200' : 'bg-slate-800 border border-slate-700 text-slate-400'}`}
        >이행률순</button>
        <button
          onClick={() => setSortKey('category')}
          className={`px-3 py-1 rounded ${sortKey === 'category' ? 'bg-blue-500/20 border border-blue-500/50 text-blue-200' : 'bg-slate-800 border border-slate-700 text-slate-400'}`}
        >카테고리순</button>
        <span className="ml-2 text-slate-500 self-center">— 카테고리 클릭으로 온톨로지 관계 그래프 + AI 인사이트 표시</span>
      </div>

      {/* 카테고리별 이행률 bar — 클릭으로 select */}
      <section className="mb-6 space-y-2">
        {sorted.map((p) => {
          const isSelected = selected?.promise_id === p.promise_id;
          return (
            <button
              key={p.promise_id}
              type="button"
              onClick={() => setSelected(p)}
              className={
                'w-full text-left border rounded-lg p-3 transition-colors ' +
                (isSelected
                  ? 'border-blue-500 bg-blue-500/15'
                  : 'border-slate-800 bg-slate-900/40 hover:border-slate-600')
              }
            >
              <div className="flex items-baseline justify-between mb-1.5">
                <div className="text-sm font-semibold text-white">{p.category}</div>
                <div className="text-[11px] text-slate-400 font-mono">
                  공약 <strong className="text-slate-200">{p.promised}</strong> · 발의 <strong className="text-blue-300">{p.filed}</strong> · 가결 <strong className="text-emerald-300">{p.passed}</strong>
                </div>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden relative">
                <div
                  className="h-2 bg-gradient-to-r from-blue-500 to-amber-400 absolute left-0 top-0"
                  style={{ width: `${p.file_rate * 100}%` }}
                />
                <div
                  className="h-2 bg-emerald-500 absolute left-0 top-0"
                  style={{ width: `${p.pass_rate * 100}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[10px]">
                <span className="text-amber-300">이행률 {(p.file_rate * 100).toFixed(0)}%</span>
                <span className="text-emerald-300">가결률 {(p.pass_rate * 100).toFixed(0)}%</span>
              </div>
            </button>
          );
        })}
      </section>

      {/* 온톨로지 관계 그래프 — selected promise */}
      {selected && subgraph && (
        <section className="mb-6">
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            🕸️ 공약 이행 온톨로지 관계 그래프 — <span className="text-white">{selected.category}</span>
            <span className="ml-2 text-[10px] text-slate-500">
              발의 의안 {CATEGORY_BILLS[selected.promise_id]?.filed.length ?? 0}건 + 가결 의안 {CATEGORY_BILLS[selected.promise_id]?.passed.length ?? 0}건 + 대표 발의 의원
            </span>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40">
            <CytoscapeView subgraph={subgraph} height={460} expandable={false} />
          </div>
        </section>
      )}

      {insightContext ? (
        <AIInsightPanel scenarioCode="R" context={insightContext} autoGenerate />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          공약 카테고리를 클릭하면 온톨로지 관계 그래프 + AI 인사이트가 표시됩니다.
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color, big = false }: { label: string; value: string; color: string; big?: boolean }) {
  return (
    <div className={`rounded-lg border p-3 ${big ? 'border-amber-500/30 bg-amber-500/10' : 'border-slate-800 bg-slate-900/40'}`}>
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{label}</div>
      <div className={`${big ? 'text-2xl' : 'text-lg'} font-bold ${color}`}>{value}</div>
    </div>
  );
}
