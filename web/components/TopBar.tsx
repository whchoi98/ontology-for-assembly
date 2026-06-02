'use client';

/**
 * TopBar — 글로벌 상단 헤더 (gcc 패턴 차용 + assembly 톤).
 *
 * 좌: 페이지 path indicator (breadcrumb-light)
 * 우: 현재 페르소나 chip · GuidedTour · 도움말 link
 *
 * mount는 항상 유지 (Sidebar와 같이 LayoutShell shell 부분).
 */
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { readPersonaIdSync } from './PersonaSwitch';
import { PERSONAS, TIER_GROUP_KR, type PersonaId } from '../lib/personas';


const PATH_LABELS: Record<string, string> = {
  '/':                  'Assembly Insight Hub · 대시보드',
  '/chat':              '데스크 챗봇',
  '/chat/compare':      '3-stage 진화 비교',
  '/chat/popup':        '데스크 챗봇 (popup)',
  '/mindmap':           '온톨로지 관계 그래프 탐색',
  '/members':           '의원 디렉토리',
  '/search':            '의미 검색',
  '/district-map':      '지역구 지도',
  '/insights':          '기사 인사이트',
  '/persona-match':     '페르소나 매칭',
  '/cluster':           '의원 클러스터링',
  '/lookalike':         '룩어라이크',
  '/article-roi':       '기사 ROI',
  '/neutrality':        '편향·중립성',
  '/external-signal':   '외부 신호 융합',
  '/outlier':           '표결 이상치',
  '/ad-match':          '광고 매칭',
  '/journey':           '의원 정치 여정',
  '/issue-legislation': '이슈 × 입법',
  '/objects':           'Object Explorer',
  '/ops':               '운영 콘솔',
};


export function TopBar() {
  const pathname = usePathname() ?? '/';
  const [persona, setPersona] = useState<PersonaId>('editorial');

  useEffect(() => { setPersona(readPersonaIdSync()); }, [pathname]);

  // path label (most specific first)
  let label = PATH_LABELS[pathname];
  if (!label) {
    if (pathname.startsWith('/objects/')) label = 'Object Explorer';
    else label = pathname;
  }

  const personaDef = PERSONAS.find((p) => p.id === persona);
  const tierLabel = personaDef ? TIER_GROUP_KR[personaDef.tier] : '';

  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 px-5 h-12 bg-slate-950/95 backdrop-blur border-b border-slate-800 shrink-0">
      {/* 좌: 페이지 path */}
      <div className="flex items-center gap-2 min-w-0">
        <Link href="/" className="text-[12px] font-semibold text-amber-200 tracking-tight whitespace-nowrap hover:text-amber-100">
          ASSEMBLY
        </Link>
        <span className="text-slate-700">›</span>
        <span className="text-[12px] text-slate-300 truncate">{label}</span>
      </div>

      {/* 우: 빠른 진입 메뉴 + 페르소나 chip */}
      <nav className="ml-auto flex items-center gap-1">
        <TopLink href="/chat" current={pathname}>챗봇</TopLink>
        <TopLink href="/mindmap" current={pathname}>온톨로지 관계 그래프</TopLink>
        <TopLink href="/members" current={pathname}>의원</TopLink>
        <TopLink href="/district-map" current={pathname}>지역구</TopLink>
        <span className="mx-1 text-slate-700">|</span>
        {personaDef && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-slate-900 border border-slate-800 text-[10px]">
            <span className="text-slate-500">PERSONA</span>
            <span className="text-amber-200 font-semibold">{personaDef.nameKr}</span>
            <span className="text-slate-500 text-[9px] uppercase tracking-wider">· {tierLabel}</span>
          </div>
        )}
      </nav>
    </header>
  );
}


function TopLink({ href, current, children }: { href: string; current: string; children: React.ReactNode }) {
  const active = current === href || (href !== '/' && current.startsWith(href));
  return (
    <Link
      href={href}
      className={
        'px-2.5 py-1 rounded text-[11px] transition-colors ' +
        (active
          ? 'bg-blue-500/20 border border-blue-500/40 text-blue-200 font-semibold'
          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60')
      }
    >
      {children}
    </Link>
  );
}
