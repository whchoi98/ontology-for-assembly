'use client';

/**
 * 시나리오 V — 표결 패턴 cluster (Phase 4f, REAL Cypher).
 *
 * 22대 의원을 *yes_rate × 정당*으로 5 cluster 분류.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { CytoscapeView } from '../../components/CytoscapeView';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import type { Subgraph } from '../../lib/api-client';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface Cluster {
  cluster_id: string;
  label: string;
  members: Array<{ assembly_id: string; name: string; party: string; yes_rate: number; total_votes: number }>;
  member_count: number;
  dominant_parties: string[];
  avg_yes_rate: number;
}

interface Response {
  clusters: Cluster[];
  source: string;
  method: string;
}

const CLUSTER_COLOR: Record<string, string> = {
  progressive_high: 'border-blue-400/40 bg-blue-500/10 text-blue-200',
  progressive_low: 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200',
  conservative_high: 'border-red-400/40 bg-red-500/10 text-red-200',
  conservative_low: 'border-orange-400/40 bg-orange-500/10 text-orange-200',
  centrist: 'border-purple-400/40 bg-purple-500/10 text-purple-200',
};

export default function VotingClusterPage() {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}/api/insights/voting-cluster`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="text-red-300 p-4">Error: {error}</div>;
  if (!data) return <div className="text-slate-400 p-4">Loading…</div>;

  const selectedCluster = selected ? data.clusters.find((c) => c.cluster_id === selected) : null;

  return (
    <div>
      <header className="mb-6 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-xs px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-400/40 text-emerald-300">
            시나리오 V · REAL
          </span>
          <span className="text-xs text-slate-500">· Phase 4f</span>
        </div>
        <h1 className="text-2xl font-bold text-white mb-1.5">표결 패턴 cluster</h1>
        <p className="text-sm text-slate-300">
          22대 의원 303명을 *yes_rate × 정당*으로 5 cluster 분류 — {data.method}.
        </p>
        <div className="mt-3 bg-emerald-500/15 border border-emerald-400/40 rounded-md px-3 py-2 text-emerald-100 text-[11px]">
          🟢 REAL · 표결 28,528 엣지 분석 — *yes_rate ≥ 0.7 → 높은 찬성률 그룹*, 그 외 *신중 표결 그룹*.
        </div>
      </header>

      <section className="mb-6 grid grid-cols-1 md:grid-cols-5 gap-3">
        {data.clusters.map((c) => (
          <button
            key={c.cluster_id}
            type="button"
            onClick={() => setSelected(c.cluster_id)}
            className={
              'rounded-lg border p-3 text-left transition-colors ' +
              (selected === c.cluster_id ? 'ring-2 ring-amber-400 ' : '') +
              (CLUSTER_COLOR[c.cluster_id] || 'border-slate-800 bg-slate-900/40 text-slate-200')
            }
          >
            <div className="text-[10px] uppercase tracking-wider opacity-70 mb-1">cluster</div>
            <div className="font-bold text-sm mb-1">{c.label}</div>
            <div className="text-2xl font-mono font-bold">{c.member_count}<span className="text-xs ml-1">명</span></div>
            <div className="text-[10px] mt-1 opacity-70">yes {(c.avg_yes_rate * 100).toFixed(0)}%</div>
          </button>
        ))}
      </section>

      {selectedCluster && (
        <section className="mb-6 border border-slate-800 bg-slate-900/40 rounded-lg p-4">
          <h2 className="text-sm font-bold text-white mb-3">
            {selectedCluster.label} — 대표 의원 sample (top 10)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {selectedCluster.members.map((m) => (
              <div key={m.assembly_id} className="flex items-center gap-2 p-2 bg-slate-800/30 rounded">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`https://www.assembly.go.kr/static/portal/img/openassm/${m.assembly_id}.jpg`}
                  alt={m.name}
                  className="w-9 h-9 rounded-full object-cover bg-slate-800"
                  onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
                />
                <div className="flex-1">
                  <div className="text-sm font-semibold text-white">{m.name}</div>
                  <div className="text-[10px] text-slate-400">{m.party}</div>
                </div>
                <div className="text-right">
                  <div className="text-emerald-300 font-mono font-bold">{(m.yes_rate * 100).toFixed(0)}%</div>
                  <div className="text-[9px] text-slate-500">표결 {m.total_votes}건</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {selectedCluster && <ClusterGraphAndInsight cluster={selectedCluster} />}

      <section className="border border-amber-500/30 bg-amber-500/10 rounded-lg p-4">
        <h3 className="text-sm font-bold text-amber-200 mb-2">📊 cluster 분류 메서드</h3>
        <ul className="text-xs text-amber-100 space-y-1 list-disc pl-5">
          <li>각 의원의 yes_rate = (yes 표결 수 / 전체 active 표결 수) 계산</li>
          <li>정당 cluster 매핑: <strong>진보계열</strong> (민주당·조국혁신당·진보당·기본소득당), <strong>보수계열</strong> (국민의힘·개혁신당), <strong>중도</strong> (무소속·기타)</li>
          <li>찬성률 threshold: <strong>≥ 0.7</strong> → "높은 찬성률", <strong>&lt; 0.7</strong> → "신중 표결"</li>
          <li>5 cluster: progressive_high / progressive_low / conservative_high / conservative_low / centrist</li>
        </ul>
      </section>
    </div>
  );
}

function ClusterGraphAndInsight({ cluster }: { cluster: Cluster }) {
  const subgraph = useMemo<Subgraph>(() => {
    const top = cluster.members.slice(0, 8);
    const nodes = top.map((m) => ({
      id: `Person:${m.assembly_id}`, label: 'Person',
      data: {
        name: m.name, party: m.party,
        profile_image_url: `https://www.assembly.go.kr/static/portal/img/openassm/${m.assembly_id}.jpg`,
        yes_rate: m.yes_rate,
      },
    }));
    const hubId = `Topic:${cluster.cluster_id}`;
    nodes.push({ id: hubId, label: 'Topic', data: { name: cluster.label, yes_rate: 0, party: '', profile_image_url: '' } });
    const edges = top.map((m) => ({ source: `Person:${m.assembly_id}`, target: hubId, type: 'BELONGS_TO' }));
    return { root_id: hubId, nodes, edges };
  }, [cluster]);

  const insightCtx = useMemo(() => ({
    cluster_id: cluster.cluster_id,
    cluster_label: cluster.label,
    member_count: cluster.member_count,
    avg_yes_rate: cluster.avg_yes_rate,
    dominant_parties: cluster.dominant_parties,
    top_member_names: cluster.members.slice(0, 5).map((m) => m.name),
  }), [cluster]);

  return (
    <>
      <section className="mb-6">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
          🕸️ 온톨로지 관계 그래프 — {cluster.label} 의원 cohort
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40">
          <CytoscapeView subgraph={subgraph} height={400} expandable={false} />
        </div>
      </section>

      <div className="mb-6">
        <AIInsightPanel scenarioCode="V" autoGenerate context={insightCtx} />
      </div>
    </>
  );
}
