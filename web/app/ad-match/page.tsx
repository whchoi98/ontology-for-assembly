'use client';

/**
 * 시나리오 L - 광고 매칭 매트릭스 (AI 거버넌스 데모 메인).
 *
 * 3 모드(keyword/embedding/agent) 사이드바이사이드 비교 + 광고 거절 trace.
 * 비위 의혹 콘텐츠(DEMO_TRAGIC_ARTICLE_ID)에서 Agent만 광고 거절 → 청중에게
 * AI 거버넌스 메시지 직관 전달.
 */
import React, { useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { adMatch, type AdMatchDecision, type AdMatchResponse } from '../../lib/api-client';

const SAMPLE_ARTICLES = [
  {
    id: 'art_safe_AI',
    label: '안전: AI 산업 진흥 분석',
    description: '정책 정보성 - 모든 모드가 광고 매칭',
  },
  {
    id: 'art_DEMO_TRAGIC_001',
    label: '★ 비위 의혹: 검찰 수사 진행 중',
    description: 'AI 거버넌스 시연 - Agent만 거절',
  },
];

const MODE_ORDER: Array<'keyword' | 'embedding' | 'agent'> = ['keyword', 'embedding', 'agent'];

const MODE_LABEL: Record<string, string> = {
  keyword: 'Keyword Matching',
  embedding: 'Embedding Similarity',
  agent: 'Agent Judgment (★)',
};

export default function AdMatchPage() {
  const [articleId, setArticleId] = useState(SAMPLE_ARTICLES[1].id);  // ★ 비위 의혹 기본
  const [result, setResult] = useState<AdMatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runMatch() {
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
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-mono text-sm text-gray-400">시나리오 L</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">
            AI 거버넌스
          </span>
        </div>
        <h1 className="text-2xl font-bold mb-1">광고 매칭 매트릭스 - 3-way 비교</h1>
        <p className="text-sm text-gray-600">
          keyword vs embedding vs Agent. 같은 콘텐츠·후보에 대해 세 모드가 어떻게 다르게
          결정하는지 시연.
        </p>
      </header>

      <div className="mb-6 space-y-3">
        <div className="text-xs uppercase text-gray-500">시연 콘텐츠 선택</div>
        <div className="flex flex-wrap gap-2">
          {SAMPLE_ARTICLES.map((a) => {
            const active = articleId === a.id;
            return (
              <button
                key={a.id}
                onClick={() => setArticleId(a.id)}
                className={
                  'border rounded-md px-3 py-2 text-left text-sm ' +
                  (active
                    ? 'border-blue-500 bg-blue-50 text-blue-900'
                    : 'border-gray-200 bg-white hover:bg-gray-50')
                }
              >
                <div className="font-semibold">{a.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{a.description}</div>
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
        <div className="border border-red-200 bg-red-50 text-red-800 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="mb-4 border-l-4 border-amber-400 bg-amber-50 p-3 text-sm">
            <strong>거버넌스 요약:</strong> {result.governance_summary.key_message}
            {result.governance_summary.modes_skipped_ads.length > 0 && (
              <span className="ml-2 text-amber-900">
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
          ? 'border-red-300 bg-red-50'
          : 'border-gray-200 bg-white')
      }
    >
      <header className="mb-3 pb-3 border-b border-gray-100">
        <h2 className="font-semibold text-gray-900">{MODE_LABEL[mode]}</h2>
      </header>

      <div className="mb-3">
        <div className="text-xs text-gray-500 mb-1">결정</div>
        {skipped ? (
          <div className="text-base font-bold text-red-700">★ 광고 노출 생략</div>
        ) : (
          <div>
            <span className="font-mono text-sm">{decision.chosen_ad_id}</span>
            <span className="ml-2 text-xs text-gray-500">
              score {decision.score.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      <div>
        <div className="text-xs text-gray-500 mb-1">근거 (audit trace)</div>
        <p className="text-xs text-gray-700 whitespace-pre-wrap leading-relaxed">
          {decision.reason_text}
        </p>
      </div>

      <div className="text-[11px] text-gray-400 mt-3 pt-2 border-t border-gray-100">
        후보 {decision.candidate_ad_ids.length}개 · decision_id={decision.decision_id.slice(0, 16)}…
      </div>
    </section>
  );
}
