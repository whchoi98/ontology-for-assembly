'use client';

/**
 * 시나리오 P — 시민 청원 → 입법 매핑.
 *
 * 합성 청원 데이터 → 발의 의안 매칭률 + 이행 lifecycle.
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

interface Petition {
  petition_id: string;
  title: string;
  category: string;
  signatures: number;
  matched_bills: number;
  lifecycle: 'received' | 'in_committee' | 'in_plenary' | 'passed';
}

const PETITIONS: Petition[] = [
  { petition_id: 'P22-001', title: '청년 임대료 보조 확대', category: '주거', signatures: 12450, matched_bills: 3, lifecycle: 'in_plenary' },
  { petition_id: 'P22-002', title: 'AI 윤리 가이드라인 강화', category: 'AI', signatures: 8920, matched_bills: 2, lifecycle: 'in_committee' },
  { petition_id: 'P22-003', title: '재생에너지 전환 가속', category: '환경', signatures: 18230, matched_bills: 4, lifecycle: 'in_plenary' },
  { petition_id: 'P22-004', title: '노인 의료 보장 강화', category: '복지', signatures: 22100, matched_bills: 5, lifecycle: 'passed' },
  { petition_id: 'P22-005', title: '사교육비 경감 정책', category: '교육', signatures: 9870, matched_bills: 2, lifecycle: 'in_committee' },
  { petition_id: 'P22-006', title: '소상공인 임대료 안정화', category: '경제', signatures: 14530, matched_bills: 3, lifecycle: 'in_plenary' },
  { petition_id: 'P22-007', title: '개인정보 침해 처벌 강화', category: '개인정보', signatures: 6780, matched_bills: 2, lifecycle: 'received' },
];

const LIFECYCLE_LABEL: Record<Petition['lifecycle'], { label: string; color: string; step: number }> = {
  received:     { label: '접수',       color: 'bg-slate-500',  step: 1 },
  in_committee: { label: '상임위 심사', color: 'bg-blue-500',   step: 2 },
  in_plenary:   { label: '본회의',     color: 'bg-amber-500',  step: 3 },
  passed:       { label: '가결',       color: 'bg-emerald-500', step: 4 },
};

// 각 청원의 매칭 의안 + 발의 의원 + 카테고리 토픽 (합성 mindmap source)
const PETITION_GRAPH: Record<string, { bills: string[]; proposers: string[]; topic: string }> = {
  'P22-001': { bills: ['청년 임대료 보조법', '주거 안정 특별법', '전세사기 방지법'],         proposers: ['김민석', '박영선'],   topic: '주거 안정' },
  'P22-002': { bills: ['AI 윤리 기본법', '알고리즘 투명성법'],                                proposers: ['고민정', '윤영찬'],   topic: 'AI 거버넌스' },
  'P22-003': { bills: ['재생에너지 가속법', '탄소중립 산업법', '에너지 전환법', '풍력·태양광 확대법'], proposers: ['우원식', '김태년', '정청래'], topic: '기후·환경' },
  'P22-004': { bills: ['노인 의료 보장법', '요양보호사 처우법', '치매 국가책임법', '의료급여 확대법', '간병비 지원법'], proposers: ['김태년', '서영교', '정청래'], topic: '복지·의료' },
  'P22-005': { bills: ['사교육비 경감법', '공교육 정상화법'],                                  proposers: ['도종환', '김영호'],   topic: '교육' },
  'P22-006': { bills: ['소상공인 임대료법', '코로나19 손실보상법', '상가건물 임대차법'],       proposers: ['민형배', '이학영'],   topic: '경제·소상공인' },
  'P22-007': { bills: ['개인정보 보호 강화법', '디지털 인격권법'],                              proposers: ['고민정', '윤영찬'],   topic: '개인정보' },
};

function buildPetitionSubgraph(p: Petition, memberByName: Map<string, MemberLite>): Subgraph {
  const g = PETITION_GRAPH[p.petition_id];
  if (!g) return { root_id: p.petition_id, nodes: [], edges: [] };

  const rootId = `Petition:${p.petition_id}`;
  const topicId = `Topic:${g.topic}`;
  const billIds = g.bills.map((b, i) => `Bill:${p.petition_id}-B${i + 1}`);

  // 발의 의원: members 매칭하여 profile_image_url + party + district 첨부
  const personEntries = g.proposers.map((name) => {
    const m = memberByName.get(name);
    const id = `Person:${m?.assembly_id ?? name}`;
    return {
      id,
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
    { id: rootId,  label: 'Petition', data: { name: `청원 — ${p.title}`, signatures: p.signatures, lifecycle: p.lifecycle } },
    { id: topicId, label: 'Topic',    data: { name: g.topic } },
    ...billIds.map((id, i) => ({ id, label: 'Bill', data: { name: g.bills[i] } })),
    ...personEntries,
  ];

  const edges = [
    { source: rootId,  target: topicId, type: 'ABOUT' },
    ...billIds.map((bid) => ({ source: rootId, target: bid, type: 'REFERENCES' })),
    // 첫 두 의안의 발의 의원 연결 (시각 단순화)
    ...personEntries.flatMap((pe, pi) =>
      billIds.slice(0, 2).map((bid) => ({ source: pe.id, target: bid, type: pi === 0 ? 'PROPOSED' : 'CO_PROPOSED' })),
    ),
  ];

  return { root_id: rootId, nodes, edges };
}

export default function PetitionMapPage() {
  const [selected, setSelected] = useState<Petition | null>(null);
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

  const stats = useMemo(() => ({
    total_petitions: PETITIONS.length,
    total_signatures: PETITIONS.reduce((s, p) => s + p.signatures, 0),
    avg_match_rate: PETITIONS.reduce((s, p) => s + (p.matched_bills > 0 ? 1 : 0), 0) / PETITIONS.length,
    passed_count: PETITIONS.filter((p) => p.lifecycle === 'passed').length,
  }), []);

  // selected가 있을 때만 flat context — petition_id를 stable identifier로 AIInsightPanel useMemo가 인식
  const insightContext = useMemo(() => {
    if (!selected) return null;
    const g = PETITION_GRAPH[selected.petition_id];
    return {
      petition_id: selected.petition_id,
      petition_title: selected.title,
      category: selected.category,
      signatures: selected.signatures,
      matched_bills: selected.matched_bills,
      lifecycle: selected.lifecycle,
      lifecycle_label: LIFECYCLE_LABEL[selected.lifecycle].label,
      matched_bill_titles: g?.bills ?? [],
      proposers: g?.proposers ?? [],
      topic: g?.topic ?? selected.category,
      stats,
    };
  }, [selected, stats]);

  const subgraph = useMemo(
    () => (selected ? buildPetitionSubgraph(selected, memberByName) : null),
    [selected, memberByName],
  );

  return (
    <div>
      <ScenarioHero code="P" subtitle="신규 ★" />

      {/* 통계 카드 */}
      <section className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="청원 (분기)" value={`${stats.total_petitions}건`} color="text-blue-300" />
        <Stat label="누적 서명" value={stats.total_signatures.toLocaleString()} color="text-amber-300" />
        <Stat label="입법 매칭률" value={`${(stats.avg_match_rate * 100).toFixed(0)}%`} color="text-emerald-300" />
        <Stat label="가결 완료" value={`${stats.passed_count}건`} color="text-cyan-300" />
      </section>

      {/* 청원 list + lifecycle */}
      <section className="mb-6">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">청원 → 입법 lifecycle</div>
        <div className="space-y-2">
          {PETITIONS.map((p) => {
            const lc = LIFECYCLE_LABEL[p.lifecycle];
            return (
              <button
                key={p.petition_id}
                onClick={() => setSelected(p)}
                className={
                  'w-full text-left border rounded-lg p-3 transition-colors ' +
                  (selected?.petition_id === p.petition_id
                    ? 'border-blue-500 bg-blue-500/15'
                    : 'border-slate-800 bg-slate-900/40 hover:border-slate-600')
                }
              >
                <div className="flex items-baseline justify-between mb-1.5">
                  <div className="text-sm font-semibold text-white">{p.title}</div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded text-white ${lc.color}`}>{lc.label}</span>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-slate-400">
                  <span className="text-cyan-300">{p.category}</span>
                  <span>서명 {p.signatures.toLocaleString()}</span>
                  <span className="text-emerald-300">매칭 의안 {p.matched_bills}건</span>
                </div>
                {/* lifecycle progress bar */}
                <div className="mt-2 flex gap-1">
                  {[1, 2, 3, 4].map((step) => (
                    <div key={step} className={`flex-1 h-1 rounded ${step <= lc.step ? lc.color : 'bg-slate-800'}`} />
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 선택 청원의 연관 관계 mindmap */}
      {selected && subgraph && (
        <section className="mb-6">
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            🕸️ 연관 관계 — <span className="text-white">{selected.title}</span>
            <span className="ml-2 text-[10px] text-slate-500">
              청원 → {PETITION_GRAPH[selected.petition_id]?.topic} → {selected.matched_bills}건 매칭 의안 → 발의 의원
            </span>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40">
            <CytoscapeView subgraph={subgraph} height={420} expandable={false} />
          </div>
        </section>
      )}

      {/* AI 인사이트 — selected 있을 때만 표시 + autoGenerate */}
      {insightContext ? (
        <AIInsightPanel scenarioCode="P" context={insightContext} autoGenerate />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          청원을 선택하면 AI 인사이트 + 연관 관계 mindmap이 표시됩니다.
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  );
}
