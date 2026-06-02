'use client';

/**
 * 의원 디렉토리 + 랭킹 (kassembly 패턴, 미디어 다크 톤).
 *
 * 페르소나 tier 시각화:
 * - staff (editorial/data_ai/ad_sales): full 메트릭 + 후속 취재 hint
 * - paid_subscriber: full 메트릭 + PDF/비교 도구 CTA
 * - general_reader (b2c_free): 핵심 메트릭만 + premium 잠금 표시
 * - b2b: API 응답 hint + raw value
 */
import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import type { PersonaId } from '../../lib/personas';

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';


interface MemberAnalytics {
  plenary_attendance_pct: number;
  committee_attendance_pct: number;
  bills_proposed: number;
  bills_co_proposed: number;
  floor_votes: number;
  party_alignment_pct: number;
  statements: number;
  media_mentions_30d: number;
  composite_score: number;
}

interface MemberInfo {
  assembly_id: string;
  name: string;
  party: string;
  district: string;
  district_type: string;
  committee: string | null;
  reelection: string;
  term: number;
  profile_image_url: string;
  analytics: MemberAnalytics;
}

const METRICS: Array<{ key: keyof MemberAnalytics; label: string; suffix: string; pro: boolean }> = [
  { key: 'composite_score',          label: '종합 점수',    suffix: '',     pro: false },
  { key: 'plenary_attendance_pct',   label: '본회의 출석', suffix: '%',    pro: false },
  { key: 'committee_attendance_pct', label: '상임위 출석', suffix: '%',    pro: true  },
  { key: 'bills_proposed',           label: '발의',         suffix: '건',   pro: false },
  { key: 'bills_co_proposed',        label: '공동발의',    suffix: '건',   pro: true  },
  { key: 'floor_votes',              label: '본회의 표결', suffix: '회',   pro: false },
  { key: 'party_alignment_pct',      label: '정당 일치',   suffix: '%',    pro: true  },
  { key: 'statements',               label: '발언',         suffix: '회',   pro: true  },
  { key: 'media_mentions_30d',       label: '언론 30일',   suffix: '회',   pro: true  },
];

const PARTY_COLORS: Record<string, string> = {
  '더불어민주당': 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  '국민의힘':     'bg-red-500/20 text-red-300 border-red-500/30',
  '조국혁신당':   'bg-purple-500/20 text-purple-300 border-purple-500/30',
  '진보당':       'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  '정의당':       'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  '개혁신당':     'bg-orange-500/20 text-orange-300 border-orange-500/30',
  '기본소득당':   'bg-pink-500/20 text-pink-300 border-pink-500/30',
  '새로운미래':   'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  '무소속':       'bg-slate-500/20 text-slate-300 border-slate-500/30',
};


export default function MembersPage() {
  const [persona, setPersona] = useState<PersonaId>('editorial');
  const [members, setMembers] = useState<MemberInfo[]>([]);
  const [metricKey, setMetricKey] = useState<keyof MemberAnalytics>('composite_score');
  const [partyFilter, setPartyFilter] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setPersona(readPersonaIdSync() as PersonaId);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const headers: Record<string, string> = { Accept: 'application/json' };
      const personaId = readPersonaIdSync() as PersonaId;
      headers['X-Persona-Id'] = personaId;
      const r = await fetch(`${PUBLIC_BASE}/api/members`, { headers, cache: 'no-store' });
      const d = await r.json();
      setMembers(d.members);
      setPersona(personaId);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // 페르소나 tier
  const isFreeReader = persona === 'general_reader';
  const isPaid = persona === 'paid_subscriber';
  const isB2b = persona === 'b2b';
  const isStaff = ['editorial', 'data_ai', 'ad_sales'].includes(persona);

  // 정렬 + 필터
  const sorted = [...members].sort((a, b) => Number(b.analytics[metricKey]) - Number(a.analytics[metricKey]));
  const filtered = sorted.filter((m) => {
    if (partyFilter && m.party !== partyFilter) return false;
    if (search && !m.name.includes(search) && !m.district.includes(search)) return false;
    return true;
  });

  // 정당 chips
  const parties = Array.from(new Set(members.map((m) => m.party)));

  // 현재 metric 정의
  const metricDef = METRICS.find((m) => m.key === metricKey) ?? METRICS[0];

  return (
    <div>
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-xs font-mono text-slate-500">/members</span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 font-medium">
            22대 국회 · 30 의원 디렉토리
          </span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-1">의원 활동 분석</h1>
        <p className="text-sm text-slate-400">
          본회의·상임위 출석, 발의·표결·발언·언론 노출 통합 지표.
          {isFreeReader && ' (premium 메트릭은 유료 구독자용)'}
          {isPaid && ' · PDF 리포트 + 비교 도구 사용 가능'}
        </p>
      </header>

      {/* Controls */}
      <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="이름·지역구 검색"
          className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-md text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
        />
        <select
          value={partyFilter ?? ''}
          onChange={(e) => setPartyFilter(e.target.value || null)}
          className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-md text-sm text-slate-100 focus:outline-none focus:border-blue-500"
        >
          <option value="">전체 정당</option>
          {parties.map((p) => (<option key={p} value={p}>{p}</option>))}
        </select>
        <div className="flex items-center justify-end text-xs text-slate-500">
          {filtered.length} 명 표시 (총 {members.length}명)
        </div>
      </div>

      {/* Ranking metric tabs */}
      <div className="mb-5">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">정렬·랭킹 기준</div>
        <div className="flex flex-wrap gap-1.5">
          {METRICS.map((m) => {
            const locked = m.pro && isFreeReader;
            return (
              <button
                key={m.key}
                onClick={() => !locked && setMetricKey(m.key)}
                disabled={locked}
                className={
                  'text-xs px-2.5 py-1.5 rounded-md border transition-colors ' +
                  (metricKey === m.key
                    ? 'bg-blue-500/20 border-blue-500/50 text-blue-200 font-medium'
                    : locked
                      ? 'bg-slate-900 border-slate-800 text-slate-600 cursor-not-allowed'
                      : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500')
                }
                title={locked ? 'Premium 지표 (유료 구독자 전용)' : ''}
              >
                {m.label}
                {locked && <span className="ml-1.5 text-[9px] text-slate-500 uppercase tracking-wider">premium</span>}
              </button>
            );
          })}
        </div>
      </div>

      {/* 카드 그리드 */}
      {loading ? (
        <p className="text-slate-400 text-sm">로딩 중…</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((m, i) => (
            <MemberCard
              key={m.assembly_id}
              member={m}
              rank={i + 1}
              metricKey={metricKey}
              metricDef={metricDef}
              isFreeReader={isFreeReader}
              isPaid={isPaid}
              isB2b={isB2b}
              isStaff={isStaff}
            />
          ))}
        </div>
      )}
    </div>
  );
}


function MemberCard({
  member, rank, metricKey, metricDef, isFreeReader, isPaid, isB2b, isStaff,
}: {
  member: MemberInfo;
  rank: number;
  metricKey: keyof MemberAnalytics;
  metricDef: typeof METRICS[number];
  isFreeReader: boolean;
  isPaid: boolean;
  isB2b: boolean;
  isStaff: boolean;
}) {
  const a = member.analytics;
  const partyStyle = PARTY_COLORS[member.party] ?? PARTY_COLORS['무소속'];
  const compositePct = Math.min(100, a.composite_score);

  return (
    <article className="bg-slate-900/70 border border-slate-800 rounded-lg p-4 hover:border-slate-600 transition-colors">
      <div className="flex items-start gap-3 mb-3">
        {/* 사진 */}
        <div className="relative w-16 h-16 shrink-0 rounded-full overflow-hidden bg-slate-800 border border-slate-700">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={member.profile_image_url}
            alt={member.name}
            className="w-16 h-16 object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
              const sibling = (e.target as HTMLImageElement).nextElementSibling as HTMLElement | null;
              if (sibling) sibling.style.display = 'flex';
            }}
          />
          <div
            className="absolute inset-0 hidden items-center justify-center text-2xl font-bold text-slate-400"
            style={{ display: 'none' }}
          >
            {member.name.charAt(0)}
          </div>
          {/* rank 배지는 list 순서로 명확하므로 제거 (사용자 신고: 의원 사진 우측 상단 노란 원이 혼란) */}
        </div>

        {/* 이름·정당·지역구 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-base font-bold text-white truncate">{member.name}</h2>
            <span className="text-[10px] text-slate-500">{member.reelection}</span>
          </div>
          <div className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${partyStyle} mb-1`}>
            {member.party}
          </div>
          <div className="text-[11px] text-slate-400 truncate" title={member.district}>
            {member.district}
          </div>
          {member.committee && (
            <div className="text-[10px] text-slate-500 truncate mt-0.5" title={member.committee}>
              {member.committee}
            </div>
          )}
        </div>

        {/* 선택된 metric 큰 표시 */}
        <div className="text-right">
          <div className="text-[10px] text-slate-500">{metricDef.label}</div>
          <div className="text-2xl font-bold text-amber-400">
            {Number(a[metricKey]).toFixed(metricDef.suffix === '%' ? 1 : 0)}
            <span className="text-[11px] text-slate-500 ml-0.5">{metricDef.suffix}</span>
          </div>
        </div>
      </div>

      {/* 종합 점수 progress bar */}
      <div className="mb-3">
        <div className="flex justify-between text-[10px] text-slate-500 mb-1">
          <span>종합 활동 점수</span>
          <span className="font-mono">{a.composite_score.toFixed(1)} / 100</span>
        </div>
        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-1.5 bg-gradient-to-r from-blue-500 to-amber-400 rounded-full"
            style={{ width: `${compositePct}%` }}
          />
        </div>
      </div>

      {/* metric grid */}
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <Stat label="본회의" value={`${a.plenary_attendance_pct.toFixed(1)}%`} />
        {isFreeReader ? (
          <Stat label="상임위" value="premium" muted />
        ) : (
          <Stat label="상임위" value={`${a.committee_attendance_pct.toFixed(1)}%`} />
        )}
        <Stat label="발의" value={`${a.bills_proposed}건`} />
        {isFreeReader ? (
          <Stat label="공동발의" value="premium" muted />
        ) : (
          <Stat label="공동발의" value={`${a.bills_co_proposed}건`} />
        )}
        {isFreeReader ? (
          <Stat label="발언" value="premium" muted />
        ) : (
          <Stat label="발언" value={`${a.statements}회`} />
        )}
        <Stat label="언론" value={`${a.media_mentions_30d}회`} />
      </div>

      {/* 공통: 온톨로지 관계 그래프 진입 (모든 페르소나) */}
      <div className="mt-3 pt-3 border-t border-slate-800">
        <Link
          href={`/objects/Person/${encodeURIComponent(member.assembly_id)}`}
          className="block w-full text-center text-[11px] tracking-wide px-2 py-2 rounded bg-slate-800/60 border border-slate-700 text-slate-200 hover:border-amber-500/60 hover:text-amber-200 transition-colors"
          title="이 의원을 중심으로 의안·표결·위원회 온톨로지 관계 그래프 펼치기"
        >
          {member.name} 온톨로지 관계 그래프
        </Link>
      </div>

      {/* 페르소나 tier별 CTA */}
      {isPaid && (
        <div className="mt-2 flex gap-2">
          <button className="flex-1 text-[10px] tracking-wide px-2 py-1.5 rounded bg-slate-800/40 border border-amber-500/30 text-amber-200 hover:bg-amber-500/10">
            PDF 리포트
          </button>
          <button className="flex-1 text-[10px] tracking-wide px-2 py-1.5 rounded bg-slate-800/40 border border-amber-500/30 text-amber-200 hover:bg-amber-500/10">
            비교 도구
          </button>
        </div>
      )}
      {isStaff && (
        <div className="mt-2 text-[10px] text-slate-400 leading-relaxed">
          <span className="text-amber-400/90 uppercase tracking-wider mr-1.5">후속 취재</span>
          발의 {a.bills_proposed} · 발언 {a.statements} · 언론 {a.media_mentions_30d}
        </div>
      )}
      {isB2b && (
        <div className="mt-2 text-[10px] font-mono text-slate-500">
          {`GET /api/members/${member.assembly_id}`}
        </div>
      )}
    </article>
  );
}


function Stat({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className={`bg-slate-800/50 rounded p-1.5 ${muted ? 'opacity-50' : ''}`}>
      <div className="text-[9px] text-slate-500">{label}</div>
      <div className="font-mono font-semibold text-slate-200">{value}</div>
    </div>
  );
}
