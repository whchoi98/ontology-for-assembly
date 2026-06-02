'use client';

/**
 * 시나리오 K - 표결 이상치 (PDF 시그니처 ★).
 *
 * 당론 이탈 · 박빙 표결 · 정파 초월 협력 패턴 - 3 유형 필터 + 상세 패널.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { outlierApi, type OutlierEntry, type OutlierListResponse } from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';
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

function buildOutlierSubgraph(
  o: OutlierEntry,
  memberById: Map<string, MemberLite>,
  memberByName: Map<string, MemberLite>,
): Subgraph {
  const billId = `Bill:${o.bill_id}`;
  const voteId = `Vote:${o.vote_id}`;
  const personNodes = o.deviating_persons.slice(0, 6).map((p) => {
    // outlier fixture의 person_id ↔ name이 mismatch될 수 있음 — *name 우선 매칭*
    const m = memberByName.get(p.name) || memberById.get(p.person_id);
    // node id도 *real assembly_id 우선* (회귀 매칭 안정성)
    const realId = m?.assembly_id ?? p.person_id;
    return {
      id: `Person:${realId}`,
      label: 'Person' as const,
      data: {
        name: p.name, party: p.party, choice: p.choice,
        district: m?.district ?? '',
        ...(m?.profile_image_url ? { profile_image_url: m.profile_image_url } : {}),
      },
    };
  });
  const nodes = [
    { id: billId, label: 'Bill', data: { name: o.bill_title } },
    { id: voteId, label: 'Vote', data: { name: `${o.vote_date} 표결 (deviation ${o.deviation_score.toFixed(2)})` } },
    ...personNodes,
  ];
  const edges = [
    { source: voteId, target: billId, type: 'VOTE_ON' },
    ...personNodes.map((pn) => ({ source: pn.id, target: voteId, type: 'VOTED' })),
  ];
  return { root_id: billId, nodes, edges };
}

type FilterType = '' | 'party_line_break' | 'swing_vote' | 'cross_party';

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  party_line_break: { label: '당론 이탈', color: 'bg-red-500/20 border border-red-400/40 text-red-200' },
  swing_vote: { label: '박빙', color: 'bg-amber-500/15 text-amber-300' },
  cross_party: { label: '정파 초월 협력', color: 'bg-emerald-500/20 border border-emerald-400/40 text-emerald-200' },
};


export default function OutlierPage() {
  const [data, setData] = useState<OutlierListResponse | null>(null);
  const [selected, setSelected] = useState<OutlierEntry | null>(null);
  const [filter, setFilter] = useState<FilterType>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (currentFilter: FilterType) => {
    setLoading(true);
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const response = await outlierApi.list({
        outlierType: currentFilter || undefined,
        personaId,
      });
      setData(response);
      // 첫 entry 자동 선택
      if (response.outliers.length > 0 && !selected) {
        setSelected(response.outliers[0]);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    void load(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const [members, setMembers] = useState<MemberLite[]>([]);
  useEffect(() => {
    fetch(`${BASE}/api/members`).then((r) => r.json()).then((d) => setMembers(d.members ?? [])).catch(() => {});
  }, []);
  const memberById = useMemo(() => {
    const m = new Map<string, MemberLite>();
    for (const x of members) m.set(x.assembly_id, x);
    return m;
  }, [members]);
  const memberByName = useMemo(() => {
    const m = new Map<string, MemberLite>();
    for (const x of members) m.set(x.name, x);
    return m;
  }, [members]);
  const subgraph = useMemo(
    () => (selected ? buildOutlierSubgraph(selected, memberById, memberByName) : null),
    [selected, memberById, memberByName],
  );

  return (
    <div>
      <ScenarioHero code="K" subtitle="PDF 시그니처 ★" />
      {data?.persona_note && (
        <div className="mb-4 text-xs text-amber-300/80 bg-amber-500/5 border border-amber-500/20 rounded px-3 py-2">
          페르소나 컨텍스트: {data.persona_note}
        </div>
      )}

      {/* 유형 필터 */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {[
          { id: '' as FilterType, label: '전체' },
          { id: 'party_line_break' as FilterType, label: '당론 이탈' },
          { id: 'swing_vote' as FilterType, label: '박빙' },
          { id: 'cross_party' as FilterType, label: '정파 초월 협력' },
        ].map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={
              'text-xs px-3 py-1.5 rounded-md border ' +
              (filter === f.id
                ? 'border-blue-500 bg-blue-500/15 text-blue-300 font-medium'
                : 'border-slate-800 bg-slate-900/40 text-slate-200 hover:bg-slate-800/40')
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}
      {loading && <p className="text-slate-400">로딩 중…</p>}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 리스트 */}
          <div className="space-y-2">
            {data.outliers.map((o) => (
              <OutlierCard
                key={o.outlier_id}
                outlier={o}
                active={selected?.outlier_id === o.outlier_id}
                onClick={() => setSelected(o)}
              />
            ))}
            {data.outliers.length === 0 && (
              <p className="text-sm text-slate-400 py-8 text-center">이상치 없음</p>
            )}
          </div>

          {/* 상세 패널 */}
          <div className="lg:sticky lg:top-4 self-start">
            {selected ? <OutlierDetail entry={selected} /> : (
              <p className="text-sm text-slate-500 italic p-4 text-center border border-dashed border-slate-800 rounded-md">
                왼쪽에서 이상치를 선택하세요.
              </p>
            )}
          </div>
        </div>
      )}
      {/* 온톨로지 관계 그래프 — selected outlier */}
      {selected && subgraph && (
        <section className="mt-6 mb-4">
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            🕸️ 온톨로지 관계 그래프 — <span className="text-white">{selected.bill_title}</span>
            <span className="ml-2 text-[10px] text-slate-500">
              표결 · 이탈 의원 {selected.deviating_persons.length}명 · deviation {selected.deviation_score.toFixed(2)}
            </span>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40">
            <CytoscapeView subgraph={subgraph} height={400} expandable={false} />
          </div>
        </section>
      )}

      {/* 선택 outlier를 context로 — 항목 변경 시 AI 인사이트 자동 재호출 */}
      <AIInsightPanel scenarioCode="K" context={selected} autoGenerate />
    </div>
  );
}


function OutlierCard({
  outlier,
  active,
  onClick,
}: {
  outlier: OutlierEntry;
  active: boolean;
  onClick: () => void;
}) {
  const typeMeta = TYPE_LABELS[outlier.outlier_type] ?? { label: outlier.outlier_type, color: 'bg-slate-800 text-slate-200' };
  return (
    <button
      onClick={onClick}
      className={
        'w-full text-left border rounded-md p-3 transition ' +
        (active
          ? 'border-blue-400 bg-blue-500/15'
          : 'border-slate-800 bg-slate-900/40 hover:border-blue-300')
      }
    >
      <div className="flex items-center justify-between mb-1">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeMeta.color}`}>
          {typeMeta.label}
        </span>
        <span className="text-xs text-slate-400 font-mono">
          dev {outlier.deviation_score.toFixed(2)}
        </span>
      </div>
      <h3 className="font-semibold text-white text-sm mb-0.5">
        {outlier.bill_title}
      </h3>
      <div className="text-xs text-slate-400">{outlier.vote_date} · {outlier.label}</div>
    </button>
  );
}


function OutlierDetail({ entry }: { entry: OutlierEntry }) {
  const typeMeta = TYPE_LABELS[entry.outlier_type] ?? { label: entry.outlier_type, color: 'bg-slate-800' };
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40">
      <header className="px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeMeta.color}`}>
            {typeMeta.label}
          </span>
          <span className="text-xs text-slate-400 font-mono">
            deviation_score {entry.deviation_score.toFixed(2)}
          </span>
        </div>
        <h2 className="font-bold text-white">{entry.bill_title}</h2>
        <div className="text-xs text-slate-400 mt-1">
          {entry.vote_date} · vote_id: <span className="font-mono">{entry.vote_id.slice(0, 30)}…</span>
        </div>
      </header>

      <div className="p-4 space-y-4 text-sm">
        <section>
          <h3 className="text-xs uppercase text-slate-400 mb-1">설명</h3>
          <p className="text-slate-100 leading-relaxed">{entry.description}</p>
        </section>

        <section className="grid grid-cols-2 gap-3 text-xs">
          <div className="border border-slate-800 rounded p-2 bg-slate-800/40">
            <div className="text-slate-400 uppercase text-[10px] mb-1">예상 패턴</div>
            <div className="text-slate-100">{entry.expected_pattern}</div>
          </div>
          <div className="border border-slate-800 rounded p-2 bg-slate-800/40">
            <div className="text-slate-400 uppercase text-[10px] mb-1">실제 패턴</div>
            <div className="text-slate-100">{entry.actual_pattern}</div>
          </div>
        </section>

        {entry.deviating_persons.length > 0 && (
          <section>
            <h3 className="text-xs uppercase text-slate-400 mb-2">
              이탈 의원 ({entry.deviating_persons.length}명)
            </h3>
            <ul className="space-y-1">
              {entry.deviating_persons.map((p) => (
                <li key={p.person_id} className="flex items-start gap-2 text-xs">
                  <span className="font-mono text-slate-500 shrink-0">{p.person_id}</span>
                  <span className="font-semibold text-slate-100">{p.name}</span>
                  <span className="text-slate-400">{p.party}</span>
                  <span className="text-slate-400">→ <strong>{p.choice}</strong></span>
                  {p.reason_hint && (
                    <span className="text-slate-400 italic">({p.reason_hint})</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
          <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">
            AI 패턴 라벨
          </div>
          <p className="text-amber-100 text-xs leading-relaxed">{entry.ai_label}</p>
        </section>
      </div>
    </section>
  );
}
