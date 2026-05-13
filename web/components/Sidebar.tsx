'use client';

/**
 * Sidebar - 좌측 네비게이션.
 *
 * 페르소나 스위처 + 시나리오 링크 + 데이터 출처 범례.
 * 시나리오 우선순위는 페르소나 정렬을 따르지만 PoC는 고정 순서 (라우터가 구현된 것만).
 */
import React from 'react';
import Link from 'next/link';
import { PersonaSwitch } from './PersonaSwitch';
import { DataSourceBadge } from './DataSourceBadge';

const SCENARIOS = [
  { code: 'A', name: '의미 검색', href: '/search', implemented: true },
  { code: 'B', name: '3-stage 챗봇', href: '/chat', implemented: true },
  { code: 'L', name: '광고 매칭 매트릭스', href: '/ad-match', implemented: true,
    badge: 'AI 거버넌스' },
  { code: 'C', name: '기사 인사이트', href: '/insights', implemented: false },
  { code: 'D', name: '페르소나 매칭', href: '/persona-match', implemented: false },
  { code: 'E', name: '의원 클러스터링', href: '/cluster', implemented: false },
  { code: 'F', name: '룩어라이크', href: '/lookalike', implemented: false },
  { code: 'G', name: '기사 ROI', href: '/article-roi', implemented: false },
  { code: 'H', name: '지역구 지도', href: '/district-map', implemented: false },
  { code: 'I', name: '편향·중립성', href: '/neutrality', implemented: false },
  { code: 'J', name: '외부 신호 융합', href: '/external-signal', implemented: false },
  { code: 'K', name: '표결 이상치', href: '/outlier', implemented: false },
  { code: 'M', name: '의원 정치 여정', href: '/journey', implemented: false },
  { code: 'N', name: '이슈 × 입법', href: '/issue-legislation', implemented: false },
];

const OPS_LINKS = [
  { name: '운영 콘솔', href: '/ops', implemented: true, badge: '5 패널' },
  { name: 'Object Explorer', href: '/objects', implemented: true, badge: '31 클래스' },
];

export function Sidebar() {
  return (
    <aside className="w-64 shrink-0 bg-gray-50 border-r border-gray-200 px-4 py-4 overflow-y-auto">
      <div className="mb-4">
        <Link href="/" className="block">
          <div className="text-lg font-bold text-gray-900">
            ontology<span className="text-blue-700">-for-assembly</span>
          </div>
          <div className="text-xs text-gray-500 mt-0.5">한국 언론사 Agentic 온톨로지 PoC</div>
        </Link>
      </div>

      <PersonaSwitch />

      <nav>
        <div className="text-xs uppercase text-gray-500 mb-2">시나리오 (14)</div>
        <ul className="space-y-1">
          {SCENARIOS.map((s) => {
            const disabled = !s.implemented;
            return (
              <li key={s.code}>
                {disabled ? (
                  <span className="block px-2 py-1.5 text-sm text-gray-400 cursor-not-allowed">
                    <span className="font-mono text-xs mr-2">{s.code}</span>
                    {s.name}
                  </span>
                ) : (
                  <Link
                    href={s.href}
                    className="block px-2 py-1.5 rounded-md text-sm hover:bg-gray-100 text-gray-700"
                  >
                    <span className="font-mono text-xs mr-2">{s.code}</span>
                    {s.name}
                    {s.badge && (
                      <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                        {s.badge}
                      </span>
                    )}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="mt-4 pt-4 border-t border-gray-200">
        <div className="text-xs uppercase text-gray-500 mb-2">운영</div>
        <ul className="space-y-1">
          {OPS_LINKS.map((o) => (
            <li key={o.href}>
              <Link
                href={o.href}
                className="block px-2 py-1.5 rounded-md text-sm hover:bg-gray-100 text-gray-700"
              >
                {o.name}
                {o.badge && (
                  <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-700">
                    {o.badge}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4 pt-4 border-t border-gray-200">
        <div className="text-xs uppercase text-gray-500 mb-2">데이터 출처</div>
        <div className="flex flex-wrap gap-1.5">
          <DataSourceBadge source="real" size="xs" />
          <DataSourceBadge source="synthetic" size="xs" />
          <DataSourceBadge source="external" size="xs" />
        </div>
      </div>
    </aside>
  );
}
