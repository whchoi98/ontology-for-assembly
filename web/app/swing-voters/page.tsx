'use client';

/**
 * 시나리오 W — Swing voter detection (Phase 4f, REAL Cypher).
 *
 * 정당 majority와 다르게 투표한 의원 ranking — 개별 신념·정책 차이 narrative.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { CytoscapeView } from '../../components/CytoscapeView';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import type { Subgraph } from '../../lib/api-client';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface SwingMember {
  assembly_id: string;
  name: string;
  party: string;
  district: string;
  party_majority_alignment_pct: number;
  total_active_votes: number;
  deviation_count: number;
}

interface Response {
  members: SwingMember[];
  total_evaluated: number;
  threshold_pct: number;
  source: string;
}

export default function SwingVotersPage() {
  const [limit, setLimit] = useState(20);
  const [threshold, setThreshold] = useState(95);
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}/api/insights/swing-voters?limit=${limit}&threshold_pct=${threshold}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [limit, threshold]);

  if (error) return <div className="text-red-300 p-4">Error: {error}</div>;
  if (!data) return <div className="text-slate-400 p-4">Loading…</div>;

  return (
    <div>
      <header className="mb-6 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-xs px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-400/40 text-emerald-300">
            시나리오 W · REAL
          </span>
          <span className="text-xs text-slate-500">· Phase 4f</span>
        </div>
        <h1 className="text-2xl font-bold text-white mb-1.5">Swing Voter Detection</h1>
        <p className="text-sm text-slate-300">
          정당 majority value와 다르게 투표한 의원 ranking — *개별 신념·정책 차이*가 표결로 드러난 case (인터뷰 hook).
        </p>
        <div className="mt-3 bg-emerald-500/15 border border-emerald-400/40 rounded-md px-3 py-2 text-emerald-100 text-[11px]">
          🟢 REAL · {data.total_evaluated}명 의원 (active 표결 10건 이상) 중 *정당 일치율 &lt; {data.threshold_pct}%*인 swing voter 탐지.
        </div>
        <div className="mt-2 bg-amber-500/10 border border-amber-400/30 rounded-md px-3 py-2 text-amber-100 text-[11px]">
          ℹ️ <b>22대 국회 응집도 ~99%</b> (시나리오 T) — 정당 노선 이탈이 매우 드물기에, 일반적 국제 기준(70-80%) 대신 *95%+ threshold*에서 의미 있는 swing voter가 보입니다.
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Top:</span>
          {[10, 20, 50].map((n) => (
            <button
              key={n}
              onClick={() => setLimit(n)}
              className={
                'px-3 py-1 rounded ' +
                (limit === n
                  ? 'bg-emerald-500/20 border border-emerald-500/50 text-emerald-200'
                  : 'bg-slate-800 border border-slate-700 text-slate-400')
              }
            >{n}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-slate-400">일치율 threshold:</span>
          {[90, 95, 98].map((t) => (
            <button
              key={t}
              onClick={() => setThreshold(t)}
              className={
                'px-3 py-1 rounded ' +
                (threshold === t
                  ? 'bg-amber-500/20 border border-amber-500/50 text-amber-200'
                  : 'bg-slate-800 border border-slate-700 text-slate-400')
              }
            >&lt; {t}%</button>
          ))}
          <span className="text-slate-500 text-[10px]">(22대 응집도 99%+ 기준 calibrated)</span>
        </div>
      </div>

      <section className="mb-6 space-y-2">
        {data.members.length === 0 ? (
          <div className="text-center text-slate-400 py-8">현재 threshold에서 swing voter 없음 — 더 높은 threshold 시도 (22대 응집도 ~99%).</div>
        ) : (
          data.members.map((m, i) => (
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
                <div className="flex items-center gap-3 text-[11px] font-mono">
                  <div className="text-center">
                    <div className="text-amber-300 font-bold text-lg">{m.party_majority_alignment_pct}%</div>
                    <div className="text-[9px] text-slate-500">정당 일치</div>
                  </div>
                  <div className="text-center">
                    <div className="text-red-300 font-bold">{m.deviation_count}</div>
                    <div className="text-[9px] text-slate-500">/{m.total_active_votes} 이탈</div>
                  </div>
                </div>
              </div>
              <div className="mt-2 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-1.5 bg-gradient-to-r from-red-500 to-amber-400"
                  style={{ width: `${100 - m.party_majority_alignment_pct}%` }}
                />
              </div>
            </div>
          ))
        )}
      </section>

      {data.members.length > 0 && <SwingGraphAndInsight members={data.members} threshold={data.threshold_pct} />}

      <section className="border border-amber-500/30 bg-amber-500/10 rounded-lg p-4">
        <h3 className="text-sm font-bold text-amber-200 mb-2">📊 swing voter 분석 메서드</h3>
        <ul className="text-xs text-amber-100 space-y-1 list-disc pl-5">
          <li>각 의안 × 정당의 majority value 계산 (yes/no/abstain 중 다수)</li>
          <li>의원의 표결이 정당 majority와 다르면 *이탈*로 카운트</li>
          <li>일치율 = aligned / total_active_votes (absent 제외)</li>
          <li>일치율 &lt; threshold% 인 의원만 swing voter ranking</li>
          <li>narrative 가치: *정당 노선과 다른 표결*은 *개별 정책 신념·지역 이해관계*를 드러냄 — 후속 취재 hook ↑</li>
        </ul>
      </section>
    </div>
  );
}

function SwingGraphAndInsight({ members, threshold }: { members: SwingMember[]; threshold: number }) {
  const subgraph = useMemo<Subgraph>(() => {
    const top = members.slice(0, 8);
    const nodes = top.map((m) => ({
      id: `Person:${m.assembly_id}`, label: 'Person',
      data: {
        name: m.name, party: m.party, district: m.district,
        profile_image_url: `https://www.assembly.go.kr/static/portal/img/openassm/${m.assembly_id}.jpg`,
        alignment: m.party_majority_alignment_pct,
      },
    }));
    const hubId = 'Topic:swing';
    nodes.push({ id: hubId, label: 'Topic', data: { name: `Swing voters (일치 < ${threshold}%)`, party: '', district: '', profile_image_url: '', alignment: 0 } });
    const edges = top.map((m) => ({ source: `Person:${m.assembly_id}`, target: hubId, type: 'VOTED' }));
    return { root_id: hubId, nodes, edges };
  }, [members, threshold]);

  const insightCtx = useMemo(() => ({
    relation_id: `swing_${threshold}`,
    threshold_pct: threshold,
    swing_count: members.length,
    top_member_names: members.slice(0, 5).map((m) => m.name),
    top_member_parties: Array.from(new Set(members.slice(0, 10).map((m) => m.party))),
    avg_alignment: members.length > 0
      ? Math.round(members.reduce((s, m) => s + m.party_majority_alignment_pct, 0) / members.length)
      : 0,
    rank1_name: members[0]?.name ?? '',
    rank1_party: members[0]?.party ?? '',
    rank1_alignment: members[0]?.party_majority_alignment_pct ?? 0,
    rank1_deviation: members[0]?.deviation_count ?? 0,
  }), [members, threshold]);

  return (
    <>
      <section className="mb-6">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
          🕸️ 온톨로지 관계 그래프 — Top swing voters cohort
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40">
          <CytoscapeView subgraph={subgraph} height={400} expandable={false} />
        </div>
      </section>

      <div className="mb-6">
        <AIInsightPanel scenarioCode="W" autoGenerate context={insightCtx} />
      </div>
    </>
  );
}
