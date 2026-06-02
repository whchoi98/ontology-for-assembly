'use client';

/**
 * 시나리오 T — 정당 응집도 (Phase 4f, REAL Neptune query).
 *
 * 22대 8 정당 × 표결 majority 일치율 ranking.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { CytoscapeView } from '../../components/CytoscapeView';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import type { Subgraph } from '../../lib/api-client';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface PartyCohesion {
  party: string;
  member_count: number;
  total_votes: number;
  majority_alignment_pct: number;
  cohesion_score: number;
}

interface Response {
  parties: PartyCohesion[];
  overall_cohesion: number;
  source: string;
}

export default function PartyCohesionPage() {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}/api/insights/party-cohesion`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="text-red-300 p-4">Error: {error}</div>;
  if (!data) return <div className="text-slate-400 p-4">Loading…</div>;

  return (
    <div>
      <header className="mb-6 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-xs px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-400/40 text-emerald-300">
            시나리오 T · REAL
          </span>
          <span className="text-xs text-slate-500">· Phase 4f</span>
        </div>
        <h1 className="text-2xl font-bold text-white mb-1.5">정당 응집도 (Party Cohesion)</h1>
        <p className="text-sm text-slate-300">
          22대 국회 8 정당 × 표결 majority 일치율 ranking — real VOTED 28,528 엣지 + BELONGS_TO 분석 (active 표결만).
        </p>
        <div className="mt-3 bg-emerald-500/15 border border-emerald-400/40 rounded-md px-3 py-2 text-emerald-100 text-[11px]">
          🟢 REAL · Neptune Cypher query — 22대 임기 (2024-05 ~ 2026-05) 진짜 표결 데이터.
        </div>
      </header>

      <section className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="border border-emerald-400/40 bg-emerald-500/10 p-4 rounded-lg">
          <div className="text-[10px] uppercase tracking-wider text-emerald-300 mb-1">전체 응집도</div>
          <div className="text-3xl font-bold text-emerald-200">{(data.overall_cohesion * 100).toFixed(1)}%</div>
          <div className="text-[10px] text-emerald-300/70 mt-1">8 정당 평균</div>
        </div>
        <div className="border border-slate-800 bg-slate-900/40 p-4 rounded-lg">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">분석 정당</div>
          <div className="text-3xl font-bold text-white">{data.parties.length}</div>
          <div className="text-[10px] text-slate-500 mt-1">개 정당</div>
        </div>
        <div className="border border-slate-800 bg-slate-900/40 p-4 rounded-lg">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">분석 의원 수</div>
          <div className="text-3xl font-bold text-white">
            {data.parties.reduce((s, p) => s + p.member_count, 0)}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">명</div>
        </div>
      </section>

      <section className="mb-6">
        <h2 className="text-sm font-bold text-white mb-3">정당별 응집도 ranking</h2>
        <div className="space-y-2">
          {data.parties.map((p, i) => (
            <div key={p.party} className="border border-slate-800 bg-slate-900/40 rounded-lg p-4">
              <div className="flex items-baseline justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="text-amber-300 font-mono font-bold text-lg">#{i + 1}</span>
                  <span className="text-white font-bold">{p.party}</span>
                  <span className="text-[11px] text-slate-400">의원 {p.member_count}명</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-slate-400">표결 {p.total_votes.toLocaleString()}건</span>
                  <span className="text-emerald-300 font-bold text-lg">{p.majority_alignment_pct}%</span>
                </div>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-2 bg-gradient-to-r from-emerald-500 to-emerald-400"
                  style={{ width: `${p.majority_alignment_pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="border border-amber-500/30 bg-amber-500/10 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-bold text-amber-200 mb-2">📊 분석 메서드</h3>
        <ul className="text-xs text-amber-100 space-y-1 list-disc pl-5">
          <li>각 의안 × 정당의 *majority vote* (yes/no/abstain 중 다수) 계산</li>
          <li>의원의 표결이 *정당 majority와 일치*하면 aligned</li>
          <li>응집도 = aligned / total_active_votes (absent 제외)</li>
          <li>Real Cypher: <code className="bg-amber-900/40 px-1 rounded">MATCH (p:Person)-[v:VOTED]-(:Bill)</code> + <code className="bg-amber-900/40 px-1 rounded">(p)-[:BELONGS_TO]-(party)</code></li>
        </ul>
      </section>

      <CohesionGraphAndInsight data={data} />
    </div>
  );
}

function CohesionGraphAndInsight({ data }: { data: Response }) {
  const subgraph = useMemo<Subgraph>(() => {
    // Party 노드 + 응집도 시각화
    const nodes: Array<{ id: string; label: string; data: Record<string, unknown> }> = data.parties.slice(0, 6).map((p) => ({
      id: `Party:${p.party}`, label: 'Party',
      data: { name: p.party, member_count: p.member_count, cohesion: `${p.majority_alignment_pct}%` },
    }));
    nodes.push({ id: 'Topic:cohesion', label: 'Topic', data: { name: '응집도 분석' } });
    const edges = data.parties.slice(0, 6).map((p) => ({
      source: `Party:${p.party}`, target: 'Topic:cohesion', type: 'ABOUT',
    }));
    return { root_id: 'Topic:cohesion', nodes, edges };
  }, [data]);

  const insightCtx = useMemo(() => ({
    relation_id: `cohesion_${data.parties.length}`,
    overall_cohesion: data.overall_cohesion,
    party_count: data.parties.length,
    parties: data.parties.slice(0, 8).map((p) => ({
      name: p.party,
      members: p.member_count,
      alignment_pct: p.majority_alignment_pct,
    })),
    total_active_votes: data.parties.reduce((s, p) => s + p.total_votes, 0),
  }), [data]);

  return (
    <>
      <section className="mb-6">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
          🕸️ 온톨로지 관계 그래프 — 정당 cohesion 분포
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40">
          <CytoscapeView subgraph={subgraph} height={400} expandable={false} />
        </div>
      </section>

      <AIInsightPanel scenarioCode="T" autoGenerate context={insightCtx} />
    </>
  );
}
