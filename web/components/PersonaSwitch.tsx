'use client';

/**
 * PersonaSwitch - 6 페르소나 토글 (sidebar 상단).
 *
 * localStorage 'persona_id'에 저장 + URL hash로 deep-link. 변경 시 페이지 reload
 * (Server Component가 페르소나를 fetch하므로 hard refresh가 가장 단순).
 *
 * ADR-0002 / 0003: 6 페르소나 SSOT는 lib/personas.ts.
 */
import React, { useEffect, useState } from 'react';
import { PenTool, LineChart, Megaphone, User, Crown, Building2, type LucideIcon } from 'lucide-react';
import {
  PERSONAS, DEFAULT_PERSONA, TIER_GROUP_KR, TIER_GROUP_ORDER,
  type PersonaId, type Tier,
} from '../lib/personas';

// 페르소나 lucide icon 매핑 (투명 fill + currentColor stroke 일관)
const PERSONA_ICONS: Record<PersonaId, LucideIcon> = {
  editorial:       PenTool,
  data_ai:         LineChart,
  ad_sales:        Megaphone,
  general_reader:  User,
  paid_subscriber: Crown,
  b2b:             Building2,
};

const STORAGE_KEY = 'persona_id';

// tier 별 아이콘·색 (UI 식별)
const TIER_BADGE: Record<Tier, { dot: string; label: string }> = {
  staff:    { dot: 'bg-slate-400',  label: '내부' },
  b2c_free: { dot: 'bg-blue-400',   label: '무료' },
  b2c_paid: { dot: 'bg-amber-400',  label: '유료' },
  b2b:      { dot: 'bg-emerald-400', label: 'API' },
};


export function PersonaSwitch() {
  const [current, setCurrent] = useState<PersonaId>(DEFAULT_PERSONA);

  useEffect(() => {
    const stored = (typeof window !== 'undefined'
      ? window.localStorage.getItem(STORAGE_KEY)
      : null) as PersonaId | null;
    if (stored && PERSONAS.some((p) => p.id === stored)) {
      setCurrent(stored);
    }
  }, []);

  function onChange(id: PersonaId) {
    setCurrent(id);
    window.localStorage.setItem(STORAGE_KEY, id);
    // 페르소나 변경 시 *홈으로 navigation* (각 페르소나 fresh entry point).
    // 사용자 신고: 페르소나 메뉴 선택해도 머무는 페이지가 그대로. → 홈으로 redirect로
    // 페르소나별 추천 시나리오·KPI hero를 다시 보여줘 의미 있는 페르소나 차이 시연.
    window.location.replace(`/?p=${encodeURIComponent(id)}`);
  }

  return (
    <div className="border-b border-slate-800 pb-3 mb-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 px-1">
        페르소나 (사용자 유형)
      </div>

      {TIER_GROUP_ORDER.map((tier) => {
        const groupPersonas = PERSONAS.filter((p) => p.tier === tier);
        if (groupPersonas.length === 0) return null;
        return (
          <div key={tier} className="mb-2">
            <div className="text-[10px] font-semibold text-slate-400 px-1 mb-1 flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${TIER_BADGE[tier].dot}`}></span>
              {TIER_GROUP_KR[tier]}
            </div>
            <ul className="space-y-0.5">
              {groupPersonas.map((p) => {
                const isActive = p.id === current;
                const Icon = PERSONA_ICONS[p.id];
                return (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => onChange(p.id)}
                      className={
                        'w-full text-left px-2 py-1.5 rounded-md text-xs flex items-center gap-2 transition-colors ' +
                        (isActive
                          ? 'bg-blue-500/15 border border-blue-500/40 text-blue-200 font-semibold'
                          : 'border border-transparent hover:bg-slate-800 text-slate-300')
                      }
                      aria-current={isActive ? 'true' : 'false'}
                      title={p.description}
                    >
                      <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-blue-300' : 'text-slate-400'}`} />
                      <span className="flex-1 truncate">{p.nameKr}</span>
                      <span className="text-[9px] text-slate-500">{TIER_BADGE[tier].label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}


// Server Component에서 현재 페르소나 ID 추론 - localStorage 접근 불가하므로
// 클라이언트에서 header 첨부 또는 cookie 필요. PoC는 client component만 페르소나
// 인식. SSR 페르소나는 후속 phase에서 cookie 도입.
export function readPersonaIdSync(): PersonaId {
  if (typeof window === 'undefined') return DEFAULT_PERSONA;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored && PERSONAS.some((p) => p.id === stored)) {
    return stored as PersonaId;
  }
  return DEFAULT_PERSONA;
}
