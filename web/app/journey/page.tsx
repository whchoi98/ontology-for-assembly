'use client';

/**
 * 시나리오 M - 의원 정치 여정 (PDF 시그니처 ★).
 *
 * 인물 선택 → 발의·표결·발언·위원회 활동 통합 timeline 표시.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  journeyApi,
  type AvailablePersonsResponse,
  type JourneyResponse,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

const EVENT_TYPE_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  proposed: { label: '발의', color: 'text-blue-300', bg: 'bg-blue-500/20 border border-blue-400/40' },
  co_proposed: { label: '공동발의', color: 'text-cyan-200', bg: 'bg-cyan-500/20 border border-cyan-400/40' },
  voted: { label: '표결', color: 'text-orange-200', bg: 'bg-orange-500/20 border border-orange-400/40' },
  statement: { label: '발언', color: 'text-pink-200', bg: 'bg-pink-500/20 border border-pink-400/40' },
  committee_join: { label: '위원회', color: 'text-emerald-200', bg: 'bg-emerald-500/20 border border-emerald-400/40' },
};


export default function JourneyPage() {
  const [persons, setPersons] = useState<AvailablePersonsResponse | null>(null);
  const [selectedPid, setSelectedPid] = useState<string>('MONA_001');
  const [journey, setJourney] = useState<JourneyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 인물 리스트 로드
  useEffect(() => {
    journeyApi.listPersons().then(setPersons).catch((e) => setError((e as Error).message));
  }, []);

  // 선택된 인물 timeline 로드
  const loadJourney = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const data = await journeyApi.detail(selectedPid, personaId);
      setJourney(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selectedPid]);

  useEffect(() => {
    void loadJourney();
  }, [loadJourney]);

  return (
    <div>
      <ScenarioHero code="M" subtitle="PDF 시그니처 ★" />

      {/* 의원 grid (사진 + 이름 + 정당 + 지역구) — /members 디렉토리 스타일 */}
      {persons && (
        <div className="mb-4">
          <div className="text-xs uppercase text-slate-400 mb-2">의원 선택 — 22대 전체 {persons.available_persons.length}명 (composite_score 정렬)</div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 max-h-96 overflow-y-auto pr-1">
            {persons.available_persons.map((p) => {
              const isActive = selectedPid === p.person_id;
              const photoUrl = `https://www.assembly.go.kr/static/portal/img/openassm/${p.person_id}.jpg`;
              return (
                <button
                  key={p.person_id}
                  onClick={() => setSelectedPid(p.person_id)}
                  className={
                    'p-2 rounded text-left transition-colors group ' +
                    (isActive
                      ? 'bg-blue-500/15 border border-blue-500/50'
                      : 'bg-slate-900/40 border border-slate-800 hover:border-blue-500/50')
                  }
                >
                  <div className="flex items-center gap-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={photoUrl}
                      alt={p.name}
                      className="w-10 h-10 rounded-full object-cover bg-slate-800 flex-shrink-0"
                      onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-semibold truncate ${isActive ? 'text-blue-200' : 'text-slate-200 group-hover:text-white'}`}>
                        {p.name}
                      </div>
                      <div className="text-[9px] text-slate-500 truncate">{p.party}</div>
                      <div className="text-[9px] text-slate-600 truncate">{p.district}</div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {loading && <p className="text-slate-400">로딩 중…</p>}

      {journey && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 인물 카드 + 통계 */}
          <aside className="lg:col-span-1 space-y-4">
            <PersonCard journey={journey} />
            <StatsCard journey={journey} />
            <SummaryCard journey={journey} />
          </aside>

          {/* Timeline */}
          <div className="lg:col-span-2">
            <Timeline events={journey.events} />
          </div>
        </div>
      )}
      {journey && (
        <AIInsightPanel
          scenarioCode="M"
          autoGenerate
          context={{
            person_id: journey.person_id,
            person_name: journey.person_name,
            party: journey.party,
            district: journey.district,
            term: journey.term,
            summary: journey.summary,
            stats: journey.stats,
            events_count: journey.events?.length ?? 0,
            events_preview: (journey.events ?? []).slice(0, 5).map((e) => ({
              date: e.date, event_type: e.event_type, title: e.title,
            })),
          }}
        />
      )}
    </div>
  );
}


function PersonCard({ journey }: { journey: JourneyResponse }) {
  const photoUrl = `https://www.assembly.go.kr/static/portal/img/openassm/${journey.person_id}.jpg`;
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <div className="flex items-center gap-3 mb-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={photoUrl}
          alt={journey.person_name}
          className="w-14 h-14 rounded-full object-cover bg-slate-800 flex-shrink-0"
          onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
        />
        <div>
          <div className="font-bold text-white">{journey.person_name}</div>
          <div className="text-xs text-slate-400">{journey.party ?? '—'} · {journey.district ?? '—'}</div>
        </div>
      </div>
      <dl className="text-xs space-y-1 mt-3">
        <div className="flex gap-2">
          <dt className="text-slate-400 w-12">정당</dt>
          <dd className="text-slate-100">{journey.party ?? '—'}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-slate-400 w-12">지역</dt>
          <dd className="text-slate-100">{journey.district ?? '—'}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-slate-400 w-12">회기</dt>
          <dd className="text-slate-100">{journey.term}대</dd>
        </div>
      </dl>
    </section>
  );
}


function StatsCard({ journey }: { journey: JourneyResponse }) {
  const stats = journey.stats;
  const items: Array<{ label: string; value: number; color: string }> = [
    { label: '발의', value: stats.proposed, color: 'text-blue-300' },
    { label: '공동발의', value: stats.co_proposed, color: 'text-cyan-300' },
    { label: '표결', value: stats.voted, color: 'text-orange-300' },
    { label: '발언', value: stats.statements, color: 'text-pink-300' },
  ];
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-xs uppercase text-slate-400">활동 통계</h2>
        <span className="text-[10px] text-amber-300 font-mono">
          22대 임기 · {stats.period_start} ~ {stats.period_end}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {items.map((s) => (
          <div key={s.label} className="bg-slate-800/40 rounded p-2">
            <div className="text-xs text-slate-400">{s.label}</div>
            <div className={`text-lg font-bold ${s.color}`}>{s.value}</div>
            <div className="text-[9px] text-slate-500 mt-0.5">임기 누적</div>
          </div>
        ))}
      </div>
      <div className="text-[10px] text-slate-500 mt-2 leading-relaxed">
        ※ 22대 국회 1분기 (2026-01 ~ 2026-05) 합성 timeline 기반 — 발의·표결·발언·위원회 활동 통합.
      </div>
    </section>
  );
}


function SummaryCard({ journey }: { journey: JourneyResponse }) {
  return (
    <section className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
      <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">
        AI 요약
      </div>
      <p className="text-xs text-amber-100 leading-relaxed">{journey.summary}</p>
      {journey.extras.follow_up_hint && (
        <p className="text-[11px] text-amber-300 mt-2 italic">
          {journey.extras.follow_up_hint}
        </p>
      )}
    </section>
  );
}


function Timeline({ events }: { events: JourneyResponse['events'] }) {
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <h2 className="text-xs uppercase text-slate-400 mb-3">Timeline (시간순)</h2>
      <ol className="relative border-l-2 border-slate-800 ml-4">
        {events.map((e) => {
          const style = EVENT_TYPE_STYLE[e.event_type] ?? { label: e.event_type, color: 'text-slate-200', bg: 'bg-slate-800' };
          return (
            <li key={e.event_id} className="mb-5 ml-6">
              <span
                className="absolute -left-[14px] w-7 h-7 bg-slate-900/40 border-2 border-slate-700 rounded-full flex items-center justify-center"
                aria-hidden
              >
                {e.icon || '•'}
              </span>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${style.bg} ${style.color}`}>
                  {style.label}
                </span>
                <time className="text-xs text-slate-400 font-mono">{e.date}</time>
              </div>
              <h3 className="font-semibold text-white text-sm">{e.title}</h3>
              <p className="text-xs text-slate-300 leading-relaxed mt-1">{e.description}</p>
              {e.related_id && (
                <div className="text-[10px] text-slate-500 font-mono mt-1">
                  related: {e.related_id.length > 36 ? e.related_id.slice(0, 36) + '…' : e.related_id}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
