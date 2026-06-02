'use client';

/**
 * 시나리오 A - 의미 검색 페이지.
 *
 * 클라이언트 컴포넌트 - PersonaSwitch가 localStorage에 저장한 페르소나로 API 호출.
 * 검색 결과 + top hit 1-hop subgraph.
 */
import React, { useState } from 'react';
import { CytoscapeView } from '../../components/CytoscapeView';
import { DataSourceBadge } from '../../components/DataSourceBadge';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { search, type SearchResponse } from '../../lib/api-client';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

export default function SearchPage() {
  const [query, setQuery] = useState('AI 입법');
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const personaId = readPersonaIdSync();
      const response = await search(query, { personaId });
      setResult(response);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <ScenarioHero code="A" />

      <form onSubmit={runSearch} className="mb-3 flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
          placeholder="검색어 입력 (예: AI 입법, 청년 주거지원)"
          maxLength={500}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '검색 중…' : '검색'}
        </button>
      </form>

      {/* 추천 자연어 검색 (10개) — 시연 시 빠른 데모 진입점 */}
      <div className="mb-6">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
          추천 검색어 — 시연 진입점 (click)
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[
            'AI 입법', 'AI 산업 진흥', '데이터·개인정보 보호', '청년 주거 지원',
            '환경·기후 정책', '사회복지 확대', '교육 격차 해소', '디지털 전환',
            '에너지 전환', '소상공인 지원',
          ].map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setQuery(q);
                // 검색 자동 실행 — async 호출은 form submit 모방
                setLoading(true); setError(null);
                import('../../components/PersonaSwitch').then(({ readPersonaIdSync }) => {
                  const personaId = readPersonaIdSync();
                  import('../../lib/api-client').then(({ search }) => {
                    search(q, { personaId })
                      .then(setResult)
                      .catch((err) => setError(String(err)))
                      .finally(() => setLoading(false));
                  });
                });
              }}
              className="px-2.5 py-1 text-xs rounded-full bg-slate-800/80 border border-slate-700 text-slate-200 hover:bg-blue-500/15 hover:border-blue-500/50 hover:text-blue-200 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {result && (
        <div>
          <div className="mb-4 flex items-center gap-3 text-sm text-slate-300">
            <span>페르소나: <strong>{result.persona_id}</strong></span>
            <span>cohort:</span>
            {result.cohort_used.map((s) => <DataSourceBadge key={s} source={s} size="xs" />)}
            <span className="ml-auto">{result.hits.length} hit</span>
          </div>

          <ul className="space-y-3 mb-6">
            {result.hits.map((hit) => (
              <li key={hit.id} className="border border-slate-800 rounded-lg p-4 bg-slate-900/40">
                <div className="flex items-start justify-between gap-3 mb-1.5">
                  <h3 className="font-semibold text-white">{hit.title}</h3>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <DataSourceBadge source={hit.source} size="xs" />
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                      {hit.node_type}
                    </span>
                    <span className="text-xs text-slate-500 font-mono">
                      {hit.score.toFixed(2)}
                    </span>
                  </div>
                </div>
                <p className="text-sm text-slate-300">{hit.snippet}</p>
              </li>
            ))}
          </ul>

          {result.top_hit_subgraph && (
            <section className="space-y-2">
              <h2 className="font-semibold text-white">Top hit 1-hop subgraph</h2>
              <CytoscapeView subgraph={result.top_hit_subgraph} height={400} />
              <details className="text-xs">
                <summary className="text-slate-400 cursor-pointer hover:text-slate-200">
                  JSON raw 데이터 (디버깅)
                </summary>
                <pre className="text-xs mt-2 overflow-x-auto bg-slate-900/40 p-2 rounded border border-slate-800">
                  {JSON.stringify(result.top_hit_subgraph, null, 2)}
                </pre>
              </details>
            </section>
          )}
        </div>
      )}
      <AIInsightPanel scenarioCode="A" context={result} />
    </div>
  );
}
