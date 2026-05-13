'use client';

/**
 * 시나리오 A - 의미 검색 페이지.
 *
 * 클라이언트 컴포넌트 - PersonaSwitch가 localStorage에 저장한 페르소나로 API 호출.
 * 검색 결과 + top hit 1-hop subgraph.
 */
import React, { useState } from 'react';
import { DataSourceBadge } from '../../components/DataSourceBadge';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { search, type SearchResponse } from '../../lib/api-client';

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
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-mono text-sm text-gray-400">시나리오 A</span>
        </div>
        <h1 className="text-2xl font-bold mb-1">의안·의원 의미 검색</h1>
        <p className="text-sm text-gray-600">
          BM25(Nori) + Cohere embed-v4 KNN + RRF + rerank-v3. 페르소나에 따라 top_k 자동 조정.
        </p>
      </header>

      <form onSubmit={runSearch} className="mb-6 flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300"
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

      {error && (
        <div className="border border-red-200 bg-red-50 text-red-800 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {result && (
        <div>
          <div className="mb-4 flex items-center gap-3 text-sm text-gray-600">
            <span>페르소나: <strong>{result.persona_id}</strong></span>
            <span>cohort:</span>
            {result.cohort_used.map((s) => <DataSourceBadge key={s} source={s} size="xs" />)}
            <span className="ml-auto">{result.hits.length} hit</span>
          </div>

          <ul className="space-y-3 mb-6">
            {result.hits.map((hit) => (
              <li key={hit.id} className="border border-gray-200 rounded-lg p-4 bg-white">
                <div className="flex items-start justify-between gap-3 mb-1.5">
                  <h3 className="font-semibold text-gray-900">{hit.title}</h3>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <DataSourceBadge source={hit.source} size="xs" />
                    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                      {hit.node_type}
                    </span>
                    <span className="text-xs text-gray-400 font-mono">
                      {hit.score.toFixed(2)}
                    </span>
                  </div>
                </div>
                <p className="text-sm text-gray-600">{hit.snippet}</p>
              </li>
            ))}
          </ul>

          {result.top_hit_subgraph && (
            <section className="border border-gray-200 rounded-lg p-4 bg-gray-50">
              <h2 className="font-semibold mb-2">
                Top hit 1-hop subgraph: {result.top_hit_subgraph.root_id}
              </h2>
              <div className="text-sm text-gray-700 mb-2">
                <strong>{result.top_hit_subgraph.nodes.length}</strong> 노드 ·{' '}
                <strong>{result.top_hit_subgraph.edges.length}</strong> 엣지
                <span className="text-xs text-gray-500 ml-2">
                  (Cytoscape 시각화는 후속 phase)
                </span>
              </div>
              <details>
                <summary className="text-sm text-gray-500 cursor-pointer">자세히</summary>
                <pre className="text-xs mt-2 overflow-x-auto bg-white p-2 rounded border border-gray-200">
                  {JSON.stringify(result.top_hit_subgraph, null, 2)}
                </pre>
              </details>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
