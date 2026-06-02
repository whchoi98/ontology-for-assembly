'use client';

/**
 * 시나리오 U — 의원 영향력 ranking (Phase 4f, REAL Cypher query).
 *
 * CO_PROPOSED_WITH cohort 가중치 기반 의원 영향력 score.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { CytoscapeView } from '../../components/CytoscapeView';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import type { Subgraph } from '../../lib/api-client';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface InfluenceMember {
  assembly_id: string;
  name: string;
  party: string;
  district: string;
  proposed_count: number;
  co_proposed_count: number;
  cohort_weight_sum: number;
  voted_count: number;
  influence_score: number;
}

interface Response {
  members: InfluenceMember[];
  total_members: number;
  source: string;
}

export default function InfluenceRankPage() {
  const [limit, setLimit] = useState(20);
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}/api/insights/influence-rank?limit=${limit}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [limit]);

  if (error) return <div className="text-red-300 p-4">Error: {error}</div>;
  if (!data) return <div className="text-slate-400 p-4">Loading…</div>;

  return (
    <div>
      <header className="mb-6 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-xs px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-400/40 text-emerald-300">
            시나리오 U · REAL
          </span>
          <span className="text-xs text-slate-500">· Phase 4f</span>
        </div>
        <h1 className="text-2xl font-bold text-white mb-1.5">의원 영향력 (Influence Rank)</h1>
        <p className="text-sm text-slate-300">
          CO_PROPOSED_WITH 19,191 cohort 가중치 + PROPOSED·CO_PROPOSED count 기반 의원 영향력 ranking.
        </p>
        <div className="mt-3 bg-emerald-500/15 border border-emerald-400/40 rounded-md px-3 py-2 text-emerald-100 text-[11px]">
          🟢 REAL · 공동발의 네트워크 *degree centrality* 분석 — 22대 임기 의원 286명 + 발의 의안 2,098건 그래프.
        </div>
      </header>

      <div className="mb-4 flex items-center gap-2 text-xs">
        <span className="text-slate-400">Top:</span>
        {[10, 20, 50].map((n) => (
          <button
            key={n}
            onClick={() => setLimit(n)}
            className={
              'px-3 py-1 rounded ' +
              (limit === n
                ? 'bg-emerald-500/20 border border-emerald-500/50 text-emerald-200'
                : 'bg-slate-800 border border-slate-700 text-slate-400 hover:text-white')
            }
          >
            {n}
          </button>
        ))}
        <span className="text-slate-500 ml-2">/ 전체 {data.total_members}명 candidate</span>
      </div>

      <section className="mb-6 space-y-2">
        {data.members.map((m, i) => (
          <div key={m.assembly_id} className="border border-slate-800 bg-slate-900/40 rounded-lg p-3">
            <div className="flex items-center gap-3">
              <span className="text-amber-300 font-mono font-bold w-8 text-center">#{i + 1}</span>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`https://www.assembly.go.kr/static/portal/img/openassm/${m.assembly_id}.jpg`}
                alt={m.name}
                className="w-10 h-10 rounded-full object-cover bg-slate-800"
                onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
              />
              <div className="flex-1">
                <div className="text-sm font-bold text-white">{m.name}</div>
                <div className="text-[10px] text-slate-400">{m.party} · {m.district}</div>
              </div>
              <div className="flex items-center gap-3 text-[11px] text-slate-300 font-mono">
                <span>발의 <strong className="text-blue-300">{m.proposed_count}</strong></span>
                <span>공동 <strong className="text-cyan-300">{m.co_proposed_count}</strong></span>
                <span>cohort <strong className="text-amber-300">{m.cohort_weight_sum}</strong></span>
              </div>
              <div className="ml-2 text-right">
                <div className="text-emerald-300 font-bold text-lg">{(m.influence_score * 100).toFixed(0)}</div>
                <div className="text-[9px] text-slate-500">/ 100</div>
              </div>
            </div>
            <div className="mt-2 h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-1.5 bg-gradient-to-r from-emerald-500 to-amber-400"
                style={{ width: `${m.influence_score * 100}%` }}
              />
            </div>
          </div>
        ))}
      </section>

      <InfluenceGraphAndInsight members={data.members} />

      <section className="border border-amber-500/30 bg-amber-500/10 rounded-lg p-4">
        <h3 className="text-sm font-bold text-amber-200 mb-2">📊 영향력 score 공식</h3>
        <p className="text-xs text-amber-100">
          <strong>score</strong> = 0.6 × (cohort_weight / max_cohort) + 0.25 × (proposed / 30) + 0.15 × (co_proposed / 200)
        </p>
        <ul className="text-xs text-amber-100 space-y-1 mt-2 list-disc pl-5">
          <li><strong>cohort_weight</strong>: 다른 의원들과의 공동발의 cohort 가중치 합 (네트워크 hub strength)</li>
          <li><strong>proposed</strong>: 대표 발의한 의안 수 (의제 주도성)</li>
          <li><strong>co_proposed</strong>: 공동 발의 참여 수 (협력 활성도)</li>
          <li>Real Cypher 2-phase query: top cohort candidates → meta + counts batch fetch</li>
        </ul>
      </section>
    </div>
  );
}

function InfluenceGraphAndInsight({ members }: { members: InfluenceMember[] }) {
  const subgraph = useMemo<Subgraph>(() => {
    const top = members.slice(0, 8);
    const nodes = top.map((m) => ({
      id: `Person:${m.assembly_id}`, label: 'Person',
      data: {
        name: m.name, party: m.party, district: m.district,
        profile_image_url: `https://www.assembly.go.kr/static/portal/img/openassm/${m.assembly_id}.jpg`,
        influence: m.influence_score,
      },
    }));
    const hubId = 'Topic:influence';
    nodes.push({
      id: hubId, label: 'Topic',
      data: { name: '영향력 hub', party: '', district: '', profile_image_url: '', influence: 0 },
    });
    const edges = top.map((m) => ({ source: `Person:${m.assembly_id}`, target: hubId, type: 'CO_PROPOSED_WITH' }));
    return { root_id: hubId, nodes, edges };
  }, [members]);

  const insightCtx = useMemo(() => ({
    person_id: members[0]?.assembly_id ?? 'influence_top',
    top_member_names: members.slice(0, 10).map((m) => m.name),
    top_member_scores: members.slice(0, 10).map((m) => m.influence_score),
    top_member_parties: Array.from(new Set(members.slice(0, 10).map((m) => m.party))).slice(0, 4),
    rank1_name: members[0]?.name ?? '',
    rank1_party: members[0]?.party ?? '',
    rank1_proposed: members[0]?.proposed_count ?? 0,
    rank1_cohort_weight: members[0]?.cohort_weight_sum ?? 0,
  }), [members]);

  return (
    <>
      <section className="mb-6">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
          🕸️ 온톨로지 관계 그래프 — top 8 의원 영향력 cohort
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40">
          <CytoscapeView subgraph={subgraph} height={420} expandable={false} />
        </div>
      </section>

      <div className="mb-6">
        <AIInsightPanel scenarioCode="U" autoGenerate context={insightCtx} />
      </div>
    </>
  );
}
