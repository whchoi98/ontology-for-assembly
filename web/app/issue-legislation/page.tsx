'use client';

/**
 * 시나리오 N - 이슈×입법 상관.
 *
 * 8 이슈 × 4 활동 유형 매트릭스 (heatmap) + top 5 강한 결합 + 페르소나 hint.
 */
import React, { useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  issueLegislationApi,
  type IssueLegislationMatrix,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';


const ACTIVITY_KR: Record<string, string> = {
  proposed: '발의',
  voted: '표결',
  statements: '발언',
  committee_activity: '위원회 활동',
};


export default function IssueLegislationPage() {
  const [matrix, setMatrix] = useState<IssueLegislationMatrix | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const personaId = readPersonaIdSync() as PersonaId;
    issueLegislationApi
      .matrix(personaId)
      .then(setMatrix)
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <ScenarioHero code="N" subtitle="8 × 4 heatmap" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {matrix && (
        <>
          <p className="text-xs text-amber-200 bg-amber-500/10 border border-amber-400/30 rounded p-2 mb-4">
            {matrix.persona_note}
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 매트릭스 */}
            <section className="lg:col-span-2 border border-slate-800 rounded-lg bg-slate-900/40 p-4">
              <h2 className="text-sm font-bold text-white mb-3">heatmap</h2>
              <MatrixHeatmap matrix={matrix} />
              <div className="flex items-center gap-3 mt-3 text-[10px] text-slate-300">
                <span className="font-medium">강도:</span>
                {['낮음', '보통', '높음', '매우 높음'].map((tier, i) => (
                  <span key={tier} className="flex items-center gap-1">
                    <span
                      className="inline-block w-3 h-3 rounded"
                      style={{ backgroundColor: heatmapColor(i * 33 + 5) }}
                    />
                    {tier}
                  </span>
                ))}
              </div>
            </section>

            {/* top 5 */}
            <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
              <h2 className="text-sm font-bold text-white mb-2">강한 결합 Top 5</h2>
              <div className="space-y-2">
                {matrix.top_correlations.map((c, i) => (
                  <CorrelationCard key={`${c.issue_id}-${c.activity}`} corr={c} rank={i + 1} />
                ))}
              </div>
            </section>
          </div>

          <div className="mt-4 border border-slate-800 rounded-lg bg-slate-900/40 p-3">
            <div className="text-[10px] uppercase text-slate-400 mb-1">데이터 출처</div>
            <div className="flex flex-wrap gap-1">
              {matrix.sources.map((s) => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">
                  {s}
                </span>
              ))}
            </div>
          </div>
        </>
      )}
      <AIInsightPanel scenarioCode="N" context={matrix} />
    </div>
  );
}


function heatmapColor(value: number): string {
  const intensity = Math.max(0, Math.min(100, value)) / 100;
  // blue-50 to blue-900 grad
  const r = Math.round(239 - intensity * (239 - 30));
  const g = Math.round(246 - intensity * (246 - 64));
  const b = Math.round(255 - intensity * (255 - 175));
  return `rgb(${r}, ${g}, ${b})`;
}


function MatrixHeatmap({ matrix }: { matrix: IssueLegislationMatrix }) {
  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse w-full">
        <thead>
          <tr>
            <th className="border border-slate-800 px-2 py-1 bg-slate-800/40 text-left">이슈 \ 활동</th>
            {matrix.activity_types.map((a) => (
              <th key={a} className="border border-slate-800 px-2 py-1 bg-slate-800/40 text-center">
                {ACTIVITY_KR[a] ?? a}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((row) => (
            <tr key={row.issue_id}>
              <td className="border border-slate-800 px-2 py-1.5">
                <div className="font-medium text-white">{row.issue_name}</div>
                <div className="text-[10px] text-slate-400">{row.category}</div>
              </td>
              {row.activities.map((a) => {
                const isDominant = a.activity === row.dominant_activity;
                const textColor = a.value >= 50 ? 'text-white' : 'text-white';
                return (
                  <td
                    key={a.activity}
                    className={`border border-slate-800 text-center px-2 py-1.5 font-mono ${textColor}`}
                    style={{ backgroundColor: heatmapColor(a.value) }}
                  >
                    <div className="font-semibold">{a.value}</div>
                    <div className="text-[9px] opacity-80">{a.intensity_label}</div>
                    {isDominant && <div className="text-[9px] opacity-80">★ dominant</div>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function CorrelationCard({
  corr, rank,
}: { corr: import('../../lib/scenario-clients').IssueCorrelation; rank: number }) {
  return (
    <div className="border border-slate-800 rounded p-2">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-[10px] text-slate-500 font-mono w-4">#{rank}</span>
        <span className="text-xs font-semibold text-white">{corr.issue_name}</span>
        <span className="text-[10px] text-slate-400 ml-1">× {ACTIVITY_KR[corr.activity] ?? corr.activity}</span>
        <span className="ml-auto font-mono font-semibold text-blue-300">{corr.intensity}</span>
      </div>
      <div className="text-[10px] text-slate-300 italic mb-1">{corr.correlation_label}</div>
      <p className="text-[10px] text-slate-200 leading-snug">{corr.insight}</p>
    </div>
  );
}
