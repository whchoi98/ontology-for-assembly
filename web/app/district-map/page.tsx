'use client';

/**
 * 시나리오 H - 지역구 지도.
 *
 * 17 시도 KoreaChoropleth + 선택된 시도 디테일 (의원 리스트 + 정당 분포 + 활동 stats).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { KoreaChoropleth } from '../../components/KoreaChoropleth';
import {
  districtMapApi,
  type DistrictMapSummaryResponse,
  type DistrictMapDetailResponse,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

export default function DistrictMapPage() {
  const [summary, setSummary] = useState<DistrictMapSummaryResponse | null>(null);
  const [detail, setDetail] = useState<DistrictMapDetailResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string>('seoul');
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const s = await districtMapApi.summary(personaId);
      setSummary(s);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const loadDetail = useCallback(async (key: string) => {
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const d = await districtMapApi.detail(key, personaId);
      setDetail(d);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    void loadDetail(selectedKey);
  }, [selectedKey, loadDetail]);

  // sido_id stable identifier로 AIInsightPanel useMemo가 인식 + WAF body size 우회 (전체 17 시도 보내지 않음)
  const insightCtx = useMemo(() => {
    if (!detail) return null;
    return {
      sido_id: detail.sido.key,
      sido_name: detail.sido.name_kr,
      member_count: detail.sido.member_count,
      density_label: detail.sido.density_label,
      activity_proposed: detail.sido.activity.proposed,
      activity_voted: detail.sido.activity.voted,
      activity_statements: detail.sido.activity.statements,
      top_member_names: detail.members.slice(0, 5).map((m) => m.name),
      top_member_parties: Array.from(new Set(detail.members.map((m) => m.party))).slice(0, 4),
      total_districts_nation: summary?.total_districts ?? 17,
      total_members_nation: summary?.total_members ?? 286,
    };
  }, [detail, summary]);

  return (
    <div>
      <ScenarioHero code="H" subtitle="17 시도 SVG" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm font-bold text-white">지도 (지역구 수)</h2>
              <span className="text-xs text-slate-400">
                총 {summary.total_members}명 · {summary.total_districts} 시도
              </span>
            </div>
            <KoreaChoropleth
              sido={summary.sido}
              selectedKey={selectedKey}
              onSelect={setSelectedKey}
            />
            {summary.persona_hint && (
              <div className="mt-3 text-[11px] text-amber-200 bg-amber-500/10 border border-amber-400/30 rounded p-2">
                {summary.persona_hint}
              </div>
            )}
          </section>

          <section className="space-y-4">
            {detail ? (
              <SidoDetailPanel detail={detail} />
            ) : (
              <p className="text-sm text-slate-500">시도를 선택하세요.</p>
            )}
          </section>
        </div>
      )}
      {insightCtx ? (
        <AIInsightPanel scenarioCode="H" context={insightCtx} autoGenerate />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          시도를 선택하면 해당 지역에 맞는 AI 인사이트가 표시됩니다.
        </div>
      )}
    </div>
  );

  function _placeholder() { /* helper scope */ }
}


function MemberRow({ m }: { m: DistrictMapDetailResponse['members'][number] }) {
  const [open, setOpen] = useState(false);
  const photoUrl = `https://www.assembly.go.kr/static/portal/img/openassm/${m.person_id}.jpg`;
  return (
    <div className="border-l-2 border-blue-500 pl-3 py-1">
      <div className="flex items-center gap-2 mb-0.5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={photoUrl}
          alt={m.name}
          className="w-8 h-8 rounded-full object-cover bg-slate-800 flex-shrink-0"
          onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.3'; }}
        />
        <div className="flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold text-white">{m.name}</span>
            <span className="text-[10px] text-slate-400 font-mono">{m.person_id}</span>
            <span className="text-[10px] text-slate-400">{m.party}</span>
          </div>
          <div className="text-[11px] text-slate-200">{m.district}</div>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-[10px] px-2 py-1 rounded border border-slate-700 bg-slate-800 hover:border-blue-400 hover:bg-slate-700 text-slate-300 hover:text-blue-200 transition-colors"
        >
          {open ? '활동 요약 닫기 ▴' : '활동 요약 ▾'}
        </button>
      </div>
      {open && (
        <div className="mt-2 ml-10 text-[11px] text-slate-200 bg-slate-900/60 border border-slate-700 rounded p-2 leading-relaxed">
          {m.activity_summary}
        </div>
      )}
    </div>
  );
}


function SidoDetailPanel({ detail }: { detail: DistrictMapDetailResponse }) {
  const s = detail.sido;
  return (
    <>
      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <div className="flex items-center gap-2 mb-2">
          <h2 className="text-lg font-bold text-white">{s.name_kr}</h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200 font-mono">
            KOSTAT {s.kostat_code}
          </span>
          <span
            className={
              'text-[10px] px-1.5 py-0.5 rounded font-medium ' +
              (s.density_label === '매우 높음'
                ? 'bg-blue-700 text-white'
                : s.density_label === '높음'
                  ? 'bg-blue-500 text-white'
                  : s.density_label === '보통'
                    ? 'bg-blue-500/30 border border-blue-400/50 text-blue-100'
                    : 'bg-blue-500/20 border border-blue-400/40 text-slate-200')
            }
          >
            {s.density_label}
          </span>
        </div>
        <p className="text-xs text-slate-200 leading-relaxed mb-3">{detail.summary}</p>

        <h3 className="text-xs uppercase text-slate-400 mb-1.5">정당 분포</h3>
        <div className="space-y-1 mb-3">
          {Object.entries(s.parties).map(([party, count]) => (
            <PartyBar key={party} party={party} count={count} total={s.member_count} />
          ))}
        </div>

        <h3 className="text-xs uppercase text-slate-400 mb-1.5">활동 통계 (회기 누적)</h3>
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          <div className="bg-slate-800/40 rounded p-2">
            <div className="text-slate-400">발의</div>
            <div className="text-lg font-bold text-blue-300">{s.activity.proposed}</div>
          </div>
          <div className="bg-slate-800/40 rounded p-2">
            <div className="text-slate-400">표결</div>
            <div className="text-lg font-bold text-orange-300">{s.activity.voted}</div>
          </div>
          <div className="bg-slate-800/40 rounded p-2">
            <div className="text-slate-400">발언</div>
            <div className="text-lg font-bold text-pink-300">{s.activity.statements}</div>
          </div>
        </div>
      </div>

      {detail.members.length > 0 ? (
        <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
          <h3 className="text-xs uppercase text-slate-400 mb-2">
            대표 의원 <span className="text-slate-500">({detail.members.length}명, composite score 정렬)</span>
          </h3>
          <div className="space-y-2">
            {detail.members.map((m) => (
              <MemberRow key={m.person_id} m={m} />
            ))}
          </div>
        </div>
      ) : (
        <div className="border border-amber-500/30 bg-amber-500/10 rounded-lg p-4 text-xs text-amber-100">
          ⚠️ 해당 시도에 매칭된 의원 데이터 없음 — 22대 임기 286명 디렉토리에서 *지역구 prefix 매칭 실패*.
          {' '}fix 진행 중.
        </div>
      )}

      {detail.extras.follow_up_hint && (
        <div className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
          <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">후속 취재</div>
          <p className="text-xs text-amber-100">{detail.extras.follow_up_hint}</p>
        </div>
      )}
      {detail.extras.premium_cta && (
        <div className="border-l-4 border-purple-400 bg-purple-500/15 p-3 rounded">
          <p className="text-xs text-purple-100">{detail.extras.premium_cta}</p>
        </div>
      )}
      {detail.extras.guide_hint && (
        <div className="border-l-4 border-emerald-400/50 bg-emerald-500/10 p-3 rounded">
          <p className="text-xs text-emerald-100">{detail.extras.guide_hint}</p>
        </div>
      )}
      {detail.extras.api_response_hint && (
        <div className="border-l-4 border-slate-600 bg-slate-800/40 p-3 rounded">
          <p className="text-xs text-slate-200 font-mono">{detail.extras.api_response_hint}</p>
        </div>
      )}
    </>
  );
}


function PartyBar({ party, count, total }: { party: string; count: number; total: number }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div>
      <div className="flex justify-between text-[11px] mb-0.5">
        <span className="text-slate-200">{party}</span>
        <span className="text-slate-400 font-mono">{count} ({pct.toFixed(0)}%)</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className="h-1.5 bg-slate-500 rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
