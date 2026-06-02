import './globals.css';
import React from 'react';
import { AppShell } from '../components/AppShell';

export const metadata = {
  title: 'ontology-for-assembly',
  description: '한국 언론사 Agentic 온톨로지 PoC',
};

// 페르소나 토글 시 stale cache 응답 방지 - 모든 페이지 dynamic 렌더 강제
// (Next.js standalone build의 default s-maxage=31536000 cache header 무효화)
export const dynamic = 'force-dynamic';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className="dark">
      <body className="min-h-screen flex bg-slate-950 text-slate-100">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
