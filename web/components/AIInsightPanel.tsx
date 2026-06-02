'use client';

/**
 * AIInsightPanel — gcc 패턴 차용, 14 시나리오 페이지 공통 컴포넌트.
 *
 * 시나리오 응답 데이터를 context로 백엔드에 전달 → Sonnet 4.6 페르소나별 해석.
 * 정치 중립성 가드 + balance_score 자동 적용 (api/services/bedrock.invoke).
 *
 * 사용:
 *   <AIInsightPanel scenarioCode="D" context={resultData} />
 */
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { readPersonaIdSync } from './PersonaSwitch';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';


interface InsightResponse {
  scenario_code: string;
  scenario_label: string;
  persona_id: string;
  tier_group_kr: string;
  text: string;
  political_balance_score: number;
  alarm: boolean;
  model_id: string;
}


export function AIInsightPanel({
  scenarioCode,
  context,
  userQuery,
  autoGenerate = false,
  title = 'AI 인사이트',
}: {
  scenarioCode: string;
  context: unknown;
  userQuery?: string;
  autoGenerate?: boolean;
  title?: string;
}) {
  const [insight, setInsight] = useState<InsightResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true); setError(null);
    try {
      const personaId = readPersonaIdSync();
      const r = await fetch(`${BASE}/api/insight`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Persona-Id': personaId,
        },
        body: JSON.stringify({
          scenario_code: scenarioCode,
          context: context ?? {},
          user_query: userQuery,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setInsight(data as InsightResponse);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // context는 매 parent render마다 *새 object reference* → useEffect deps에 직접 넣으면
  // *무한 재실행* (Kiro review gate high-severity). Fix: stable identifier key 추출.
  // 우선순위: person_id → article_id → assembly_id → id → JSON hash (truncated).
  const contextKey = React.useMemo(() => {
    if (!context || typeof context !== 'object') return null;
    const c = context as Record<string, unknown>;
    for (const f of ['person_id', 'article_id', 'assembly_id', 'id', 'bill_id', 'topic_id', 'outlier_id', 'vote_id', 'fusion_id', 'petition_id', 'promise_id', 'burst_id', 'relation_id', 'committee_id']) {
      const v = c[f];
      if (typeof v === 'string' && v) return `${f}:${v}`;
    }
    // fallback: JSON 첫 200자 hash (object 변경 감지 가능 + 비용 제한)
    try {
      return JSON.stringify(context).slice(0, 200);
    } catch {
      return null;
    }
  }, [context]);

  // autoGenerate: contextKey *값 변경* 시만 자동 재호출 (object reference 변경은 무시).
  // 사용자 신고: 의원/기사 변경 후 insight가 옛 데이터 유지 → context key 변경 시 reset+fetch.
  // Note: `loading` guard는 의도적으로 deps에 없음 — contextKey가 바뀌면 새 요청이고,
  //  기존 fetch는 stale이라서 새로 fetch해야 함. (이전 stale closure bug로 nested fetch가 dropping되던 이슈 회피.)
  React.useEffect(() => {
    if (!autoGenerate || !contextKey) return;
    setInsight(null);
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoGenerate, contextKey]);

  return (
    <section className="mt-6 bg-slate-900/40 border border-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
            <span>{title}</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/15 border border-blue-500/30 text-blue-300">
              Sonnet 4.6
            </span>
          </h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            시나리오 {scenarioCode} · 페르소나별 어조·관심사 + 정치 중립성 가드 자동 적용
          </p>
        </div>
        {!autoGenerate && (
          <button
            onClick={generate}
            disabled={loading || !context}
            className="text-xs px-3 py-1.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20 disabled:opacity-40"
          >
            {loading ? '분석 중…' : insight ? '재분석' : '인사이트 생성'}
          </button>
        )}
      </div>

      {error && (
        <div className="p-2 bg-red-900/30 border border-red-700/50 text-red-300 rounded text-xs mb-2">
          {error}
        </div>
      )}

      {loading && !insight && (
        <div className="text-center py-6 text-slate-400 text-sm animate-pulse">
          페르소나 적용 + Sonnet 4.6 분석 중...
        </div>
      )}

      {insight && (
        <article>
          <div className="flex items-center gap-2 mb-3 text-[10px] uppercase tracking-wider">
            <span className="text-slate-500">audience</span>
            <span className="text-amber-300">{insight.tier_group_kr}</span>
            <span className="text-slate-500 ml-auto">balance</span>
            <span className={insight.alarm ? 'text-amber-400' : 'text-emerald-400'}>
              {insight.political_balance_score.toFixed(2)}
            </span>
            {insight.alarm && <span className="text-amber-400">⚠</span>}
            <button
              type="button"
              onClick={() => downloadMarkdown(insight, scenarioCode)}
              className="ml-2 px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 hover:border-amber-500/50 normal-case"
              title="Markdown으로 저장"
            >MD</button>
            <button
              type="button"
              onClick={() => printPdf(insight, scenarioCode)}
              className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 hover:border-amber-500/50 normal-case"
              title="브라우저 PDF 인쇄"
            >PDF</button>
          </div>
          <div className="chat-markdown text-sm text-slate-200 leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{insight.text}</ReactMarkdown>
          </div>
        </article>
      )}

      {!insight && !loading && !context && (
        <div className="text-center py-4 text-slate-500 text-xs italic">
          시나리오 결과가 로드된 후 인사이트 생성이 가능합니다.
        </div>
      )}
    </section>
  );
}


function downloadMarkdown(insight: InsightResponse, scenarioCode: string) {
  const ts = new Date().toISOString().slice(0, 19).replace('T', ' ');
  const md = [
    `# AI 인사이트 — 시나리오 ${scenarioCode} (${insight.scenario_label})`,
    ``,
    `> 생성: ${ts} · 페르소나: ${insight.persona_id} (${insight.tier_group_kr}) · 모델: ${insight.model_id}`,
    `> political_balance_score: ${insight.political_balance_score.toFixed(2)}${insight.alarm ? ' ⚠' : ''}`,
    ``,
    insight.text,
  ].join('\n');
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `insight-${scenarioCode}-${insight.persona_id}-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}


function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function printPdf(insight: InsightResponse, scenarioCode: string) {
  const ts = new Date().toLocaleString('ko-KR');
  // 1. HTML escape (XSS 방지) → 2. 안전한 markdown 패턴 변환
  const html = escapeHtml(insight.text)
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^\s*\n/gm, '');
  const doc = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>AI 인사이트 - 시나리오 ${scenarioCode}</title>
<style>
  body { font-family: -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; max-width: 720px; margin: 32px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.6; }
  h1 { color: #0f172a; border-bottom: 2px solid #1e293b; padding-bottom: 8px; }
  h2 { color: #1e293b; margin-top: 24px; }
  .meta { color: #666; font-size: 11px; margin-bottom: 24px; padding: 8px 12px; background: #f5f5f5; border-radius: 4px; }
  li { margin: 4px 0; }
  strong { color: #0f172a; }
  p { margin: 0.8rem 0; }
</style></head>
<body>
<h1>AI 인사이트 — 시나리오 ${scenarioCode} (${insight.scenario_label})</h1>
<div class="meta">
  생성: ${ts}<br>
  페르소나: <strong>${insight.persona_id}</strong> (${insight.tier_group_kr}) · 모델: ${insight.model_id}<br>
  political_balance_score: <strong>${insight.political_balance_score.toFixed(2)}</strong>${insight.alarm ? ' ⚠' : ''}
</div>
<p>${html}</p>
</body></html>`;
  // Blob URL 사용 - document.write 회피 (XSS 안전)
  const blob = new Blob([doc], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const w = window.open(url, '_blank');
  if (!w) { alert('PDF 출력을 위해 popup을 허용하세요.'); URL.revokeObjectURL(url); return; }
  // popup 로드 후 print dialog
  setTimeout(() => { try { w.print(); } catch { /* ignore */ } }, 500);
  // 메모리 정리 - 5분 후 blob URL revoke
  setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000);
}
