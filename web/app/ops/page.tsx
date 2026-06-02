'use client';

/**
 * 운영 콘솔 페이지 - 5 패널 (Phase 5 Track 5-2).
 *
 * 시연자가 데이터 적재 / 가드레일 통계 / 메모리 / 평가 / trace 한눈에 확인.
 * '새로고침' 버튼으로 live 갱신.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  opsApi,
  type GuardrailPanel,
  type IngestPanel,
  type MemoryPanel,
  type QualityPanel,
  type TracePanel,
} from '../../lib/ops-client';

export default function OpsPage() {
  const [ingest, setIngest] = useState<IngestPanel | null>(null);
  const [guardrail, setGuardrail] = useState<GuardrailPanel | null>(null);
  const [memory, setMemory] = useState<MemoryPanel | null>(null);
  const [quality, setQuality] = useState<QualityPanel | null>(null);
  const [trace, setTrace] = useState<TracePanel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [i, g, m, q, t] = await Promise.all([
        opsApi.ingest(),
        opsApi.guardrail(),
        opsApi.memory(),
        opsApi.wowQuality(),
        opsApi.trace(20),
      ]);
      setIngest(i);
      setGuardrail(g);
      setMemory(m);
      setQuality(q);
      setTrace(t);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div>
      <header className="mb-6 flex items-center justify-between">
        <div>
          <div className="text-sm text-slate-500 font-mono mb-1">/ops</div>
          <h1 className="text-2xl font-bold">운영 콘솔</h1>
          <p className="text-sm text-slate-300 mt-1">
            5 패널 - 데이터 적재 · 가드레일 · 메모리 · 평가 · LLM trace.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '갱신 중…' : '새로고침'}
        </button>
      </header>

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="① 적재 (Ingest)">{ingest && <IngestView data={ingest} />}</Panel>
        <Panel title="② 가드레일 (Guardrail)">
          {guardrail && <GuardrailView data={guardrail} />}
        </Panel>
        <Panel title="③ 메모리 (AgentCore)">{memory && <MemoryView data={memory} />}</Panel>
        <Panel title="④ wow-query 품질">
          {quality && <QualityView data={quality} />}
        </Panel>
        <Panel title="⑤ LLM Trace" wide>
          {trace && <TraceView data={trace} />}
        </Panel>
      </div>
    </div>
  );
}


function Panel({ title, wide, children }: { title: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <section
      className={
        'border border-slate-800 rounded-lg bg-slate-900/40 p-4 ' + (wide ? 'lg:col-span-2' : '')
      }
    >
      <h2 className="font-semibold text-white mb-3 pb-2 border-b border-slate-800">{title}</h2>
      <div className="text-sm">{children}</div>
    </section>
  );
}


function IngestView({ data }: { data: IngestPanel }) {
  const totalFiles = Object.keys(data.file_counts).length;
  const totalNodes = Object.values(data.file_counts).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="NDJSON 파일" value={String(totalFiles)} />
        <Stat label="총 노드" value={totalNodes.toLocaleString()} />
      </div>
      {Object.keys(data.source_distribution).length > 0 && (
        <div className="text-xs text-slate-300 pt-2">
          출처 분포:{' '}
          {Object.entries(data.source_distribution)
            .map(([s, n]) => `${s}=${n}`)
            .join(' · ')}
        </div>
      )}
      <details className="text-xs text-slate-400">
        <summary className="cursor-pointer hover:text-slate-200">파일별 카운트</summary>
        <ul className="mt-1 space-y-0.5">
          {Object.entries(data.file_counts).map(([f, n]) => (
            <li key={f} className="font-mono">
              {f}: {n.toLocaleString()}
            </li>
          ))}
        </ul>
      </details>
      <p className="text-xs text-slate-500 italic">{data.note}</p>
    </div>
  );
}


function GuardrailView({ data }: { data: GuardrailPanel }) {
  const lowBalance = data.avg_balance_score < data.threshold;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="LLM 호출" value={String(data.total_invocations)} />
        <Stat label="차단" value={String(data.total_blocked)} />
        <Stat label="알람" value={String(data.total_alarms_low_balance)} />
      </div>
      <div className="text-sm">
        평균 balance score:{' '}
        <span className={lowBalance ? 'text-warn font-bold' : 'text-badge-real font-bold'}>
          {data.avg_balance_score.toFixed(3)}
        </span>
        <span className="text-xs text-slate-400 ml-2">(임계 {data.threshold})</span>
      </div>
      {Object.keys(data.blocked_by_topic).length > 0 && (
        <div className="text-xs text-slate-300">
          차단 토픽:{' '}
          {Object.entries(data.blocked_by_topic)
            .map(([t, n]) => `${t}=${n}`)
            .join(', ')}
        </div>
      )}
    </div>
  );
}


function MemoryView({ data }: { data: MemoryPanel }) {
  return (
    <div className="space-y-2">
      <Stat label="활성 세션 (추정)" value={String(data.active_sessions_estimate)} />
      <div className="text-xs text-slate-300">
        Namespaces: {data.namespaces.join(' / ')}
      </div>
      <div className="text-xs text-slate-400 font-mono break-all">
        store: {data.store_id ?? '(미설정)'}
      </div>
      <p className="text-xs text-slate-500 italic">{data.note}</p>
    </div>
  );
}


function QualityView({ data }: { data: QualityPanel }) {
  const passOk = data.pass_rate >= 0.85;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="평가 케이스" value={String(data.total_cases)} />
        <Stat
          label="통과율"
          value={`${(data.pass_rate * 100).toFixed(1)}%`}
          tone={data.total_cases === 0 ? 'muted' : passOk ? 'good' : 'warn'}
        />
      </div>
      {data.avg_balance_score !== null && (
        <div className="text-sm">
          평균 balance: <strong>{data.avg_balance_score.toFixed(3)}</strong>
        </div>
      )}
      <p className="text-xs text-slate-500 italic">{data.note}</p>
    </div>
  );
}


function TraceView({ data }: { data: TracePanel }) {
  if (data.entries.length === 0) {
    return (
      <p className="text-slate-400">
        링버퍼 비어있음 (size {data.buffer_size}). LLM 호출 시 자동 기록.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-slate-400 border-b border-slate-800">
          <tr>
            <th className="text-left p-1">시각</th>
            <th className="text-left p-1">persona</th>
            <th className="text-left p-1">scn</th>
            <th className="text-right p-1">score</th>
            <th className="text-center p-1">alarm</th>
            <th className="text-right p-1">ms</th>
          </tr>
        </thead>
        <tbody>
          {data.entries.map((e, idx) => (
            <tr key={idx} className="border-b border-slate-800">
              <td className="p-1 text-slate-400">{e.ts_iso.slice(11, 19)}</td>
              <td className="p-1">{e.persona_id}</td>
              <td className="p-1 font-mono">{e.scenario_code}</td>
              <td className="p-1 text-right font-mono">{e.political_balance_score.toFixed(2)}</td>
              <td className="p-1 text-center">
                {e.alarm ? (
                  <span className="text-warn" title={e.alarm_reason ?? ''}>
                    ⚠
                  </span>
                ) : (
                  '·'
                )}
              </td>
              <td className="p-1 text-right text-slate-400 font-mono">{e.duration_ms}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function Stat({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'warn' | 'muted';
}) {
  const toneCls =
    tone === 'good'
      ? 'text-badge-real'
      : tone === 'warn'
      ? 'text-warn'
      : tone === 'muted'
      ? 'text-slate-500'
      : 'text-white';
  return (
    <div className="border border-slate-800 bg-slate-800/40 rounded-md px-2 py-1.5">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-lg font-bold ${toneCls}`}>{value}</div>
    </div>
  );
}
