'use client';

/**
 * 시나리오 Q — 위원회 영향력 heatmap.
 *
 * 17 상임위 × 5 메트릭 heatmap (발의·심사·통과·발언·출석).
 * 위원회 row 클릭 → 온톨로지 관계 그래프 (위원회 → 위원장·간사·소관 의안) + AI 인사이트 specific.
 */
import React, { useEffect, useMemo, useState } from 'react';
import ScenarioHero from '../../components/ScenarioHero';
import { AIInsightPanel } from '../../components/AIInsightPanel';
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

interface Committee {
  committee_id: string;
  name: string;
  short: string;
  metrics: { proposed: number; reviewed: number; passed: number; statements: number; attendance_pct: number };
}

const COMMITTEES: Committee[] = [
  { committee_id: 'C-FIN', name: '기획재정위원회',     short: '기재',  metrics: { proposed: 14, reviewed: 9,  passed: 3, statements: 28, attendance_pct: 91 } },
  { committee_id: 'C-POL', name: '정무위원회',         short: '정무',  metrics: { proposed: 12, reviewed: 8,  passed: 3, statements: 25, attendance_pct: 88 } },
  { committee_id: 'C-SCI', name: '과학기술정보방송통신', short: '과방',  metrics: { proposed: 11, reviewed: 7,  passed: 2, statements: 22, attendance_pct: 87 } },
  { committee_id: 'C-EDU', name: '교육위원회',         short: '교육',  metrics: { proposed: 8,  reviewed: 6,  passed: 5, statements: 19, attendance_pct: 92 } },
  { committee_id: 'C-FOR', name: '외교통일위원회',     short: '외통',  metrics: { proposed: 7,  reviewed: 11, passed: 1, statements: 18, attendance_pct: 84 } },
  { committee_id: 'C-DEF', name: '국방위원회',         short: '국방',  metrics: { proposed: 5,  reviewed: 8,  passed: 1, statements: 14, attendance_pct: 86 } },
  { committee_id: 'C-ADM', name: '행정안전위원회',     short: '행안',  metrics: { proposed: 9,  reviewed: 7,  passed: 2, statements: 17, attendance_pct: 89 } },
  { committee_id: 'C-CUL', name: '문화체육관광위원회', short: '문체',  metrics: { proposed: 8,  reviewed: 5,  passed: 2, statements: 16, attendance_pct: 85 } },
  { committee_id: 'C-AGR', name: '농림축산식품해양수산', short: '농해', metrics: { proposed: 7,  reviewed: 6,  passed: 2, statements: 15, attendance_pct: 87 } },
  { committee_id: 'C-IND', name: '산업통상자원중소벤처',  short: '산자', metrics: { proposed: 13, reviewed: 10, passed: 4, statements: 26, attendance_pct: 90 } },
  { committee_id: 'C-HEA', name: '보건복지위원회',     short: '복지',  metrics: { proposed: 15, reviewed: 11, passed: 5, statements: 30, attendance_pct: 93 } },
  { committee_id: 'C-ENV', name: '환경노동위원회',     short: '환노',  metrics: { proposed: 10, reviewed: 9,  passed: 3, statements: 21, attendance_pct: 88 } },
  { committee_id: 'C-LND', name: '국토교통위원회',     short: '국토',  metrics: { proposed: 12, reviewed: 9,  passed: 4, statements: 24, attendance_pct: 89 } },
  { committee_id: 'C-WMN', name: '여성가족위원회',     short: '여가',  metrics: { proposed: 6,  reviewed: 4,  passed: 2, statements: 12, attendance_pct: 86 } },
  { committee_id: 'C-LAW', name: '법제사법위원회',     short: '법사',  metrics: { proposed: 9,  reviewed: 14, passed: 2, statements: 23, attendance_pct: 90 } },
  { committee_id: 'C-INT', name: '정보위원회',         short: '정보',  metrics: { proposed: 4,  reviewed: 5,  passed: 1, statements: 10, attendance_pct: 82 } },
  { committee_id: 'C-OPR', name: '운영위원회',         short: '운영',  metrics: { proposed: 5,  reviewed: 6,  passed: 2, statements: 13, attendance_pct: 85 } },
];

const METRICS = [
  { key: 'proposed' as const,       label: '발의',   max: 15 },
  { key: 'reviewed' as const,       label: '심사',   max: 14 },
  { key: 'passed' as const,         label: '통과',   max: 5 },
  { key: 'statements' as const,     label: '발언',   max: 30 },
  { key: 'attendance_pct' as const, label: '출석률', max: 100 },
];

// 위원회별 소관 합성 의안 (3건)
const COMMITTEE_BILLS: Record<string, string[]> = {
  'C-FIN': ['세법 개정안',           '예산결산 특별법',     '국가재정법 일부개정안'],
  'C-POL': ['공정거래법 개정안',     '금융소비자보호법',     '은행법 일부개정안'],
  'C-SCI': ['AI 기본법',             '디지털플랫폼법',       '방송법 일부개정안'],
  'C-EDU': ['사교육비 경감법',       '초중등교육법 개정',    '대학 등록금 안정법'],
  'C-FOR': ['해외동포 지원법',       '외교통상 기본법',      '남북교류협력법'],
  'C-DEF': ['병역법 일부개정안',     '방위사업법 개정안',    '예비군법 개정'],
  'C-ADM': ['지방자치법 개정안',     '재난안전관리 기본법',  '주민투표법 개정'],
  'C-CUL': ['관광진흥법 개정안',     '체육진흥법 개정안',    '문화예술인 지원법'],
  'C-AGR': ['농업·농촌 기본법',      '해양수산 발전법',      '식품안전 강화법'],
  'C-IND': ['산업진흥 특별법',       '중소벤처기업 지원법',  '소상공인 보호법'],
  'C-HEA': ['노인 의료 보장법',      '치매 국가책임법',      '국민건강보험법 개정'],
  'C-ENV': ['환경 기본법 개정안',    '근로기준법 개정안',    '대기환경보전법'],
  'C-LND': ['주거 안정 특별법',      '도로교통법 개정안',    '도시정비 촉진법'],
  'C-WMN': ['성평등 기본법',         '다문화가족지원법',      '아동학대처벌법'],
  'C-LAW': ['형사소송법 개정안',     '법원조직법 일부개정',  '검찰청법 개정안'],
  'C-INT': ['국가정보원법 개정안',   '국가보안법 일부개정',  '사이버안보법'],
  'C-OPR': ['국회법 개정안',         '국회운영 규칙 개정',   '국회사무처법'],
};

function colorFor(value: number, max: number): string {
  const ratio = Math.min(1, value / max);
  if (ratio < 0.25) return 'bg-slate-700 text-slate-300';
  if (ratio < 0.5)  return 'bg-blue-500/40 text-blue-100';
  if (ratio < 0.75) return 'bg-amber-500/60 text-white';
  return 'bg-red-500/70 text-white font-bold';
}

// committee_id로 deterministic 의원 3명 선택 (위원장 + 양당 간사 우선)
function pickCommitteeMembers(c: Committee, members: MemberLite[]): { chair?: MemberLite; whipA?: MemberLite; whipB?: MemberLite } {
  if (members.length < 3) return {};
  const seed = c.committee_id.split('').reduce((s, ch) => (s + ch.charCodeAt(0)) % 1000, 0);
  const chair = members[seed % members.length];
  // 다른 정당의 첫 의원 (cross-party whip 우선)
  const whipA = members.find((m, i) => i !== members.indexOf(chair) && m.party !== chair.party)
              ?? members[(seed + 1) % members.length];
  const whipB = members.find((m, i) =>
    i !== members.indexOf(chair) && i !== members.indexOf(whipA) && m.party !== chair.party,
  ) ?? members[(seed + 2) % members.length];
  return { chair, whipA, whipB };
}

function buildCommitteeSubgraph(c: Committee, members: MemberLite[]): Subgraph {
  const cmtId = `Committee:${c.committee_id}`;
  const { chair, whipA, whipB } = pickCommitteeMembers(c, members);
  const billTitles = COMMITTEE_BILLS[c.committee_id] ?? [];
  const billIds = billTitles.map((_, i) => `Bill:${c.committee_id}-B${i + 1}`);

  const personNodes = [chair, whipA, whipB].filter((m): m is MemberLite => !!m).map((m) => ({
    id: `Person:${m.assembly_id}`,
    label: 'Person' as const,
    data: { name: m.name, party: m.party, district: m.district, profile_image_url: m.profile_image_url },
  }));

  const nodes = [
    { id: cmtId, label: 'Committee', data: { name: c.name, ...c.metrics } },
    ...personNodes,
    ...billIds.map((id, i) => ({ id, label: 'Bill', data: { name: billTitles[i] } })),
  ];

  const edges = [
    // 위원장 + 간사 → Committee MEMBER_OF
    ...personNodes.map((pn) => ({ source: pn.id, target: cmtId, type: 'MEMBER_OF' })),
    // 소관 의안 → Committee ASSIGNED_TO
    ...billIds.map((bid) => ({ source: bid, target: cmtId, type: 'ASSIGNED_TO' })),
  ];

  return { root_id: cmtId, nodes, edges };
}

export default function CommitteeHeatmapPage() {
  const [selected, setSelected] = useState<Committee | null>(null);
  const [members, setMembers] = useState<MemberLite[]>([]);

  useEffect(() => {
    fetch(`${BASE}/api/members`)
      .then((r) => r.json())
      .then((d) => setMembers(d.members ?? []))
      .catch(() => setMembers([]));
  }, []);

  const topPassed = useMemo(() =>
    [...COMMITTEES].sort((a, b) => b.metrics.passed - a.metrics.passed).slice(0, 3), []);

  const subgraph = useMemo(
    () => (selected && members.length ? buildCommitteeSubgraph(selected, members) : null),
    [selected, members],
  );

  const insightContext = useMemo(() => {
    if (!selected) return null;
    const { chair, whipA, whipB } = pickCommitteeMembers(selected, members);
    return {
      committee_id: selected.committee_id,
      committee_name: selected.name,
      committee_short: selected.short,
      proposed: selected.metrics.proposed,
      reviewed: selected.metrics.reviewed,
      passed: selected.metrics.passed,
      statements: selected.metrics.statements,
      attendance_pct: selected.metrics.attendance_pct,
      pass_rate: ((selected.metrics.passed / selected.metrics.proposed) * 100).toFixed(0),
      assigned_bills: COMMITTEE_BILLS[selected.committee_id] ?? [],
      chair_name: chair?.name ?? '',
      whip_a_name: whipA?.name ?? '',
      whip_b_name: whipB?.name ?? '',
    };
  }, [selected, members]);

  return (
    <div>
      <ScenarioHero code="Q" subtitle="신규 ★" />

      {/* Top 3 통과 위원회 */}
      <section className="mb-6 grid grid-cols-3 gap-3">
        {topPassed.map((c, i) => (
          <button key={c.name} type="button" onClick={() => setSelected(c)}
            className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-left hover:border-amber-400 transition-colors">
            <div className="text-[10px] uppercase tracking-wider text-amber-300 mb-1">#{i + 1} 통과 top</div>
            <div className="text-sm font-bold text-white">{c.name}</div>
            <div className="text-xl font-mono font-bold text-amber-300 mt-1">{c.metrics.passed}건</div>
          </button>
        ))}
      </section>

      {/* heatmap — row 클릭으로 select */}
      <section className="mb-6 overflow-x-auto">
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">17 위원회 × 5 메트릭 heatmap <span className="text-slate-500 normal-case">— 위원회 클릭으로 온톨로지 관계 그래프/AI 인사이트 표시</span></div>
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left py-2 pr-3 text-slate-500 font-normal">위원회</th>
              {METRICS.map((m) => (
                <th key={m.key} className="text-center py-2 px-2 text-slate-400 font-semibold">{m.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {COMMITTEES.map((c) => {
              const isSelected = selected?.committee_id === c.committee_id;
              return (
                <tr key={c.name}
                    onClick={() => setSelected(c)}
                    className={
                      'border-t border-slate-800 cursor-pointer transition-colors ' +
                      (isSelected ? 'bg-blue-500/15' : 'hover:bg-slate-800/50')
                    }>
                  <td className={'py-2 pr-3 font-medium ' + (isSelected ? 'text-blue-200' : 'text-slate-200')}>
                    {c.name}
                  </td>
                  {METRICS.map((m) => {
                    const val = c.metrics[m.key];
                    return (
                      <td key={m.key} className="py-2 px-1 text-center">
                        <div className={`inline-block w-14 py-1 rounded font-mono text-[11px] ${colorFor(val, m.max)}`}>
                          {val}{m.key === 'attendance_pct' ? '%' : ''}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* 온톨로지 관계 그래프 — selected committee */}
      {selected && subgraph && (
        <section className="mb-6">
          <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
            🕸️ 위원회 온톨로지 관계 그래프 — <span className="text-white">{selected.name}</span>
            <span className="ml-2 text-[10px] text-slate-500">
              위원장 · 양당 간사 · 소관 의안 {COMMITTEE_BILLS[selected.committee_id]?.length ?? 0}건
            </span>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40">
            <CytoscapeView subgraph={subgraph} height={440} expandable={false} />
          </div>
        </section>
      )}

      {insightContext ? (
        <AIInsightPanel scenarioCode="Q" context={insightContext} autoGenerate />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          위원회를 클릭하면 온톨로지 관계 그래프 + AI 인사이트가 표시됩니다.
        </div>
      )}
    </div>
  );
}
