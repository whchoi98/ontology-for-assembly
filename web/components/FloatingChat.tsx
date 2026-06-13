'use client';

/**
 * 우측 하단 floating chat 트리거.
 *
 * 브라우저별 분기 (검증 결과):
 *   - Firefox: window.open(url, name, "popup,...") → features 만으로 popup 보장
 *   - Chrome: Site Engagement Score 가 낮으면 popup → tab 으로 demote
 *     → window.open 결과가 null 이거나 closed 즉시 감지 → iframe modal fallback
 *   - 기타(Safari/Edge): Chrome 과 동일 분기 (engagement score 의존)
 *
 * 채팅 popup 자체는 /chat/popup 페이지 (Sidebar 없는 standalone UI).
 */
import React, { useEffect, useRef, useState } from 'react';
import { MessageCircle } from 'lucide-react';
import { readPersonaIdSync } from './PersonaSwitch';


type LaunchMode = 'popup' | 'iframe';


function detectBrowser(): 'firefox' | 'chrome' | 'safari' | 'edge' | 'other' {
  if (typeof navigator === 'undefined') return 'other';
  const ua = navigator.userAgent;
  if (ua.includes('Firefox/')) return 'firefox';
  if (ua.includes('Edg/')) return 'edge';
  if (ua.includes('Chrome/')) return 'chrome';
  if (ua.includes('Safari/')) return 'safari';
  return 'other';
}


/** Firefox 외 브라우저는 engagement score 의존 → iframe 우선 안전. */
function preferredMode(): LaunchMode {
  return detectBrowser() === 'firefox' ? 'popup' : 'iframe';
}


export function FloatingChat() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<LaunchMode>('iframe');
  const popupRef = useRef<Window | null>(null);

  useEffect(() => {
    setMode(preferredMode());
  }, []);

  function launch() {
    const personaId = readPersonaIdSync();
    const url = `/chat/popup?persona=${encodeURIComponent(personaId)}`;

    if (mode === 'popup') {
      // Firefox: features 만으로 popup 보장
      const w = window.open(
        url, 'assembly-chat',
        'popup=yes,width=520,height=720,resizable=yes,scrollbars=yes,toolbar=no,location=no',
      );
      // popup blocked or demoted to tab → iframe fallback
      if (!w || w.closed || typeof w.closed === 'undefined') {
        setMode('iframe');
        setOpen(true);
        return;
      }
      popupRef.current = w;
      w.focus();
      return;
    }

    // Chrome/Safari/Edge: iframe modal 직접 (engagement score 의존 회피)
    setOpen(true);
  }

  function close() {
    setOpen(false);
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.close();
    }
  }

  return (
    <>
      <button
        onClick={launch}
        title="챗봇 (시나리오 B)"
        aria-label="챗봇 열기"
        className="
          fixed bottom-20 right-6 z-40
          bg-gradient-to-br from-blue-500 to-blue-700
          hover:from-blue-400 hover:to-blue-600
          text-white rounded-full
          w-14 h-14 shadow-xl shadow-blue-900/50
          flex items-center justify-center
          transition-transform hover:scale-105
        "
      >
        <MessageCircle className="w-7 h-7" strokeWidth={2.25} />
      </button>

      {open && mode === 'iframe' && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) close(); }}
        >
          <div className="relative w-full max-w-2xl h-[80vh] bg-slate-950 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
            <header className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="text-base">💬</span>
                <span className="text-sm font-semibold text-slate-100">기자/독자 챗봇</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  시나리오 B · SSE
                </span>
              </div>
              <button
                onClick={close}
                className="text-slate-400 hover:text-white text-xl leading-none w-6 h-6 flex items-center justify-center"
                aria-label="닫기"
              >×</button>
            </header>
            <iframe
              src={`/chat/popup?persona=${encodeURIComponent(readPersonaIdSync())}&embed=1`}
              className="w-full h-[calc(80vh-40px)] border-0 bg-slate-950"
              title="챗봇"
            />
          </div>
        </div>
      )}
    </>
  );
}
