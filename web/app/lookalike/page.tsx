'use client';

/**
 * 시나리오 F - 룩어라이크.
 *
 * seed 의원 선택 (dropdown 또는 시드 카드) → top-K 유사 후보 막대 + factors +
 * cross-party 시그널 강조 + narrative.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  lookalikeApi,
  type LookalikeResult,
  type LookalikeSeedsResponse,
  type LookalikeCandidate,
} from '../../lib/scenario-clients';
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

function buildLookalikeSubgraph(r: LookalikeResult, memberById: Map<string, MemberLite>): Subgraph {
  const seedM = memberById.get(r.seed_person_id);
  const seedId = `Person:${r.seed_person_id}`;
  const clusterId = r.seed_cluster_id ? `Cluster:${r.seed_cluster_id}` : null;

  const seedNode = {
    id: seedId, label: 'Person' as const,
    data: {
      name: r.seed_name, party: r.seed_party,
      district: seedM?.district ?? '',
      ...(seedM?.profile_image_url ? { profile_image_url: seedM.profile_image_url } : {}),
    },
  };

  const candidateNodes = r.candidates.map((c) => {
    const m = memberById.get(c.person_id);
    return {
      id: `Person:${c.person_id}`,
      label: 'Person' as const,
      data: {
        name: c.name, party: c.party, district: c.district,
        similarity: c.similarity,
        ...(m?.profile_image_url ? { profile_image_url: m.profile_image_url } : {}),
      },
    };
  });

  const clusterNodes = clusterId
    ? [{ id: clusterId, label: 'Topic' as const, data: { name: r.seed_cluster_label ?? r.seed_cluster_id ?? '' } }]
    : [];

  const nodes = [seedNode, ...clusterNodes, ...candidateNodes];
  const edges = [
    ...(clusterId ? [{ source: seedId, target: clusterId, type: 'BELONGS_TO' }] : []),
    ...candidateNodes.flatMap((cn) => [
      // 유사 의원 → 같은 cluster 소속
      ...(clusterId ? [{ source: cn.id, target: clusterId, type: 'BELONGS_TO' }] : []),
      // seed ↔ 유사 의원 (similarity)
      { source: seedId, target: cn.id, type: 'CO_PROPOSED' },
    ]),
  ];

  return { root_id: seedId, nodes, edges };
}


export default function LookalikePage() {
  const [seeds, setSeeds] = useState<LookalikeSeedsResponse | null>(null);
  // seedId는 seeds fetch 완료 후 첫 항목으로 자동 설정 — 옛 'MONA_001' fixture id로 인한 404 회피
  const [seedId, setSeedId] = useState<string>('');
  const [topK, setTopK] = useState(5);
  const [result, setResult] = useState<LookalikeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [members, setMembers] = useState<MemberLite[]>([]);

  useEffect(() => {
    fetch(`${BASE}/api/members`).then((r) => r.json()).then((d) => setMembers(d.members ?? [])).catch(() => {});
  }, []);

  const memberById = useMemo(() => {
    const m = new Map<string, MemberLite>();
    for (const x of members) m.set(x.assembly_id, x);
    return m;
  }, [members]);

  const subgraph = useMemo(
    () => (result ? buildLookalikeSubgraph(result, memberById) : null),
    [result, memberById],
  );

  const insightCtx = useMemo(() => {
    if (!result) return null;
    return {
      person_id: result.seed_person_id,
      seed_name: result.seed_name,
      seed_party: result.seed_party,
      seed_cluster_label: result.seed_cluster_label,
      top_k: result.candidates.length,
      candidate_names: result.candidates.map((c) => c.name),
      candidate_parties: Array.from(new Set(result.candidates.map((c) => c.party))),
      cross_party_count: result.candidates.filter((c) => c.cross_party_signal).length,
      avg_similarity: result.candidates.length
        ? result.candidates.reduce((s, c) => s + c.similarity, 0) / result.candidates.length
        : 0,
      top_factors: Array.from(new Set(result.candidates.flatMap((c) => c.factors))).slice(0, 5),
    };
  }, [result]);

  useEffect(() => {
    lookalikeApi.seeds()
      .then((s) => {
        setSeeds(s);
        if (s.seeds.length && !seedId) setSeedId(s.seeds[0].person_id);
      })
      .catch((e) => setError((e as Error).message));
    // seedId는 의도적으로 deps에서 제외 — 초기 1회만 첫 seed로 set
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadResult = useCallback(async () => {
    if (!seedId) return;  // seeds fetch 완료 전 호출 회피
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const r = await lookalikeApi.detail(seedId, topK, personaId);
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [seedId, topK]);

  useEffect(() => { void loadResult(); }, [loadResult]);

  return (
    <div>
      <ScenarioHero code="F" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {/* 컨트롤 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="md:col-span-2">
          <label className="block text-xs text-slate-400 mb-1">Seed 의원</label>
          <select
            value={seedId}
            onChange={(e) => setSeedId(e.target.value)}
            className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md px-2 py-1.5 text-slate-100 focus:outline-none focus:border-blue-500"
          >
            {seeds?.seeds.map((s) => (
              <option key={s.person_id} value={s.person_id}>
                {s.person_id} · {s.name} · {s.party} · {s.cluster_label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Top-K (1-15)</label>
          <input
            type="number"
            min={1}
            max={15}
            value={topK}
            onChange={(e) => setTopK(Math.max(1, Math.min(15, parseInt(e.target.value, 10) || 5)))}
            className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md px-2 py-1.5 text-slate-100 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {result && (
        <>
          {/* seed 메타 */}
          <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4 mb-4">
            <div className="flex items-baseline gap-3">
              <div>
                <div className="text-[10px] text-slate-400">Seed</div>
                <h2 className="text-lg font-bold">{result.seed_name}</h2>
                <div className="text-[11px] text-slate-300">
                  {result.seed_party} · {result.seed_cluster_label}
                </div>
              </div>
            </div>
          </section>

          <div className="border border-amber-500/30 bg-amber-500/10 p-3 rounded mb-4">
            <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">narrative</div>
            <p className="text-xs text-amber-100">{result.narrative}</p>
          </div>

          {/* 후보 리스트 */}
          <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4 mb-4">
            <h3 className="text-xs uppercase text-slate-400 mb-2">
              유사 후보 ({result.candidates.length})
            </h3>
            <div className="space-y-3">
              {result.candidates.map((c, i) => (
                <CandidateRow key={c.person_id} candidate={c} rank={i + 1} />
              ))}
            </div>
          </section>

          {/* 출처 */}
          <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-3 mb-4">
            <div className="text-[10px] uppercase text-slate-400 mb-1">데이터 출처</div>
            <div className="flex flex-wrap gap-1">
              {result.sources.map((s) => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* 페르소나 hints */}
          {result.extras.follow_up_hint && (
            <ExtraBox color="amber" label="후속 취재" text={result.extras.follow_up_hint} />
          )}
          {result.extras.analysis_hint && (
            <ExtraBox color="cyan" label="분석 hint" text={result.extras.analysis_hint} />
          )}
          {result.extras.premium_cta && (
            <ExtraBox color="purple" label="Premium" text={result.extras.premium_cta} />
          )}
          {result.extras.api_response_hint && (
            <ExtraBox color="gray" label="API" text={result.extras.api_response_hint} />
          )}
        </>
      )}
      {/* 온톨로지 관계 그래프 — seed + candidates */}
      {subgraph && (
        <section className="mb-6">
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            🕸️ 룩어라이크 온톨로지 관계 그래프 — <span className="text-white">{result?.seed_name}</span>
            <span className="ml-2 text-[10px] text-slate-500">
              {result?.seed_cluster_label ?? 'cluster'} · top-{result?.candidates.length} 유사 의원
            </span>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40">
            <CytoscapeView subgraph={subgraph} height={440} expandable={false} />
          </div>
        </section>
      )}

      {insightCtx ? (
        <AIInsightPanel scenarioCode="F" autoGenerate context={insightCtx} />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          Seed 의원 선택 후 *해당 결과 specific* AI 인사이트 + 온톨로지 관계 그래프이 표시됩니다.
        </div>
      )}
    </div>
  );
}


function CandidateRow({ candidate, rank }: { candidate: LookalikeCandidate; rank: number }) {
  return (
    <div className="border border-slate-800 rounded p-3">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-[11px] text-slate-500 font-mono w-6">#{rank}</span>
        <span className="font-semibold">{candidate.name}</span>
        <span className="text-[10px] text-slate-400 font-mono">{candidate.person_id}</span>
        <span className="text-[10px] text-slate-400">{candidate.party}</span>
        {candidate.cross_party_signal && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 border border-emerald-400/40 text-emerald-200 font-medium">
            ★ cross-party
          </span>
        )}
        <span className="ml-auto font-mono font-semibold text-blue-300">
          {candidate.similarity.toFixed(3)}
        </span>
      </div>
      <div className="text-[11px] text-slate-300 mb-1.5">
        {candidate.district} · {candidate.cluster_label} · activity {candidate.activity_score.toFixed(2)}
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden mb-1.5">
        <div
          className={`h-1.5 rounded-full ${candidate.cross_party_signal ? 'bg-emerald-500' : 'bg-blue-500'}`}
          style={{ width: `${candidate.similarity * 100}%` }}
        />
      </div>
      <ul className="text-[10px] text-slate-300 space-y-0.5">
        {candidate.factors.map((f, i) => (
          <li key={i} className="ml-3 list-disc">{f}</li>
        ))}
      </ul>
    </div>
  );
}


function ExtraBox({ color, label, text }: { color: string; label: string; text: string }) {
  const colors: Record<string, string> = {
    amber: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
    cyan: 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200',
    purple: 'border-purple-400 bg-purple-500/15 text-purple-100',
    gray: 'border-slate-600 bg-slate-800/40 text-slate-200',
  };
  return (
    <div className={`border p-3 rounded mb-3 ${colors[color] ?? colors.gray}`}>
      <div className="text-[10px] uppercase font-semibold mb-1">{label}</div>
      <p className="text-xs leading-relaxed">{text}</p>
    </div>
  );
}
