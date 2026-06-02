'use client';

/**
 * Sidebar - 좌측 네비게이션 (다크 패턴, 미디어 사이트 톤).
 *
 * 페르소나 스위처(tier 3그룹 분리) + 시나리오 + 운영 + 의원 디렉토리 + 데이터 출처.
 */
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Search, MessageSquare, BarChart3, Users, Layers, GitMerge, TrendingUp,
  Map, ShieldCheck, Radio, AlertTriangle, Compass, Sparkles, LineChart,
  Network, Activity, Database, Handshake, Mailbox, Building, ClipboardCheck, BarChart,
  Scale, Crown, Target, Shuffle,
  type LucideIcon,
} from 'lucide-react';
import { PersonaSwitch } from './PersonaSwitch';
import { DataSourceBadge } from './DataSourceBadge';
import {
  DEFAULT_PERSONA, PERSONA_PRIMARY_SCENARIOS, PERSONAS,
  type PersonaId,
} from '../lib/personas';

// gcc 패턴: lucide-react SVG 아이콘 (w-4 h-4, text-ink-400 → text-accent-400 활성).
const SCENARIOS: Array<{ code: string; icon: LucideIcon; name: string; href: string; badge?: string }> = [
  { code: 'A', icon: Search,         name: '의미 검색',       href: '/search' },
  { code: 'B', icon: MessageSquare,  name: '데스크 챗봇',     href: '/chat', badge: '데모 ★' },
  { code: 'L', icon: Sparkles,       name: '광고 매칭',       href: '/ad-match', badge: 'AI 거버넌스' },
  { code: 'C', icon: BarChart3,      name: '기사 인사이트',   href: '/insights' },
  { code: 'D', icon: Users,          name: '페르소나 매칭',   href: '/persona-match' },
  { code: 'E', icon: Layers,         name: '의원 클러스터링', href: '/cluster' },
  { code: 'F', icon: GitMerge,       name: '룩어라이크',      href: '/lookalike' },
  { code: 'G', icon: TrendingUp,     name: '기사 ROI',        href: '/article-roi' },
  { code: 'H', icon: Map,            name: '지역구 지도',     href: '/district-map' },
  { code: 'I', icon: ShieldCheck,    name: '편향·중립성',     href: '/neutrality' },
  { code: 'J', icon: Radio,          name: '외부 신호 융합',  href: '/external-signal' },
  { code: 'K', icon: AlertTriangle,  name: '표결 이상치',     href: '/outlier', badge: 'PDF' },
  { code: 'M', icon: Compass,        name: '의원 정치 여정',  href: '/journey', badge: 'PDF' },
  { code: 'N', icon: LineChart,      name: '이슈 × 입법',     href: '/issue-legislation' },
  // ─── 확장 시나리오 (O–S) — 사용자 요청 ─────────────────────────────
  { code: 'O', icon: Handshake,      name: '인물 관계 분석',  href: '/relations', badge: '신규 ★' },
  { code: 'P', icon: Mailbox,        name: '청원 → 입법',     href: '/petition-map', badge: '신규 ★' },
  { code: 'Q', icon: Building,       name: '위원회 영향력',   href: '/committee-heatmap', badge: '신규' },
  { code: 'R', icon: ClipboardCheck, name: '공약 이행 추적',  href: '/promise-tracker', badge: '신규' },
  { code: 'S', icon: BarChart,       name: '토픽 burst',      href: '/topic-burst', badge: '신규' },
  // ─── Phase 4f 고급 인사이트 (T-W) — 74K real edges Cypher 분석 ──────
  { code: 'T', icon: Scale,          name: '정당 응집도',     href: '/party-cohesion', badge: 'REAL' },
  { code: 'U', icon: Crown,          name: '의원 영향력',     href: '/influence-rank', badge: 'REAL' },
  { code: 'V', icon: Target,         name: '표결 cluster',    href: '/voting-cluster', badge: 'REAL' },
  { code: 'W', icon: Shuffle,        name: 'Swing voter',     href: '/swing-voters',   badge: 'REAL' },
];

const MEDIA_LINKS: Array<{ icon: LucideIcon; name: string; href: string; badge?: string }> = [
  { icon: Network, name: '온톨로지 관계 그래프',  href: '/mindmap',  badge: '1–3 hop' },
  { icon: Users,   name: '의원 디렉토리',  href: '/members',  badge: '286명 · 9 지표' },
];

const OPS_LINKS: Array<{ icon: LucideIcon; name: string; href: string; badge?: string }> = [
  { icon: Activity, name: '운영 콘솔',       href: '/ops',     badge: '5 패널' },
  { icon: Database, name: 'Object Explorer', href: '/objects', badge: '31 클래스' },
];


export function Sidebar() {
  const pathname = usePathname();
  // 페르소나 변경 시 사이드바 재구성 — localStorage에서 읽기 + URL query ?p={id}로 reload
  const [persona, setPersona] = useState<PersonaId>(DEFAULT_PERSONA);
  useEffect(() => {
    const stored = typeof window !== 'undefined'
      ? (window.localStorage.getItem('persona_id') as PersonaId | null) : null;
    if (stored && PERSONAS.some((p) => p.id === stored)) setPersona(stored);
  }, []);

  // 페르소나별 *주력 시나리오* + *기타* 분리 (사용자 신고: 사이드바 혼란 → 주력 강조)
  const primaryCodes = PERSONA_PRIMARY_SCENARIOS[persona] ?? [];
  const primaryScenarios = primaryCodes
    .map((c) => SCENARIOS.find((s) => s.code === c))
    .filter((s): s is typeof SCENARIOS[number] => s !== undefined);
  const otherScenarios = SCENARIOS.filter((s) => !primaryCodes.includes(s.code));

  // 페르소나별 *언론·미디어* 메뉴 — staff/B2C는 온톨로지 관계 그래프+디렉토리, B2B는 API 우선
  const mediaForPersona = (() => {
    if (persona === 'b2b') {
      return [
        { icon: Database, name: 'Object Explorer', href: '/objects', badge: 'API' },
        { icon: Users,    name: '의원 디렉토리',    href: '/members',  badge: '286명' },
      ];
    }
    return MEDIA_LINKS;
  })();

  const personaName = PERSONAS.find((p) => p.id === persona)?.nameKr ?? '편집국';

  return (
    <aside className="w-64 shrink-0 bg-slate-900/80 border-r border-slate-800 px-3 py-4 overflow-y-auto">
      {/* Brand */}
      <div className="mb-4 px-1">
        <Link href="/" className="block">
          <div className="text-base font-bold text-white tracking-tight">
            ontology<span className="text-blue-400">·</span>assembly
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            한국 언론사 Agentic 온톨로지
          </div>
        </Link>
      </div>

      <PersonaSwitch />

      {/* 의원·미디어 (페르소나별) */}
      <NavSection title="언론·미디어">
        {mediaForPersona.map((m) => (
          <NavItem key={m.href} href={m.href} active={pathname === m.href}
                   icon={m.icon} label={m.name} badge={m.badge} accent="amber" />
        ))}
      </NavSection>

      {/* 주력 시나리오 (페르소나별 top 4-5) */}
      <NavSection title={`${personaName} 주력 시나리오`}>
        {primaryScenarios.map((s) => (
          <NavItem
            key={s.code} href={s.href} active={pathname === s.href}
            icon={s.icon} code={s.code} label={s.name} badge={s.badge}
          />
        ))}
      </NavSection>

      {/* 전체 시나리오 (기타 — 흐릿) */}
      <NavSection title="전체 시나리오">
        {otherScenarios.map((s) => (
          <NavItem
            key={s.code} href={s.href} active={pathname === s.href}
            icon={s.icon} code={s.code} label={s.name} badge={s.badge}
            dimmed
          />
        ))}
      </NavSection>

      {/* 운영 (staff만 표시) */}
      {(persona === 'editorial' || persona === 'data_ai' || persona === 'ad_sales') && (
        <NavSection title="운영">
          {OPS_LINKS.map((o) => (
            <NavItem key={o.href} href={o.href} active={pathname?.startsWith(o.href)}
                     icon={o.icon} label={o.name} badge={o.badge} accent="slate" />
          ))}
        </NavSection>
      )}

      {/* 데이터 출처 범례 */}
      <div className="mt-4 pt-3 border-t border-slate-800">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 px-1">
          데이터 출처
        </div>
        <div className="flex flex-wrap gap-1 px-1">
          <DataSourceBadge source="real" size="xs" />
          <DataSourceBadge source="synthetic" size="xs" />
          <DataSourceBadge source="external" size="xs" />
        </div>
      </div>
    </aside>
  );
}


function NavSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <nav className="mb-4">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 px-1">
        {title}
      </div>
      <ul className="space-y-0.5">{children}</ul>
    </nav>
  );
}


function NavItem({
  href, label, code, badge, active, accent = 'blue', icon: Icon, dimmed = false,
}: {
  href: string;
  label: string;
  code?: string;
  badge?: string;
  active?: boolean;
  accent?: 'blue' | 'amber' | 'slate';
  icon?: LucideIcon;
  dimmed?: boolean;
}) {
  const accentBg = accent === 'amber' ? 'bg-amber-500/15 border-amber-500/40 text-amber-200'
                 : accent === 'slate' ? 'bg-slate-700/40 border-slate-600 text-slate-100'
                 : 'bg-blue-500/15 border-blue-500/40 text-blue-200';
  const badgeColor = accent === 'amber' ? 'bg-amber-500/20 text-amber-300'
                   : accent === 'slate' ? 'bg-slate-700 text-slate-300'
                   : 'bg-blue-500/20 text-blue-300';

  return (
    <li>
      <Link
        href={href}
        className={
          'flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs transition-colors border ' +
          (active
            ? accentBg + ' font-semibold'
            : dimmed
              ? 'border-transparent hover:bg-slate-800 text-slate-500'
              : 'border-transparent hover:bg-slate-800 text-slate-300')
        }
      >
        {Icon && <Icon className={`w-4 h-4 flex-shrink-0 ${active ? 'text-blue-300' : 'text-slate-400'}`} />}
        {code && <span className="font-mono text-[10px] text-slate-500 w-3">{code}</span>}
        <span className="flex-1 truncate">{label}</span>
        {badge && (
          <span className={`text-[9px] px-1 py-0.5 rounded ${badgeColor} whitespace-nowrap`}>
            {badge}
          </span>
        )}
      </Link>
    </li>
  );
}
