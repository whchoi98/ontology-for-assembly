'use client';

/**
 * 시나리오 D - 페르소나 매칭.
 *
 * 기사 선택(드롭다운) 또는 텍스트 입력 → 6 페르소나 점수 막대 + reasons +
 * 권장 사유 + affinity matrix 메타.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import {
  personaMatchApi,
  insightsApi,
  type MatchResult,
  type AffinityMatrixResponse,
  type ArticleListResponse,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';


export default function PersonaMatchPage() {
  const [mode, setMode] = useState<'article' | 'text'>('article');
  const [matrix, setMatrix] = useState<AffinityMatrixResponse | null>(null);
  const [articles, setArticles] = useState<ArticleListResponse | null>(null);
  const [selectedArticleId, setSelectedArticleId] = useState<string>('');
  const [text, setText] = useState('');
  const [hints, setHints] = useState<string>('');
  const [result, setResult] = useState<MatchResult | null>(null);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 매트릭스·기사 리스트 로드
  useEffect(() => {
    Promise.all([personaMatchApi.matrix(), insightsApi.articles({ limit: 30 })])
      .then(([m, a]) => {
        setMatrix(m);
        setArticles(a);
        if (a.articles.length > 0) setSelectedArticleId(a.articles[0].article_id);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const runMatch = useCallback(async () => {
    setMatching(true);
    setError(null);
    setResult(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      if (mode === 'article') {
        if (!selectedArticleId) {
          throw new Error('기사를 선택하세요.');
        }
        const r = await personaMatchApi.article(selectedArticleId, personaId);
        setResult(r);
      } else {
        if (!text.trim() || text.trim().length < 10) {
          throw new Error('텍스트는 최소 10자 이상.');
        }
        const hintArr = hints.split(',').map((s) => s.trim()).filter(Boolean);
        const r = await personaMatchApi.text(
          text, hintArr.length > 0 ? hintArr : undefined, personaId,
        );
        setResult(r);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMatching(false);
    }
  }, [mode, selectedArticleId, text, hints]);

  return (
    <div>
      <ScenarioHero code="D" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 입력 */}
        <section className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
          <div className="flex items-center gap-1 mb-3">
            <button
              onClick={() => setMode('article')}
              className={
                'text-xs px-3 py-1.5 rounded-md ' +
                (mode === 'article'
                  ? 'bg-blue-600 text-white font-medium'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700')
              }
            >
              기사 선택
            </button>
            <button
              onClick={() => setMode('text')}
              className={
                'text-xs px-3 py-1.5 rounded-md ' +
                (mode === 'text'
                  ? 'bg-blue-600 text-white font-medium'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700')
              }
            >
              텍스트 입력
            </button>
          </div>

          {mode === 'article' ? (
            <div>
              <label className="block text-xs text-slate-400 mb-1">합성 기사 풀 (30건)</label>
              <select
                value={selectedArticleId}
                onChange={(e) => setSelectedArticleId(e.target.value)}
                className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md px-2 py-1.5 text-slate-100 focus:outline-none focus:border-blue-500"
              >
                {articles?.articles.map((a) => (
                  <option key={a.article_id} value={a.article_id}>
                    {a.article_id} · {a.title.slice(0, 60)}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="space-y-2">
              <label className="block text-xs text-slate-400">텍스트 (10-4000자)</label>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={5}
                placeholder="기사 본문 또는 임의 콘텐츠를 입력하세요. 예) AI 산업 진흥 정책..."
                className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md p-2 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
              />
              <label className="block text-xs text-slate-400">
                카테고리 hints (선택, 쉼표 구분 - 산업·경제·사회·환경·법무·문화)
              </label>
              <input
                value={hints}
                onChange={(e) => setHints(e.target.value)}
                placeholder="예) 산업, 경제"
                className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          )}

          <button
            onClick={runMatch}
            disabled={matching}
            className="mt-3 w-full text-xs px-3 py-2 rounded-md bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:bg-slate-700"
          >
            {matching ? '매칭 중…' : '매칭 실행'}
          </button>
        </section>

        {/* 결과 */}
        <section>
          {result ? (
            <MatchResultPanel result={result} matrix={matrix} />
          ) : (
            <p className="text-sm text-slate-500">매칭 실행을 눌러주세요.</p>
          )}
        </section>
      </div>

      {/* affinity matrix 메타 */}
      {matrix && (
        <section className="mt-6 border border-slate-800 rounded-lg bg-slate-900/40 p-4">
          <h2 className="text-sm font-bold text-white mb-2">
            페르소나 × 토픽 카테고리 affinity 매트릭스
          </h2>
          <p className="text-xs text-slate-400 mb-3">{matrix.note}</p>
          <AffinityMatrixTable matrix={matrix.matrix} />
          <div className="mt-3 text-[11px] text-slate-400">
            가중치: topic_affinity {matrix.weights.topic_affinity} · kpi_keyword {matrix.weights.kpi_keyword} · tone_fit {matrix.weights.tone_fit}
          </div>
        </section>
      )}

      {result ? (
        <AIInsightPanel scenarioCode="D" autoGenerate context={{
          article_id: result.source_id ?? selectedArticleId,
          source_kind: result.source_kind,
          article_title: result.title,
          content_excerpt: result.content_excerpt?.slice(0, 300) ?? '',
          topic_categories: result.topic_categories,
          balance_score: result.balance_score,
          top_persona_id: result.top_persona_id,
          persona_scores: result.scores.map((s) => ({ persona_id: s.persona_id, score: s.score })),
          rationale: result.rationale?.slice(0, 400) ?? '',
        }} />
      ) : (
        <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          기사 또는 텍스트 매칭 실행 후 *해당 결과 specific* AI 인사이트가 표시됩니다.
        </div>
      )}
    </div>
  );
}


function MatchResultPanel({
  result, matrix,
}: { result: MatchResult; matrix: AffinityMatrixResponse | null }) {
  const maxScore = Math.max(...result.scores.map((s) => s.score), 0.0001);
  return (
    <div className="space-y-3">
      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <div className="text-[10px] text-slate-400 mb-1">매칭 결과</div>
        <h3 className="text-sm font-semibold text-white line-clamp-2">{result.title}</h3>
        <p className="text-xs text-slate-300 mt-1 line-clamp-3">{result.content_excerpt}</p>
        <div className="flex items-center gap-2 mt-2 text-[10px]">
          {result.topic_categories.map((c) => (
            <span key={c} className="px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-400/40 text-purple-200">{c}</span>
          ))}
          <span className="text-slate-400 ml-2">
            balance {result.balance_score.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
        <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">
          추천 ({result.top_persona_id})
        </div>
        <p className="text-xs text-amber-100">{result.rationale}</p>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h3 className="text-xs uppercase text-slate-400 mb-2">6 페르소나 점수</h3>
        <div className="space-y-2">
          {result.scores.map((s, i) => (
            <ScoreBar key={s.persona_id} score={s} maxScore={maxScore} rank={i + 1} />
          ))}
        </div>
      </div>
    </div>
  );
}


function ScoreBar({
  score, maxScore, rank,
}: { score: import('../../lib/scenario-clients').PersonaScore; maxScore: number; rank: number }) {
  const pct = (score.score / maxScore) * 100;
  const isTop = rank === 1;
  return (
    <div>
      <div className="flex items-center justify-between mb-0.5 text-xs">
        <span className={`font-medium ${isTop ? 'text-blue-300' : 'text-slate-200'}`}>
          {rank}. {score.name_kr}
          <span className="text-[10px] text-slate-500 ml-1 font-mono">{score.persona_id}</span>
        </span>
        <span className="font-mono font-semibold">{score.score.toFixed(3)}</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden mb-1">
        <div
          className={`h-2 ${isTop ? 'bg-blue-600' : 'bg-slate-600'} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex gap-2 text-[10px] text-slate-400 mb-1">
        <span>topic {score.topic_affinity.toFixed(2)}</span>
        <span>kpi {score.kpi_keyword_match.toFixed(2)}</span>
        <span>tone {score.tone_fit.toFixed(2)}</span>
      </div>
      <ul className="text-[10px] text-slate-300 space-y-0.5">
        {score.reasons.map((r, i) => (
          <li key={i} className="ml-3 list-disc">{r}</li>
        ))}
      </ul>
    </div>
  );
}


function AffinityMatrixTable({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const categories = Array.from(
    new Set(Object.values(matrix).flatMap((row) => Object.keys(row))),
  );
  const personas = Object.keys(matrix);
  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse">
        <thead>
          <tr>
            <th className="border border-slate-800 px-2 py-1 bg-slate-800/40 text-left">페르소나 \ 카테고리</th>
            {categories.map((c) => (
              <th key={c} className="border border-slate-800 px-2 py-1 bg-slate-800/40">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {personas.map((p) => (
            <tr key={p}>
              <td className="border border-slate-800 px-2 py-1 font-mono font-medium">{p}</td>
              {categories.map((c) => {
                const v = matrix[p]?.[c] ?? 0;
                const intensity = v / 5;
                return (
                  <td
                    key={c}
                    className="border border-slate-800 px-2 py-1 text-center font-mono"
                    style={{ backgroundColor: `rgba(59, 130, 246, ${intensity * 0.5})` }}
                  >
                    {v}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
