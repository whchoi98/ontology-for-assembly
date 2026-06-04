'use client';

/**
 * 시나리오 L - 광고 매칭 매트릭스 (AI 거버넌스 데모 메인).
 *
 * 3 모드(keyword/embedding/agent) 사이드바이사이드 비교 + 광고 거절 trace.
 * 비위 의혹 콘텐츠(DEMO_TRAGIC_ARTICLE_ID)에서 Agent만 광고 거절 → 청중에게
 * AI 거버넌스 메시지 직관 전달.
 */
import React, { useState, useEffect } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { adMatch, fetchAdMatchSamples, type AdMatchDecision, type AdMatchResponse, type AdMatchSample } from '../../lib/api-client';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';


const MODE_ORDER: Array<'keyword' | 'embedding' | 'agent'> = ['keyword', 'embedding', 'agent'];

const MODE_LABEL: Record<string, string> = {
  keyword: 'Keyword Matching',
  embedding: 'Embedding Similarity',
  agent: 'Agent Judgment (★)',
};

export default function AdMatchPage() {
  const [samples, setSamples] = useState<AdMatchSample[]>([]);
  const [articleId, setArticleId] = useState<string>('');
  const [result, setResult] = useState<AdMatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdMatchSamples()
      .then((rows) => {
        setSamples(rows);
        const firstSkip = rows.find((r) => r.expected_governance.startsWith('skip'));
        setArticleId(firstSkip?.article_id ?? rows[0]?.article_id ?? '');
      })
      .catch(() => setSamples([]));
  }, []);

  async function runMatch() {
    if (!articleId) return;
    setLoading(true);
    setError(null);
    try {
      const personaId = readPersonaIdSync();
      const response = await adMatch(articleId, 'compare', { personaId });
      setResult(response);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <ScenarioHero code="L" subtitle="AI 거버넌스 · 3-way" />

      <div className="mb-6 space-y-3">
        <div className="text-xs uppercase text-slate-400">시연 콘텐츠 선택</div>
        <div className="flex flex-wrap gap-2">
          {samples.map((a) => {
            const active = articleId === a.article_id;
            const isSkip = a.expected_governance.startsWith('skip');
            return (
              <button
                key={a.article_id}
                onClick={() => setArticleId(a.article_id)}
                className={
                  'border rounded-md px-3 py-2 text-left text-sm ' +
                  (active
                    ? 'border-blue-500 bg-blue-500/15 text-blue-100'
                    : 'border-slate-800 bg-slate-900/40 hover:bg-slate-800/40')
                }
              >
                <div className="font-semibold">{a.title}</div>
                <div className="mt-1">
                  {isSkip ? (
                    <span className="text-xs text-amber-400">Agent 거절 예상</span>
                  ) : (
                    <span className="text-xs text-emerald-400">안전 매칭</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
        <button
          onClick={runMatch}
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '매칭 실행 중…' : '3 모드 매칭 비교'}
        </button>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="mb-4 border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
            <strong>거버넌스 요약:</strong> {result.governance_summary.key_message}
            {result.governance_summary.modes_skipped_ads.length > 0 && (
              <span className="ml-2 text-amber-100">
                (거절: {result.governance_summary.modes_skipped_ads.join(', ')})
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {MODE_ORDER.map((mode) => {
              const d = result.results[mode];
              if (!d) return null;
              return <DecisionCard key={mode} mode={mode} decision={d} />;
            })}
          </div>
        </>
      )}
      <AIInsightPanel scenarioCode="L" context={result} />
    </div>
  );
}


function DecisionCard({ mode, decision }: { mode: string; decision: AdMatchDecision }) {
  const skipped = decision.chosen_ad_id === null;
  return (
    <section
      className={
        'border rounded-lg p-4 ' +
        (skipped
          ? 'border-red-300 bg-red-500/15'
          : 'border-slate-800 bg-slate-900/40')
      }
    >
      <header className="mb-3 pb-3 border-b border-slate-800">
        <h2 className="font-semibold text-white">{MODE_LABEL[mode]}</h2>
      </header>

      <div className="mb-3">
        <div className="text-xs text-slate-400 mb-1">결정</div>
        {skipped ? (
          <div className="text-base font-bold text-red-300">★ 광고 노출 생략</div>
        ) : (
          <div>
            <span className="font-mono text-sm">{decision.chosen_ad_id}</span>
            <span className="ml-2 text-xs text-slate-400">
              score {decision.score.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      <div>
        <div className="text-xs text-slate-400 mb-1">근거 (audit trace)</div>
        <p className="text-xs text-slate-200 whitespace-pre-wrap leading-relaxed">
          {decision.reason_text}
        </p>
      </div>

      <div className="text-[11px] text-slate-500 mt-3 pt-2 border-t border-slate-800">
        후보 {decision.candidate_ad_ids.length}개 · decision_id={decision.decision_id.slice(0, 16)}…
      </div>
    </section>
  );
}
