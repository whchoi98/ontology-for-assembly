import './globals.css';
import React from 'react';
import { GuidedTour } from '../components/GuidedTour';
import { Sidebar } from '../components/Sidebar';

export const metadata = {
  title: 'ontology-for-assembly',
  description: '한국 언론사 Agentic 온톨로지 PoC',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen flex">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-6xl mx-auto px-6 py-6">{children}</div>
        </main>
        <GuidedTour />
      </body>
    </html>
  );
}
