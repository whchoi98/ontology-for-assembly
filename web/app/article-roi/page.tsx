'use client';

/**
 * 시나리오 G - 기사 ROI.
 *
 * ROI 내림차순 기사 리스트 + 선택 시 디테일 - metrics 4 박스 + 6 페르소나 KPI 카드.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  articleRoiApi,
  type RoiListResponse,
  type RoiDetailResponse,
  type RoiEntry,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

const PAGE_SIZE = 10;


export default function ArticleRoiPage() {
  const [list, setList] = useState<RoiListResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RoiDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const r = await articleRoiApi.list({ offset, limit: PAGE_SIZE, personaId });
      setList(r);
      if (r.entries.length > 0 && !selectedId) {
        setSelectedId(r.entries[0].article_id);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [offset, selectedId]);

  useEffect(() => { void loadList(); }, [loadList]);

  // WAF SizeRestrictions_BODY (8KB) 우회 — 60건 entries 대신 summary + top-3만 context로 전달
  const insightCtx = useMemo(() => {
    if (!list) return null;
    const det = detail?.entry;
    return {
      article_id: det?.article_id ?? list.entries[0]?.article_id ?? '',
      total_articles: list.total,
      persona_note: list.persona_note,
      top_3_entries: list.entries.slice(0, 3).map((e) => ({
        article_id: e.article_id,
        title: e.title,
        primary_topic: e.primary_topic,
        roi_pct: e.metrics.roi_pct,
      })),
      selected_detail: det ? {
        article_id: det.article_id,
        title: det.title,
        primary_topic: det.primary_topic,
        roi_pct: det.metrics.roi_pct,
        reach_pv: det.metrics.reach_pv,
        cost_won: det.metrics.cost_won,
        conv_value_won: det.metrics.conv_value_won,
      } : null,
    };
  }, [list, detail]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const personaId = readPersonaIdSync() as PersonaId;
    articleRoiApi.detail(selectedId, personaId).then(setDetail).catch((e) => setError((e as Error).message));
  }, [selectedId]);

  return (
    <div>
      <ScenarioHero code="G" />

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
            {/* 리스트 */}
            <section className="lg:col-span-2 space-y-2">
              <div className="flex justify-between items-baseline text-xs text-slate-400 mb-1">
                <span>총 {list.total}건 · 페이지 {Math.floor(offset / PAGE_SIZE) + 1}</span>
                <div className="flex gap-1">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ←
                  </button>
                  <button
                    disabled={offset + PAGE_SIZE >= list.total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    →
                  </button>
                </div>
              </div>
              {list.entries.map((e) => (
                <RoiRow
                  key={e.article_id}
                  entry={e}
                  selected={selectedId === e.article_id}
                  onClick={() => setSelectedId(e.article_id)}
                />
              ))}
            </section>

            {/* 디테일 */}
            <section className="lg:col-span-3">
              {detail ? <RoiDetail detail={detail} /> : <p className="text-sm text-slate-500">기사를 선택하세요.</p>}
            </section>
          </div>
        </>
      )}
      <AIInsightPanel scenarioCode="G" context={insightCtx} autoGenerate />
    </div>
  );
}


function RoiRow({
  entry, selected, onClick,
}: { entry: RoiEntry; selected: boolean; onClick: () => void }) {
  const positive = entry.metrics.roi_pct >= 0;
  return (
    <button
      onClick={onClick}
      className={
        'block w-full text-left border rounded-md p-3 transition-colors ' +
        (selected
          ? 'border-blue-500 bg-blue-500/15'
          : 'border-slate-800 bg-slate-900/40 hover:border-slate-600')
      }
    >
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] font-mono text-slate-500">{entry.article_id}</span>
        <span className={`text-xs font-mono font-bold ${positive ? 'text-emerald-300' : 'text-red-300'}`}>
          ROI {entry.metrics.roi_pct.toFixed(1)}%
        </span>
      </div>
      <div className="text-sm font-semibold text-white line-clamp-2">{entry.title}</div>
      <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-400">
        {entry.primary_topic && (
          <span className="px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-400/40 text-purple-200">
            {entry.primary_topic}
          </span>
        )}
        <span>PV {entry.metrics.reach_pv.toLocaleString()}</span>
        <span>공유 {entry.metrics.reach_share}</span>
      </div>
    </button>
  );
}


function RoiDetail({ detail }: { detail: RoiDetailResponse }) {
  const e = detail.entry;
  const positive = e.metrics.roi_pct >= 0;
  return (
    <div className="space-y-4">
      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <div className="flex items-baseline gap-2 mb-2">
          <h2 className="text-sm font-bold text-white flex-1">{e.title}</h2>
          <span className={`text-lg font-mono font-bold ${positive ? 'text-emerald-300' : 'text-red-300'}`}>
            ROI {e.metrics.roi_pct.toFixed(1)}%
          </span>
        </div>
        {e.primary_topic && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-400/40 text-purple-200 font-medium">
            {e.primary_topic}
          </span>
        )}
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h3 className="text-xs uppercase text-slate-400 mb-2">Metrics</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-[11px]">
          <Metric label="비용" value={`${e.metrics.cost_won.toLocaleString()}원`} color="text-slate-200" />
          <Metric label="페이지뷰" value={e.metrics.reach_pv.toLocaleString()} color="text-blue-300" />
          <Metric label="공유" value={e.metrics.reach_share.toString()} color="text-cyan-300" />
          <Metric label="체류 시간" value={`${e.metrics.avg_dwell_sec}s`} color="text-pink-300" />
          <Metric label="전환 가치" value={`${e.metrics.conv_value_won.toLocaleString()}원`} color="text-emerald-300" />
          <Metric label="ROI" value={`${e.metrics.roi_pct.toFixed(1)}%`} color={positive ? 'text-emerald-300' : 'text-red-300'} />
        </div>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h3 className="text-xs uppercase text-slate-400 mb-2">6 페르소나 KPI</h3>
        <div className="space-y-2">
          {e.persona_kpis.map((k) => (
            <div key={k.persona_id} className="border-l-2 border-slate-700 pl-3 py-1">
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-semibold text-white">{k.name_kr}</span>
                <span className="text-[10px] text-slate-400 font-mono">{k.persona_id}</span>
                <span className="ml-auto text-xs font-mono font-bold text-blue-300">{k.kpi_value}</span>
              </div>
              <div className="text-[10px] text-slate-400">{k.kpi_label}</div>
              <p className="text-[10px] text-slate-300 italic mt-0.5">{k.note}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-3">
        <div className="text-[10px] uppercase text-slate-400 mb-1">출처</div>
        <div className="flex flex-wrap gap-1">
          {e.sources.map((s) => (
            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">{s}</span>
          ))}
        </div>
      </div>

      {detail.extras.follow_up_hint && (
        <ExtraBox color="amber" label="후속 취재" text={detail.extras.follow_up_hint} />
      )}
      {detail.extras.ad_revenue_hint && (
        <ExtraBox color="orange" label="광고 매출" text={detail.extras.ad_revenue_hint} />
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


function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-slate-800/40 rounded p-2">
      <div className="text-slate-400 text-[10px]">{label}</div>
      <div className={`font-semibold font-mono ${color ?? 'text-white'}`}>{value}</div>
    </div>
  );
}


function ExtraBox({ color, label, text }: { color: string; label: string; text: string }) {
  const colors: Record<string, string> = {
    amber: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
    orange: 'border-orange-400/40 bg-orange-500/15 text-orange-200',
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
