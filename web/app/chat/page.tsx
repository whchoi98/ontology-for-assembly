'use client';

/**
 * 시나리오 B - 3-stage 챗봇 (데모 메인).
 *
 * 같은 질문에 Chatbot / Agent / Agentic 3 모드가 다르게 응답하는지 사이드바이사이드 비교.
 * 페르소나 차별: 본문은 같지만 페르소나마다 다른 형식·어조.
 */
import React, { useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { chat, type ChatResponse, type StageResult } from '../../lib/api-client';

const SAMPLE_QUERIES = [
  '최근 1년간 AI 입법 활동이 활발한 의원 3명과 공동발의 네트워크 알려줘',
  '22대 국회 청년 주거지원 법안의 발의 추이는?',
  '환경·기후 관련 의안 중 양당 협력 사례를 찾아줘',
];

const STAGE_ORDER: Array<'chatbot' | 'agent' | 'agentic'> = ['chatbot', 'agent', 'agentic'];

const STAGE_LABEL: Record<string, string> = {
  chatbot: 'Chatbot (RAG)',
  agent: 'Agent (Tool Use)',
  agentic: 'Agentic AI (Multi-Agent)',
};

export default function ChatPage() {
  const [query, setQuery] = useState(SAMPLE_QUERIES[0]);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runChat(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const personaId = readPersonaIdSync();
      const response = await chat(query, 'compare', { personaId });
      setResult(response);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-mono text-sm text-gray-400">시나리오 B</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">
            데모 메인
          </span>
        </div>
        <h1 className="text-2xl font-bold mb-1">3-stage 진화 챗봇</h1>
        <p className="text-sm text-gray-600">
          같은 질문에 Chatbot / Agent / Agentic 3 모드가 어떻게 다르게 응답하는지 비교.
        </p>
      </header>

      <form onSubmit={runChat} className="mb-4">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={3}
          className="w-full border border-gray-300 rounded-md px-3 py-2 mb-2 focus:outline-none focus:ring-2 focus:ring-blue-300"
          maxLength={2000}
        />
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap gap-1.5">
            {SAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => setQuery(q)}
                className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-700"
              >
                {q.length > 40 ? q.slice(0, 40) + '…' : q}
              </button>
            ))}
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? '실행 중…' : '3 모드 비교'}
          </button>
        </div>
      </form>

      {error && (
        <div className="border border-red-200 bg-red-50 text-red-800 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {STAGE_ORDER.map((stage) => {
            const r = result.results[stage];
            if (!r) return null;
            return <StageCard key={stage} stage={stage} result={r} />;
          })}
        </div>
      )}
    </div>
  );
}


function StageCard({ stage, result }: { stage: string; result: StageResult }) {
  return (
    <section className="border border-gray-200 rounded-lg p-4 bg-white">
      <header className="mb-3 pb-3 border-b border-gray-100">
        <h2 className="font-semibold text-gray-900">{STAGE_LABEL[stage]}</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          {(result.extras as { approach?: string })?.approach ?? stage}
        </p>
      </header>

      <div className="text-sm text-gray-800 whitespace-pre-wrap mb-3">{result.text}</div>

      <div className="text-xs text-gray-500 space-y-1 border-t border-gray-100 pt-3">
        <div>도구 호출: {result.tools_called.length}개 {result.tools_called.length > 0 && `(${result.tools_called.join(', ')})`}</div>
        <div>에이전트: {result.agents_invoked.length}개 {result.agents_invoked.length > 0 && `(${result.agents_invoked.join(' → ')})`}</div>
        <div>출처: {result.sources_used.length} 건</div>
        <div className="flex items-center gap-2">
          political_balance_score:{' '}
          <span className={result.alarm ? 'text-warn font-semibold' : 'text-badge-real font-semibold'}>
            {result.political_balance_score.toFixed(2)}
          </span>
          {result.alarm && <span className="text-warn">⚠ 알람</span>}
        </div>
        <div className="text-gray-400">{result.duration_ms}ms</div>
      </div>

      {(result.extras as { limitation?: string })?.limitation && (
        <p className="text-[11px] text-gray-500 mt-2 italic">
          한계: {(result.extras as { limitation?: string }).limitation}
        </p>
      )}
    </section>
  );
}
