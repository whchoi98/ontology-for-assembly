'use client';

/**
 * 시나리오 I - 편향·중립성 가드레일 (ADR-0004 시연).
 *
 * 4 레이어 아키텍처 시각화 + 4 등급 샘플 + 실시간 채점 + 최근 trace.
 * ADR-0004 가드레일의 "보이는 거버넌스" 데모.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { BiasScoreIndicator } from '../../components/BiasScoreIndicator';
import {
  neutralityApi,
  type NeutralitySamplesResponse,
  type NeutralityScoreResponse,
  type NeutralityArchitectureResponse,
  type NeutralityRecentResponse,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

export default function NeutralityPage() {
  const [samples, setSamples] = useState<NeutralitySamplesResponse | null>(null);
  const [architecture, setArchitecture] = useState<NeutralityArchitectureResponse | null>(null);
  const [recent, setRecent] = useState<NeutralityRecentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const [s, a, r] = await Promise.all([
        neutralityApi.samples(personaId),
        neutralityApi.architecture(personaId),
        neutralityApi.recent(20, personaId),
      ]);
      setSamples(s);
      setArchitecture(a);
      setRecent(r);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <div>
      <ScenarioHero code="I" subtitle="AI 거버넌스" />

      {error && (
        <div className="border border-red-400/40 bg-red-500/15 text-red-200 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {architecture && <ArchitectureSection arch={architecture} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <div>{samples && <SamplesSection samples={samples} />}</div>
        <div className="space-y-6">
          <LiveScoreForm />
          {recent && <RecentTraceSection recent={recent} />}
        </div>
      </div>
      <AIInsightPanel scenarioCode="I" context={samples} />
    </div>
  );
}


function ArchitectureSection({ arch }: { arch: NeutralityArchitectureResponse }) {
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm font-bold text-white">{arch.adr_reference} 4-layer</h2>
        <span className="text-xs text-slate-400">
          weights: balance {arch.weights.party_balance} / cite {arch.weights.citation} /
          assertion {arch.weights.assertion_penalty} · 알람 임계 {arch.weights.alarm_threshold}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {arch.layers.map((l) => (
          <div
            key={l.layer}
            className={
              'border rounded-md p-3 ' +
              (l.is_active ? 'border-emerald-400/50 bg-emerald-500/15 text-emerald-100' : 'border-slate-800 bg-slate-800/40')
            }
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-200 font-mono">
                L{l.layer}
              </span>
              {l.is_active && (
                <span className="text-[10px] text-emerald-300 font-medium">● 활성</span>
              )}
            </div>
            <div className="text-sm font-semibold text-white">{l.name}</div>
            <div className="text-[10px] text-slate-400 font-mono mt-0.5">{l.where}</div>
            <p className="text-xs text-slate-200 leading-relaxed mt-2">{l.description}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 text-[11px] text-slate-400">
        정당 카탈로그 ({arch.party_catalog.length}): {arch.party_catalog.join(' · ')}
      </div>
    </section>
  );
}


function SamplesSection({ samples }: { samples: NeutralitySamplesResponse }) {
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <h2 className="text-sm font-bold text-white mb-1">데모 텍스트 4 등급</h2>
      <p className="text-xs text-slate-400 mb-3">{samples.note}</p>
      <div className="space-y-3">
        {samples.samples.map((s) => (
          <div key={s.sample_id} className="border border-slate-800 rounded p-3">
            <div className="flex items-center gap-2 mb-1">
              <span
                className={
                  'text-[10px] px-1.5 py-0.5 rounded font-medium ' +
                  (s.label === '우수'
                    ? 'bg-emerald-500/20 border border-emerald-400/40 text-emerald-200'
                    : s.label === '양호'
                      ? 'bg-blue-500/20 border border-blue-400/40 text-blue-200'
                      : s.label === '중간'
                        ? 'bg-amber-500/15 text-amber-300'
                        : 'bg-red-500/20 border border-red-400/40 text-red-200')
                }
              >
                {s.label}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">{s.sample_id}</span>
            </div>
            <p className="text-xs text-slate-400 italic mb-2">{s.description}</p>
            <p className="text-xs text-slate-100 leading-relaxed mb-2">{s.text}</p>
            <BiasScoreIndicator score={s.score} threshold={samples.threshold} size="sm" alarm={s.alarm} />
            <div className="grid grid-cols-3 gap-1 mt-2 text-[10px] text-slate-300">
              <div>균형 {s.components.party_mention_balance.toFixed(2)}</div>
              <div>인용 {s.components.citation_score.toFixed(2)}</div>
              <div>단정 감점 {s.components.assertion_penalty.toFixed(2)}</div>
            </div>
            {s.components.parties_mentioned.length > 0 && (
              <div className="text-[10px] text-slate-400 mt-1">
                언급된 정당: {s.components.parties_mentioned.join(' · ')}
                {' '}({s.components.total_party_mentions}회)
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}


function LiveScoreForm() {
  const [text, setText] = useState('');
  const [scoring, setScoring] = useState(false);
  const [result, setResult] = useState<NeutralityScoreResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScore = useCallback(async () => {
    if (!text.trim()) return;
    setScoring(true);
    setError(null);
    setResult(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const r = await neutralityApi.score(text, personaId);
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScoring(false);
    }
  }, [text]);

  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <h2 className="text-sm font-bold text-white mb-2">실시간 채점</h2>
      <p className="text-xs text-slate-400 mb-3">
        텍스트를 입력해 political_balance_score 계산. (max 4000자)
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="예) 더불어민주당과 국민의힘이 청년 주거 정책에서 96%의 일치를 보였다. (출처: 국회 OpenAPI 2026-04)"
        className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md p-2 font-sans text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <button
        onClick={handleScore}
        disabled={!text.trim() || scoring}
        className="mt-2 text-xs px-3 py-1.5 rounded-md bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:bg-slate-700 disabled:cursor-not-allowed"
      >
        {scoring ? '채점 중…' : '채점'}
      </button>
      {error && (
        <div className="mt-2 text-xs text-red-200 bg-red-500/15 border border-red-400/40 rounded p-2">
          {error}
        </div>
      )}
      {result && (
        <div className="mt-3 border-t pt-3 border-slate-800">
          <BiasScoreIndicator score={result.score} alarm={result.alarm} size="md" />
          <p className="text-xs text-slate-200 mt-2">{result.interpretation}</p>
          <div className="grid grid-cols-3 gap-2 mt-2 text-[10px]">
            <ComponentBox
              label="정당 균형"
              value={result.components.party_mention_balance}
              count={result.components.total_party_mentions}
              unit="회"
            />
            <ComponentBox
              label="출처 인용"
              value={result.components.citation_score}
              count={result.components.citation_count}
              unit="건"
            />
            <ComponentBox
              label="단정 감점"
              value={result.components.assertion_penalty}
              count={result.components.assertion_count}
              unit="개"
            />
          </div>
          {result.blocked_topics.length > 0 && (
            <div className="mt-2 text-[10px] text-red-200 bg-red-500/15 border border-red-400/40 rounded p-2">
              차단 사유: {result.blocked_topics.join(', ')}
            </div>
          )}
        </div>
      )}
    </section>
  );
}


function ComponentBox({
  label,
  value,
  count,
  unit,
}: {
  label: string;
  value: number;
  count: number;
  unit: string;
}) {
  return (
    <div className="bg-slate-800/40 rounded p-2">
      <div className="text-slate-400">{label}</div>
      <div className="text-sm font-bold text-white">{value.toFixed(2)}</div>
      <div className="text-slate-500">{count}{unit}</div>
    </div>
  );
}


function RecentTraceSection({ recent }: { recent: NeutralityRecentResponse }) {
  const c = recent.counters;
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
      <h2 className="text-sm font-bold text-white mb-2">최근 LLM 호출 trace</h2>
      <div className="grid grid-cols-4 gap-2 mb-3 text-[10px]">
        <Counter label="총 호출" value={c.total_invocations} />
        <Counter label="평균 점수" value={c.avg_balance_score.toFixed(2)} />
        <Counter label="차단" value={c.total_blocked} />
        <Counter label="알람" value={c.total_alarms_low_balance} />
      </div>
      {recent.traces.length === 0 ? (
        <p className="text-xs text-slate-500 italic">
          buffer 비어있음. LLM 호출이 발생하면 자동 기록.
        </p>
      ) : (
        <div className="space-y-1">
          {recent.traces.map((t, i) => (
            <div key={`${t.ts_iso}-${i}`} className="flex items-center gap-2 text-[10px]">
              <span className="text-slate-500 font-mono">{t.ts_iso.slice(11, 19)}</span>
              <span className="font-mono">{t.scenario_code}</span>
              <span className="text-slate-300">{t.persona_id}</span>
              <span
                className={
                  'ml-auto font-semibold ' +
                  (t.alarm ? 'text-amber-300' : 'text-slate-100')
                }
              >
                {t.political_balance_score.toFixed(2)}
                {t.alarm && ' ⚠'}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


function Counter({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-slate-800/40 rounded p-2">
      <div className="text-slate-400">{label}</div>
      <div className="text-sm font-bold text-white">{value}</div>
    </div>
  );
}
