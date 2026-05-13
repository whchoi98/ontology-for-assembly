'use client';

/**
 * 시나리오 B - 3-stage 챗봇 (데모 메인) + SSE streaming (Phase 5 Track 5-5).
 *
 * 같은 질문에 Chatbot / Agent / Agentic 3 모드가 다르게 응답. SSE로 한 stage씩
 * 나타남 + Agent의 도구 호출·Agentic의 4 에이전트 진행이 log 이벤트로 실시간 표시.
 */
import React, { useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { chatStream, type StageResult } from '../../lib/api-client';

const SAMPLE_QUERIES = [
  '최근 1년간 AI 입법 활동이 활발한 의원 3명과 공동발의 네트워크 알려줘',
  '22대 국회 청년 주거지원 법안의 발의 추이는?',
  '환경·기후 관련 의안 중 양당 협력 사례를 찾아줘',
];

type StageKey = 'chatbot' | 'agent' | 'agentic';
const STAGE_ORDER: StageKey[] = ['chatbot', 'agent', 'agentic'];

const STAGE_LABEL: Record<string, string> = {
  chatbot: 'Chatbot (RAG)',
  agent: 'Agent (Tool Use)',
  agentic: 'Agentic AI (Multi-Agent)',
};


interface StageState {
  status: 'pending' | 'running' | 'done';
  approach?: string;
  logs: string[];                 // 실시간 도구/에이전트 호출
  result?: StageResult;
}


export default function ChatPage() {
  const [query, setQuery] = useState(SAMPLE_QUERIES[0]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stages, setStages] = useState<Record<StageKey, StageState>>({
    chatbot: { status: 'pending', logs: [] },
    agent: { status: 'pending', logs: [] },
    agentic: { status: 'pending', logs: [] },
  });
  const [totalMs, setTotalMs] = useState<number | null>(null);

  async function runChat(e: React.FormEvent) {
    e.preventDefault();
    setStreaming(true);
    setError(null);
    setTotalMs(null);
    // 초기화
    setStages({
      chatbot: { status: 'pending', logs: [] },
      agent: { status: 'pending', logs: [] },
      agentic: { status: 'pending', logs: [] },
    });

    const personaId = readPersonaIdSync();

    await chatStream(query, {
      onEvent: (e) => {
        if (e.type === 'phase') {
          const stage = e.data.stage as StageKey;
          setStages((prev) => ({
            ...prev,
            [stage]: { ...prev[stage], status: 'running', approach: e.data.approach },
          }));
        } else if (e.type === 'log') {
          const stage = e.data.stage as StageKey;
          const label = e.data.tool_called
            ? `도구: ${e.data.tool_called}`
            : e.data.agent_invoked
            ? `에이전트: ${e.data.agent_invoked}`
            : 'log';
          setStages((prev) => ({
            ...prev,
            [stage]: { ...prev[stage], logs: [...prev[stage].logs, label] },
          }));
        } else if (e.type === 'result') {
          const stage = e.data.stage as StageKey;
          setStages((prev) => ({
            ...prev,
            [stage]: { ...prev[stage], status: 'done', result: e.data },
          }));
        } else if (e.type === 'done') {
          setTotalMs(e.data.total_ms);
        }
      },
      onError: (err) => {
        setError(err.message);
      },
    }, { personaId });

    setStreaming(false);
  }

  return (
    <div>
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-mono text-sm text-gray-400">시나리오 B</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">
            데모 메인
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-medium">
            SSE streaming
          </span>
        </div>
        <h1 className="text-2xl font-bold mb-1">3-stage 진화 챗봇</h1>
        <p className="text-sm text-gray-600">
          같은 질문에 Chatbot / Agent / Agentic 3 모드가 어떻게 다르게 응답하는지 비교.
          Agent의 도구 호출과 Agentic의 4 에이전트 흐름이 실시간 표시.
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
            disabled={streaming || !query.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {streaming ? 'streaming…' : '3 모드 비교'}
          </button>
        </div>
      </form>

      {error && (
        <div className="border border-red-200 bg-red-50 text-red-800 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {STAGE_ORDER.map((stage) => (
          <StageCard key={stage} stage={stage} state={stages[stage]} />
        ))}
      </div>

      {totalMs !== null && (
        <p className="text-xs text-gray-500 text-right mt-3">총 {totalMs}ms</p>
      )}
    </div>
  );
}


function StageCard({ stage, state }: { stage: string; state: StageState }) {
  const r = state.result;
  return (
    <section className="border border-gray-200 rounded-lg p-4 bg-white">
      <header className="mb-3 pb-3 border-b border-gray-100">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">{STAGE_LABEL[stage]}</h2>
          <StatusBadge status={state.status} />
        </div>
        {state.approach && (
          <p className="text-xs text-gray-500 mt-0.5">{state.approach}</p>
        )}
      </header>

      {state.logs.length > 0 && (
        <div className="text-xs text-gray-500 mb-3 space-y-0.5 max-h-24 overflow-y-auto font-mono">
          {state.logs.map((log, idx) => (
            <div key={idx} className="flex items-center gap-1">
              <span className="text-gray-400">›</span>
              <span>{log}</span>
            </div>
          ))}
        </div>
      )}

      {r ? (
        <>
          <div className="text-sm text-gray-800 whitespace-pre-wrap mb-3">{r.text}</div>
          <div className="text-xs text-gray-500 space-y-1 border-t border-gray-100 pt-3">
            <div>도구: {r.tools_called.length} · 에이전트: {r.agents_invoked.length} · 출처: {r.sources_used.length}</div>
            <div className="flex items-center gap-2">
              score:{' '}
              <span className={r.alarm ? 'text-warn font-semibold' : 'text-badge-real font-semibold'}>
                {r.political_balance_score.toFixed(2)}
              </span>
              {r.alarm && <span className="text-warn">⚠</span>}
              <span className="text-gray-400 ml-auto">{r.duration_ms}ms</span>
            </div>
          </div>
        </>
      ) : (
        <div className="text-xs text-gray-400 italic py-4 text-center">
          {state.status === 'pending' ? '대기 중' : state.status === 'running' ? '실행 중...' : ''}
        </div>
      )}
    </section>
  );
}


function StatusBadge({ status }: { status: StageState['status'] }) {
  const config: Record<StageState['status'], { label: string; cls: string }> = {
    pending: { label: '대기', cls: 'bg-gray-100 text-gray-500' },
    running: { label: '진행 중', cls: 'bg-blue-100 text-blue-700 animate-pulse' },
    done: { label: '완료', cls: 'bg-green-100 text-green-700' },
  };
  const c = config[status];
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${c.cls}`}>
      {c.label}
    </span>
  );
}
