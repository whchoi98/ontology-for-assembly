'use client';

/**
 * 메인 shell — Sidebar + FloatingChat 노출 제어.
 *
 * /chat/popup 라우트는 popup window / iframe modal 내부에 렌더되므로
 * Sidebar·FloatingChat 숨김 (standalone UX).
 */
import React from 'react';
import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';
import { FloatingChat } from './FloatingChat';
import { TopBar } from './TopBar';


export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isStandalone = pathname?.startsWith('/chat/popup');

  if (isStandalone) {
    return <main className="flex-1 overflow-y-auto">{children}</main>;
  }

  return (
    <>
      <Sidebar />
      <main className="flex-1 overflow-y-auto flex flex-col min-w-0">
        <TopBar />
        <div className="max-w-7xl mx-auto w-full px-6 py-6">{children}</div>
      </main>
      <FloatingChat />
    </>
  );
}
