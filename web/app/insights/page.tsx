'use client';

/**
 * 시나리오 C - 기사 인사이트.
 *
 * 기사 리스트 (페이징·토픽 필터) + 선택 시 디테일 (인사이트 bullet + 정치 균형 + 참조 entity).
 */
import React, { useCallback, useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { BiasScoreIndicator } from '../../components/BiasScoreIndicator';
import {
  insightsApi,
  type ArticleListResponse,
  type InsightDetailResponse,
  type TopicsResponse,
} from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';
import { AIInsightPanel } from '../../components/AIInsightPanel';
import ScenarioHero from '../../components/ScenarioHero';

const PAGE_SIZE = 10;

export default function InsightsPage() {
  const [topics, setTopics] = useState<TopicsResponse | null>(null);
  const [topicId, setTopicId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<ArticleListResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InsightDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 토픽 카탈로그 로드 (once)
  useEffect(() => {
    insightsApi.topics().then(setTopics).catch((e) => setError((e as Error).message));
  }, []);

  // 리스트 로드 (offset/topic 변경 시)
  const loadList = useCallback(async () => {
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const r = await insightsApi.articles({
        offset, limit: PAGE_SIZE, topicId: topicId ?? undefined, personaId,
      });
      setList(r);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [offset, topicId]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  // 디테일 로드 (선택 시)
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const personaId = readPersonaIdSync() as PersonaId;
    insightsApi
      .detail(selectedId, personaId)
      .then(setDetail)
      .catch((e) => setError((e as Error).message));
  }, [selectedId]);

  return (
    <div>
      <ScenarioHero code="C" subtitle="합성 기사 60건" />

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {/* 토픽 필터 */}
      {topics && (
        <div className="mb-4">
          <div className="text-xs uppercase text-slate-400 mb-1">토픽 필터 ({topics.total})</div>
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => { setTopicId(null); setOffset(0); }}
              className={
                'text-xs px-2.5 py-1.5 rounded-md border ' +
                (topicId === null
                  ? 'border-blue-500 bg-blue-500/15 text-blue-300 font-medium'
                  : 'border-slate-800 bg-slate-900/40 text-slate-200 hover:bg-slate-800/40')
              }
            >
              전체
            </button>
            {topics.topics.slice(0, 12).map((t) => (
              <button
                key={t.topic_id}
                onClick={() => { setTopicId(t.topic_id); setOffset(0); }}
                className={
                  'text-xs px-2.5 py-1.5 rounded-md border ' +
                  (topicId === t.topic_id
                    ? 'border-blue-500 bg-blue-500/15 text-blue-300 font-medium'
                    : 'border-slate-800 bg-slate-900/40 text-slate-200 hover:bg-slate-800/40')
                }
              >
                {t.name}
                <span className="ml-1 text-[10px] text-slate-500">{t.category}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* 리스트 */}
        <section className="lg:col-span-2 space-y-2">
          {list && (
            <>
              <div className="flex justify-between items-baseline text-xs text-slate-400 mb-1">
                <span>총 {list.total}건 · 페이지 {Math.floor(offset / PAGE_SIZE) + 1}</span>
                <div className="flex gap-1">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="px-2 py-0.5 rounded border border-slate-700 bg-slate-900/40 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800/40"
                  >
                    ← 이전
                  </button>
                  <button
                    disabled={offset + PAGE_SIZE >= list.total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="px-2 py-0.5 rounded border border-slate-700 bg-slate-900/40 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800/40"
                  >
                    다음 →
                  </button>
                </div>
              </div>
              {list.articles.map((a) => (
                <button
                  key={a.article_id}
                  onClick={() => setSelectedId(a.article_id)}
                  className={
                    'block w-full text-left border rounded-md p-3 transition-colors ' +
                    (selectedId === a.article_id
                      ? 'border-blue-500 bg-blue-500/15'
                      : 'border-slate-800 bg-slate-900/40 hover:border-slate-600')
                  }
                >
                  <div className="text-sm font-semibold text-white line-clamp-2">
                    {a.title}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-400">
                    <span className="font-mono">{a.published_at.slice(0, 10)}</span>
                    {a.primary_topic && (
                      <span className="px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-400/40 text-purple-200 font-medium">
                        {a.primary_topic.name}
                      </span>
                    )}
                    <span>의원 {a.referenced_persons}</span>
                    <span>의안 {a.referenced_bills}</span>
                  </div>
                </button>
              ))}
            </>
          )}
        </section>

        {/* 디테일 */}
        <section className="lg:col-span-3">
          {detail ? (
            <ArticleDetail detail={detail} />
          ) : (
            <p className="text-sm text-slate-500">기사를 선택하세요.</p>
          )}
        </section>
      </div>
      {/* 선택 기사를 context로 전달 → 기사 변경 시 AI 인사이트 자동 재호출 */}
      <AIInsightPanel scenarioCode="C" context={detail} autoGenerate />
    </div>
  );
}


function ArticleDetail({ detail }: { detail: InsightDetailResponse }) {
  return (
    <div className="space-y-4">
      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] text-slate-400 font-mono">{detail.article_id}</span>
          <span className="text-[10px] text-slate-400">{detail.published_at.slice(0, 10)}</span>
          <span className="text-[10px] text-slate-400">by {detail.author}</span>
        </div>
        <h2 className="text-lg font-bold text-white mb-2">{detail.title}</h2>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {detail.topics.map((t) => (
            <span
              key={t.topic_id}
              className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-400/40 text-purple-200 font-medium"
            >
              {t.name}
            </span>
          ))}
        </div>
        <p className="text-xs text-slate-200 leading-relaxed whitespace-pre-line">
          {detail.content}
        </p>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h3 className="text-xs uppercase text-slate-400 mb-2">정치 균형 점수</h3>
        <BiasScoreIndicator
          score={detail.political_balance_score}
          alarm={detail.balance_alarm}
          size="md"
        />
      </div>

      <div className="border border-amber-500/30 bg-amber-500/10 p-3 rounded">
        <div className="text-[10px] uppercase text-amber-300 font-semibold mb-1">
          AI 요약
        </div>
        <p className="text-xs text-amber-100 leading-relaxed">{detail.summary}</p>
      </div>

      <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
        <h3 className="text-xs uppercase text-slate-400 mb-2">인사이트 ({detail.insights.length})</h3>
        <ul className="space-y-1.5">
          {detail.insights.map((insight, i) => (
            <li key={i} className="text-xs text-slate-200 flex gap-2">
              <span className="text-amber-600 mt-0.5">●</span>
              <span>{insight}</span>
            </li>
          ))}
        </ul>
      </div>

      {(detail.referenced_person_ids.length > 0 || detail.referenced_bill_ids.length > 0) && (
        <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-4">
          <h3 className="text-xs uppercase text-slate-400 mb-2">참조 엔티티</h3>
          {detail.referenced_person_ids.length > 0 && (
            <div className="mb-2">
              <div className="text-[10px] text-slate-400 mb-1">의원 ({detail.referenced_person_ids.length})</div>
              <div className="flex flex-wrap gap-1">
                {detail.referenced_person_ids.map((pid) => (
                  <span key={pid} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300">
                    {pid}
                  </span>
                ))}
              </div>
            </div>
          )}
          {detail.referenced_bill_ids.length > 0 && (
            <div>
              <div className="text-[10px] text-slate-400 mb-1">의안 ({detail.referenced_bill_ids.length})</div>
              <div className="flex flex-wrap gap-1">
                {detail.referenced_bill_ids.map((bid) => (
                  <span key={bid} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-400/30 text-emerald-200">
                    {bid}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 페르소나별 hint */}
      {detail.extras.follow_up_hint && (
        <PersonaHint color="amber" label="후속 취재" text={detail.extras.follow_up_hint} />
      )}
      {detail.extras.cohort_hint && (
        <PersonaHint color="cyan" label="코호트 매칭" text={detail.extras.cohort_hint} />
      )}
      {detail.extras.ad_hint && (
        <PersonaHint color="orange" label="광고 매칭" text={detail.extras.ad_hint} />
      )}
      {detail.extras.guide_hint && (
        <PersonaHint color="emerald" label="안내" text={detail.extras.guide_hint} />
      )}
      {detail.extras.premium_cta && (
        <PersonaHint color="purple" label="Premium" text={detail.extras.premium_cta} />
      )}
      {detail.extras.api_response_hint && (
        <PersonaHint color="gray" label="API" text={detail.extras.api_response_hint} />
      )}
    </div>
  );
}


function PersonaHint({ color, label, text }: { color: string; label: string; text: string }) {
  const colors: Record<string, string> = {
    amber: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
    cyan: 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200',
    orange: 'border-orange-400/40 bg-orange-500/15 text-orange-200',
    emerald: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
    purple: 'border-purple-400 bg-purple-500/15 text-purple-100',
    gray: 'border-slate-600 bg-slate-800/40 text-slate-200',
  };
  return (
    <div className={`border p-3 rounded ${colors[color] ?? colors.gray}`}>
      <div className="text-[10px] uppercase font-semibold mb-1">{label}</div>
      <p className="text-xs leading-relaxed">{text}</p>
    </div>
  );
}
