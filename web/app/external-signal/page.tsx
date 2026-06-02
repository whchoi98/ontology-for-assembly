'use client';

/**
 * 시나리오 J - 외부 신호 융합.
 *
 * 3 패턴 (signal_leads · legislation_leads · decoupled) 카드 + 선택 시
 * 12주 dual-line SVG 시계열 + narrative + 페르소나 hint.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  externalSignalApi,
  type FusionListResponse,
  type FusionDetailResponse,
  type FusionPattern,
  type TopicFusion,
  type WeeklyPoint,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

const PATTERN_TINT: Record<FusionPattern, { bg: string; text: string; ring: string }> = {
  signal_leads:     { bg: 'bg-blue-500/15',   text: 'text-blue-300',   ring: 'ring-blue-400' },
  legislation_leads: { bg: 'bg-emerald-500/15', text: 'text-emerald-200', ring: 'ring-emerald-400' },
  decoupled:        { bg: 'bg-slate-800/40',   text: 'text-slate-200',   ring: 'ring-gray-400' },
};


export default function ExternalSignalPage() {
  const [list, setList] = useState<FusionListResponse | null>(null);
  const [patternFilter, setPatternFilter] = useState<FusionPattern | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<FusionDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const r = await externalSignalApi.list({
        pattern: patternFilter ?? undefined, personaId,
      });
      setList(r);
      if (r.fusions.length > 0 && !selectedId) {
        setSelectedId(r.fusions[0].fusion_id);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [patternFilter, selectedId]);

  useEffect(() => { void loadList(); }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const personaId = readPersonaIdSync() as PersonaId;
    externalSignalApi
      .detail(selectedId, personaId)
      .then(setDetail)
      .catch((e) => setError((e as Error).message));
  }, [selectedId]);

  return (
    <div>
      <ScenarioHero code="J" subtitle="12주 시계열 · 3 패턴" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {/* 패턴 필터 */}
      <div className="mb-4">
        <div className="text-xs uppercase text-slate-400 mb-1">패턴 필터</div>
        <div className="flex flex-wrap gap-1.5">
          <PatternChip
            active={patternFilter === null}
            onClick={() => setPatternFilter(null)}
            label="전체"
          />
          <PatternChip
            active={patternFilter === 'signal_leads'}
            onClick={() => setPatternFilter('signal_leads')}
            label="외부 시그널 선행"
            color="blue"
          />
          <PatternChip
            active={patternFilter === 'legislation_leads'}
            onClick={() => setPatternFilter('legislation_leads')}
            label="입법 선행"
            color="emerald"
          />
          <PatternChip
            active={patternFilter === 'decoupled'}
            onClick={() => setPatternFilter('decoupled')}
            label="비상관"
            color="gray"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* 리스트 */}
        <section className="lg:col-span-2 space-y-2">
          {list && (
            <>
              <p className="text-xs text-amber-200 bg-amber-500/10 border border-amber-400/30 rounded p-2 mb-2">
                {list.persona_note}
              </p>
              {list.fusions.map((f) => (
                <FusionCard
                  key={f.fusion_id}
                  fusion={f}
                  selected={selectedId === f.fusion_id}
                  onClick={() => setSelectedId(f.fusion_id)}
                />
              ))}
            </>
          )}
        </section>

        {/* 디테일 */}
        <section className="lg:col-span-3">
          {detail ? (
            <FusionDetail detail={detail} />
          ) : (
            <p className="text-sm text-slate-500">패턴을 선택하세요.</p>
          )}
        </section>
      </div>
      <AIInsightPanel scenarioCode="J" context={list} />
    </div>
  );
}


function PatternChip({
  active, onClick, label, color = 'blue',
}: { active: boolean; onClick: () => void; label: string; color?: string }) {
  const activeStyle: Record<string, string> = {
    blue: 'border-blue-500 bg-blue-500/15 text-blue-300',
    emerald: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200',
    gray: 'border-slate-500 bg-slate-800 text-slate-100',
  };
  return (
    <button
      onClick={onClick}
      className={
        'text-xs px-2.5 py-1.5 rounded-md border font-medium ' +
        (active
          ? activeStyle[color] ?? activeStyle.blue
          : 'border-slate-800 bg-slate-900/40 text-slate-200 hover:bg-slate-800/40')
      }
    >
      {label}
    </button>
  );
}


function FusionCard({
  fusion, selected, onClick,
}: { fusion: TopicFusion; selected: boolean; onClick: () => void }) {
  const tint = PATTERN_TINT[fusion.pattern];
  return (
    <button
      onClick={onClick}
      className={
        `block w-full text-left border rounded-md p-3 transition-all ${tint.bg} ` +
        (selected
          ? `border-slate-600 ring-2 ${tint.ring}`
          : 'border-slate-800 hover:border-slate-600')
      }
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-semibold text-white">{fusion.topic_name}</span>
        <span className={`text-[10px] font-medium ${tint.text}`}>
          corr {fusion.correlation_hint.toFixed(2)}
        </span>
      </div>
      <div className={`text-[11px] ${tint.text} mb-2`}>{fusion.pattern_label}</div>
      <Sparkline weeks={fusion.weeks} pattern={fusion.pattern} compact />
    </button>
  );
}


function FusionDetail({ detail }: { detail: FusionDetailResponse }) {
  const f = detail.fusion;
  return (
    <div className="space-y-4">
      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <div className="flex items-center gap-2 mb-2">
          <h2 className="text-lg font-bold text-white">{f.topic_name}</h2>
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PATTERN_TINT[f.pattern].bg} ${PATTERN_TINT[f.pattern].text}`}>
            {f.pattern_label}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2 mb-3 text-[11px]">
          <Stat label="signal peak" value={f.peak_signal_week} />
          <Stat label="legislation peak" value={f.peak_legislation_week} />
          <Stat label="lag (주)" value={f.lag_weeks.toString()} />
        </div>
        <Sparkline weeks={f.weeks} pattern={f.pattern} />
        <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-300">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-blue-500" /> 외부 시그널
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-orange-500" /> 입법 활동
          </span>
        </div>
      </div>

      <div className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
        <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">narrative</div>
        <p className="text-xs text-amber-100 leading-relaxed">{f.narrative}</p>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-3">
        <div className="text-[10px] uppercase text-slate-400 mb-1">데이터 출처</div>
        <div className="flex flex-wrap gap-1">
          {f.sources.map((s) => (
            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">
              {s}
            </span>
          ))}
        </div>
      </div>

      {detail.extras.follow_up_hint && (
        <ExtraBox color="amber" label="후속 취재" text={detail.extras.follow_up_hint} />
      )}
      {detail.extras.analysis_hint && (
        <ExtraBox color="cyan" label="분석 hint" text={detail.extras.analysis_hint} />
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


function Sparkline({
  weeks, pattern, compact = false,
}: { weeks: WeeklyPoint[]; pattern: FusionPattern; compact?: boolean }) {
  const W = compact ? 220 : 460;
  const H = compact ? 50 : 140;
  const PAD = compact ? 2 : 18;

  const { signalPath, billPath } = useMemo(() => {
    if (weeks.length === 0) return { signalPath: '', billPath: '' };
    const maxSignal = Math.max(...weeks.map((p) => p.signal_count), 1);
    const maxBill = Math.max(...weeks.map((p) => p.bill_count), 1);
    const stepX = (W - 2 * PAD) / Math.max(1, weeks.length - 1);
    const innerH = H - 2 * PAD;
    const toPath = (key: 'signal_count' | 'bill_count', max: number) =>
      weeks
        .map((p, i) => {
          const x = PAD + i * stepX;
          const y = PAD + innerH - (p[key] / max) * innerH;
          return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
        })
        .join(' ');
    return {
      signalPath: toPath('signal_count', maxSignal),
      billPath: toPath('bill_count', maxBill),
    };
  }, [weeks, W, H, PAD]);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-auto"
      role="img"
      aria-label={`${pattern} 시계열`}
    >
      {!compact && (
        <>
          {/* y-axis baseline */}
          <line
            x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD}
            stroke="#e5e7eb" strokeWidth="1"
          />
          {/* x labels - 첫·중간·마지막 */}
          {[0, Math.floor(weeks.length / 2), weeks.length - 1].map((i) => {
            if (!weeks[i]) return null;
            const x = PAD + i * ((W - 2 * PAD) / Math.max(1, weeks.length - 1));
            return (
              <text
                key={i} x={x} y={H - 2}
                textAnchor="middle"
                fontSize="9"
                fill="#9ca3af"
              >
                {weeks[i].week_iso.replace('2026-', '')}
              </text>
            );
          })}
        </>
      )}
      <path d={signalPath} fill="none" stroke="#3b82f6" strokeWidth="1.5" />
      <path d={billPath} fill="none" stroke="#f97316" strokeWidth="1.5" />
    </svg>
  );
}


function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-800/40 rounded p-2">
      <div className="text-slate-400 text-[10px]">{label}</div>
      <div className="font-semibold text-white font-mono">{value}</div>
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
    <div className={`border p-3 rounded ${colors[color] ?? colors.gray}`}>
      <div className="text-[10px] uppercase font-semibold mb-1">{label}</div>
      <p className="text-xs leading-relaxed">{text}</p>
    </div>
  );
}
