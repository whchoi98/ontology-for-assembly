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
import { PERSONAS, DEFAULT_PERSONA, type PersonaId } from '../lib/personas';

const STORAGE_KEY = 'persona_id';

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
    // 페르소나가 모든 API 응답에 영향 → 페이지 새로고침으로 일관성 보장.
    window.location.reload();
  }

  return (
    <div className="border-b border-gray-200 pb-3 mb-3">
      <div className="text-xs uppercase text-gray-500 mb-2">페르소나</div>
      <ul className="space-y-1">
        {PERSONAS.map((p) => {
          const isActive = p.id === current;
          return (
            <li key={p.id}>
              <button
                onClick={() => onChange(p.id)}
                className={
                  'w-full text-left px-2 py-1.5 rounded-md text-sm flex items-center gap-2 ' +
                  (isActive
                    ? 'bg-blue-50 text-blue-800 font-semibold'
                    : 'hover:bg-gray-100 text-gray-700')
                }
                aria-current={isActive ? 'true' : 'false'}
              >
                <span>{p.emoji}</span>
                <span className="flex-1">{p.nameKr}</span>
                <span className="text-xs text-gray-400">{p.tier}</span>
              </button>
            </li>
          );
        })}
      </ul>
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
