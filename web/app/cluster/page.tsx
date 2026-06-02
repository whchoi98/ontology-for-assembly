'use client';

/**
 * 시나리오 E - 의원 클러스터링.
 *
 * 5 thematic 클러스터 카드 + 선택 시 디테일 (멤버 리스트 + cross-party share +
 * dominant topics + insight + 페르소나 hint).
 */
import React, { useCallback, useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  clusterApi,
  type ClusterListResponse,
  type ClusterDetailResponse,
  type ClusterEntry,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

export default function ClusterPage() {
  const [list, setList] = useState<ClusterListResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClusterDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const r = await clusterApi.list(personaId);
      setList(r);
      if (r.clusters.length > 0 && !selectedId) {
        setSelectedId(r.clusters[0].cluster_id);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [selectedId]);

  useEffect(() => { void loadList(); }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const personaId = readPersonaIdSync() as PersonaId;
    clusterApi.detail(selectedId, personaId).then(setDetail).catch((e) => setError((e as Error).message));
  }, [selectedId]);

  return (
    <div>
      <ScenarioHero code="E" subtitle="5 thematic cluster · ADR-0004" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {list && (
        <>
          <p className="text-xs text-amber-200 bg-amber-500/10 border border-amber-400/30 rounded p-2 mb-4">
            {list.persona_note}
          </p>
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <section className="lg:col-span-2 space-y-2">
              {list.clusters.map((c) => (
                <ClusterCard
                  key={c.cluster_id}
                  cluster={c}
                  selected={selectedId === c.cluster_id}
                  onClick={() => setSelectedId(c.cluster_id)}
                />
              ))}
            </section>

            <section className="lg:col-span-3">
              {detail ? (
                <ClusterDetail detail={detail} />
              ) : (
                <p className="text-sm text-slate-500">클러스터를 선택하세요.</p>
              )}
            </section>
          </div>
        </>
      )}
      {detail ? (
        <AIInsightPanel scenarioCode="E" autoGenerate context={{
          cluster_id: detail.cluster.cluster_id,
          cluster_label: detail.cluster.label,
          dominant_topics: detail.cluster.dominant_topics,
          description: detail.cluster.description,
          member_count: detail.cluster.member_count,
          parties_represented: detail.cluster.parties_represented,
          cross_party_share: detail.cluster.cross_party_share,
          coherence_score: detail.cluster.coherence_score,
          avg_proposed: detail.cluster.avg_activity.proposed,
          avg_voted: detail.cluster.avg_activity.voted,
          avg_statements: detail.cluster.avg_activity.statements,
          top_member_names: detail.cluster.members.slice(0, 5).map((m) => m.name),
        }} />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          클러스터를 선택하면 해당 그룹 specific AI 인사이트가 표시됩니다.
        </div>
      )}
    </div>
  );
}


function ClusterCard({
  cluster, selected, onClick,
}: { cluster: ClusterEntry; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={
        'block w-full text-left border rounded-md p-3 transition-all ' +
        (selected
          ? 'border-blue-500 bg-blue-500/15 ring-1 ring-blue-300'
          : 'border-slate-800 bg-slate-900/40 hover:border-slate-600')
      }
    >
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-sm font-semibold text-white">{cluster.label}</span>
        <span className="text-[10px] text-slate-400 font-mono">
          코히어런스 {cluster.coherence_score.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-slate-300 mb-1">
        <span>멤버 {cluster.member_count}</span>
        <span>·</span>
        <span>{cluster.parties_represented.length}개 정당</span>
        <span>·</span>
        <span className={cluster.cross_party_share >= 0.4 ? 'text-emerald-300 font-medium' : ''}>
          cross-party {(cluster.cross_party_share * 100).toFixed(0)}%
        </span>
      </div>
      <p className="text-[11px] text-slate-200 line-clamp-2">{cluster.description}</p>
    </button>
  );
}


function ClusterDetail({ detail }: { detail: ClusterDetailResponse }) {
  const c = detail.cluster;
  return (
    <div className="space-y-4">
      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h2 className="text-lg font-bold text-white mb-2">{c.label}</h2>
        <p className="text-xs text-slate-200 leading-relaxed mb-3">{c.description}</p>

        <h3 className="text-xs uppercase text-slate-400 mb-1.5">Dominant Topics</h3>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {c.dominant_topics.map((t) => (
            <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-400/40 text-purple-200 font-medium">
              {t}
            </span>
          ))}
        </div>

        <h3 className="text-xs uppercase text-slate-400 mb-1.5">통계</h3>
        <div className="grid grid-cols-4 gap-2 text-[11px]">
          <Stat label="멤버" value={c.member_count.toString()} />
          <Stat label="코히어런스" value={c.coherence_score.toFixed(2)} />
          <Stat label="cross-party" value={`${(c.cross_party_share * 100).toFixed(0)}%`} />
          <Stat label="정당 수" value={c.parties_represented.length.toString()} />
        </div>

        <h3 className="text-xs uppercase text-slate-400 mt-3 mb-1.5">평균 활동 (의원당)</h3>
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          <Stat label="발의" value={c.avg_activity.proposed.toFixed(1)} color="text-blue-300" />
          <Stat label="표결" value={c.avg_activity.voted.toFixed(1)} color="text-orange-300" />
          <Stat label="발언" value={c.avg_activity.statements.toFixed(1)} color="text-pink-300" />
        </div>
      </div>

      <div className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
        <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">
          AI 인사이트
        </div>
        <p className="text-xs text-amber-100 leading-relaxed">{c.insight}</p>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h3 className="text-xs uppercase text-slate-400 mb-2">
          멤버 ({c.member_count}) - activity_score 순
        </h3>
        <div className="space-y-1.5">
          {c.members.map((m) => (
            <MemberRow key={m.person_id} member={m} />
          ))}
        </div>
        <div className="mt-3 text-[10px] text-slate-400">
          참여 정당: {c.parties_represented.join(' · ')}
        </div>
      </div>

      {detail.extras.follow_up_hint && (
        <ExtraBox color="amber" label="후속 취재" text={detail.extras.follow_up_hint} />
      )}
      {detail.extras.premium_cta && (
        <ExtraBox color="purple" label="Premium" text={detail.extras.premium_cta} />
      )}
      {detail.extras.api_response_hint && (
        <ExtraBox color="gray" label="API" text={detail.extras.api_response_hint} />
      )}
    </div>
  );
}


function MemberRow({ member }: { member: import('../../lib/scenario-clients').ClusterMember }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="font-mono text-slate-400 w-20 shrink-0">{member.person_id}</span>
      <span className="font-medium text-white w-12 shrink-0">{member.name}</span>
      <span className="text-slate-400 w-24 shrink-0 truncate">{member.party}</span>
      <span className="text-slate-400 flex-1 truncate">{member.district}</span>
      <span className="font-mono text-slate-200 w-12 shrink-0 text-right">
        {member.activity_score.toFixed(2)}
      </span>
      <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden shrink-0">
        <div
          className="h-1.5 bg-blue-500 rounded-full"
          style={{ width: `${member.activity_score * 100}%` }}
        />
      </div>
    </div>
  );
}


function Stat({
  label, value, color,
}: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-slate-800/40 rounded p-2">
      <div className="text-slate-400 text-[10px]">{label}</div>
      <div className={`font-semibold ${color ?? 'text-white'}`}>{value}</div>
    </div>
  );
}


function ExtraBox({ color, label, text }: { color: string; label: string; text: string }) {
  const colors: Record<string, string> = {
    amber: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
    purple: 'border-purple-400 bg-purple-500/15 text-purple-100',
    gray: 'border-slate-600 bg-slate-800/40 text-slate-200',
  };
  return (
    <div className={`border-l-4 p-3 rounded ${colors[color] ?? colors.gray}`}>
      <div className="text-[10px] uppercase font-semibold mb-1">{label}</div>
      <p className="text-xs leading-relaxed">{text}</p>
    </div>
  );
}
