'use client';

/**
 * /chat — 데스크 챗봇 (gcc Cally 패턴 차용, 언론·미디어 어조).
 *
 * - 단일 대화 thread (user/assistant 교대)
 * - 페르소나별 system prompt + 응답 헤더 (`**[tier_group_kr — name_kr]**`)
 * - SSE token streaming (CloudFront idle timeout reset)
 * - 우측 도구 호출 trace panel
 * - 페르소나별 추천 질문 (25-30개)
 * - 3-stage 비교 보고 싶으면 /chat/compare로 이동
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ChatThread, type ChatMsg } from '../../components/ChatThread';
import { ToolCallPanel, type ToolCall } from '../../components/ToolCallPanel';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { chatStream } from '../../lib/api-client';
import { PERSONAS, type PersonaId } from '../../lib/personas';
import { getScenario } from '../../lib/scenario-meta';


const ASSISTANT_NAME = '데스크';
const ASSISTANT_TAGLINE = '편집 데스크 + Sonnet 4.6 + 정치 중립성 가드';


// 페르소나별 추천 질문 — gcc 패턴 30 questions
// 페르소나별 후속 질문 (응답 후 자동 표시 - gcc followups 패턴).
// 각 chip에 *명시적 topic keyword* 포함 — fctx prepend 회피, 새 topic 매칭 가능.
// 사용자 신고: 추가 질문이 계속 AI 답변 → topic을 다양화 + 명시.
const FOLLOWUPS: Record<PersonaId, string[]> = {
  editorial:       ['청년 주거 입법 트렌드 분석', '환경·기후 양당 협력 사례', '복지 카테고리 통과율'],
  data_ai:         ['주거 입법 sample expansion 가설', '환경 표결 일치율 95% CI', '복지 cluster modularity 변화'],
  ad_sales:        ['청년 주거 광고 매칭 score', '환경 콘텐츠 CTR 시뮬레이션', '경제 카테고리 광고 적합도'],
  general_reader:  ['내 지역구 의원 활동은?', '청년 주거 법안 어떤게 있나요?', '환경 정책 양당 협력 사례'],
  paid_subscriber: ['주거 입법 시계열 분기별', '환경 의원 비교 분석', '복지 입법 PDF 리포트'],
  b2b:             ['주거 산업 impact_score', '환경 산업 영향 cross-tab', '경제 KOSIS 통계 연결'],
};

const SAMPLES: Array<{ persona: PersonaId; label: string }> = [
  // 편집국 (편집·취재)
  { persona: 'editorial',       label: 'AI 관련 의안 발의 상위 5명 + 공동발의 네트워크 요약' },
  { persona: 'editorial',       label: '청년 주거지원 법안 발의 추이와 핵심 발의자' },
  { persona: 'editorial',       label: '환경·기후 의안 중 양당 협력 사례 발굴' },
  { persona: 'editorial',       label: '국방 위원회 최근 1년 발의 의안 카테고리 분포' },
  { persona: 'editorial',       label: '재선 이상 의원의 발의·표결 패턴 비교' },
  // 데이터·AI
  { persona: 'data_ai',         label: '의안 카테고리 엔트로피 + 정당별 비교 (sample size 명시)' },
  { persona: 'data_ai',         label: '표결 일치율 95% CI 추정 + 시계열 변화' },
  { persona: 'data_ai',         label: '의원 클러스터 KMeans 5 cluster + feature importance' },
  { persona: 'data_ai',         label: '의안 통과 가능성 logistic regression coefficient' },
  { persona: 'data_ai',         label: '본회의·상임위 출석률 분포의 분산 분석' },
  // 광고·세일즈
  { persona: 'ad_sales',        label: 'AI 입법 콘텐츠의 광고 매칭 score (keyword/embedding/agent)' },
  { persona: 'ad_sales',        label: '광고주 평판 보호 trade-off 분석 (정치 민감 토픽)' },
  { persona: 'ad_sales',        label: '시나리오 G ROI 시뮬레이션 → 카테고리별 추천 광고 인벤토리' },
  { persona: 'ad_sales',        label: 'AdMatchDecision trace에서 거절 사유 패턴' },
  // 일반 독자
  { persona: 'general_reader',  label: '내 지역구 의원이 어떤 활동을 했는지' },
  { persona: 'general_reader',  label: 'AI 관련 법안이 통과되면 내 생활에 어떻게 영향을 줄까요?' },
  { persona: 'general_reader',  label: '본회의 출석률이 높은 의원 top 5' },
  { persona: 'general_reader',  label: '청년 정책 법안 어떤 것이 발의되었나요?' },
  { persona: 'general_reader',  label: '환경 법안이 정파를 가리지 않고 협력하나요?' },
  // 유료 구독자
  { persona: 'paid_subscriber', label: '22대 국회 1분기 AI 입법 심층 분석 + PDF 리포트용 정리' },
  { persona: 'paid_subscriber', label: '핵심 의원 3명의 발의·표결·발언 통합 timeline' },
  { persona: 'paid_subscriber', label: '의안 카테고리별 통과율 + 외부 신호 cross-source 패턴' },
  { persona: 'paid_subscriber', label: '지역구 분포 × 발의 토픽 카테고리 cross-tab' },
  { persona: 'paid_subscriber', label: '협력 클러스터의 종방향 변화 (분기별)' },
  // B2B
  { persona: 'b2b',             label: 'AI 산업 영향 법안 JSON (headline·impact_score·timeline)' },
  { persona: 'b2b',             label: '재생에너지 정책 변화 영향 — impact_score + 통과 가능성' },
  { persona: 'b2b',             label: '데이터 거버넌스 관련 법안 모니터링 (sources 포함)' },
  { persona: 'b2b',             label: '특정 산업 위원회의 입법 활동 인덱스 (raw values)' },
  { persona: 'b2b',             label: '청년 주거 관련 법안 + 관련 KOSIS 통계 후보' },
];


export default function ChatPage() {
  const [persona, setPersona] = useState<PersonaId>('editorial');
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [tools, setTools] = useState<ToolCall[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // gcc 패턴: phase ordered list (chip 누적). 3 stage status chip 대체.
  const [phases, setPhases] = useState<{ name: string; detail?: string }[]>([]);
  const [followups, setFollowups] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 페르소나 로드 + 변경 시 대화 초기화
  useEffect(() => {
    setPersona(readPersonaIdSync());
  }, []);

  // autoscroll: 메시지 *개수* 변경(user/assistant 새 turn) 시만 — delta chunk마다 X
  // smooth → 'auto' (smooth가 매 chunk마다 animation 발생, 깜빡임 보임)
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'auto' });
  }, [messages.length]);

  const samplesForPersona = SAMPLES.filter((s) => s.persona === persona);

  async function send(query: string) {
    if (!query.trim() || streaming) return;
    setError(null);
    setStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: query },
      { role: 'assistant', text: '' },
    ]);
    setDraft('');
    setFollowups([]);
    setPhases([]);

    let assistantText = '';
    const toolLogs: { tool: string; input?: unknown }[] = [];

    try {
      // gcc 패턴: agentic 단일 mode + phase ordered list (3 stage status chip 대체)
      await chatStream(query, {
        onEvent: (e) => {
          if (e.type === 'phase') {
            // phase event를 ordered list에 누적 (gcc 패턴)
            setPhases((p) => [...p, { name: e.data.stage ?? 'phase' }]);
          } else if (e.type === 'log') {
            const label = e.data.tool_called || e.data.agent_invoked || 'unknown';
            toolLogs.push({ tool: label });
            setTools((prev) => [...prev, { tool_call: label }]);
            setPhases((p) => [...p, { name: `tool:${label}` }]);
          } else if (e.type === 'delta' && e.data.stage === 'agentic') {
            assistantText += e.data.text;
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last.role === 'assistant') {
                copy[copy.length - 1] = { ...last, text: assistantText };
              }
              return copy;
            });
          } else if (e.type === 'result' && e.data.stage === 'agentic') {
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last.role === 'assistant') {
                copy[copy.length - 1] = { ...last, toolLogs };
              }
              return copy;
            });
            setFollowups(buildFollowups(persona));
          } else if (e.type === 'error') {
            setError(e.data.message);
          }
        },
        onError: (err) => setError(err.message),
      }, { personaId: persona, mode: 'agentic' });
    } catch (e) {
      setError(String(e));
    } finally {
      setStreaming(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    void send(draft);
  }

  function buildFollowups(pid: PersonaId): string[] {
    return FOLLOWUPS[pid] ?? FOLLOWUPS.editorial;
  }

  function escapeHtml(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function buildMarkdown(): string {
    const personaDef = PERSONAS.find((p) => p.id === persona);
    const ts = new Date().toISOString().slice(0, 19).replace('T', ' ');
    return [
      `# ${ASSISTANT_NAME} 분석 — ${personaDef?.nameKr ?? persona}`,
      ``,
      `> 생성: ${ts} · 페르소나: ${personaDef?.nameKr ?? persona} (${persona}) · 모델: Sonnet 4.6`,
      ``,
      ...messages.flatMap((m) => [
        `## ${m.role === 'user' ? '질문' : ASSISTANT_NAME}`,
        ``, m.text, ``,
      ]),
    ].join('\n');
  }

  function downloadMarkdown() {
    if (messages.length === 0) return;
    const md = buildMarkdown();
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `desk-${persona}-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function printPdf() {
    if (messages.length === 0) return;
    const personaDef = PERSONAS.find((p) => p.id === persona);
    const ts = new Date().toLocaleString('ko-KR');
    const body = messages.map((m) => {
      const role = m.role === 'user' ? '질문' : ASSISTANT_NAME;
      // 1. HTML escape (XSS 방지) — <script>, event handler 등 무효화
      // 2. 안전한 markdown 패턴 → HTML (escaped 입력에 추가 변환, injection 없음)
      const safe = escapeHtml(m.text);
      const html = safe
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\n\n/g, '</p><p>');
      return `<section class="${m.role}"><h4>${role}</h4><p>${html}</p></section>`;
    }).join('\n');
    const doc = `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>${ASSISTANT_NAME} 분석 - ${personaDef?.nameKr ?? persona}</title>
<style>
  body { font-family: -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; max-width: 720px; margin: 32px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.6; }
  h1 { color: #0f172a; border-bottom: 2px solid #1e293b; padding-bottom: 8px; }
  h3 { color: #1e293b; margin-top: 20px; }
  section { margin: 20px 0; padding: 12px 16px; border-radius: 6px; }
  section.user { background: #eff6ff; border-left: 3px solid #3b82f6; }
  section.assistant { background: #fafafa; border-left: 3px solid #1e293b; }
  h4 { margin: 0 0 6px; font-size: 11px; text-transform: uppercase; color: #666; }
  li { margin: 4px 0; }
</style></head><body>
<h1>${ASSISTANT_NAME} 분석 — ${personaDef?.nameKr ?? persona}</h1>
<div style="color:#666;font-size:11px;margin-bottom:24px;">
  생성: ${ts} · 페르소나: <strong>${personaDef?.nameKr ?? persona}</strong> (${persona}) · 모델: Sonnet 4.6
</div>
${body}
</body></html>`;
    const blob = new Blob([doc], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const w = window.open(url, '_blank');
    if (!w) { alert('PDF 출력을 위해 popup을 허용하세요.'); URL.revokeObjectURL(url); return; }
    setTimeout(() => { try { w.print(); } catch { /* ignore */ } }, 500);
    setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000);
  }

  return (
    <div>
      {/* gcc Cally 스타일 헤더 */}
      <header className="mb-4">
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-2xl font-bold text-white tracking-tight">{ASSISTANT_NAME}</h1>
          <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-500/15 border border-blue-500/30 text-blue-300">
            Assembly Insight AI
          </span>
        </div>
        <div className="text-xs text-slate-400">
          <span className="text-amber-300 font-medium">
            {PERSONAS.find((p) => p.id === persona)?.nameKr ?? persona}
          </span>
          {' '}어조 · 10 도구 · Sonnet 4.6 · 정치 중립성 가드
        </div>
      </header>

      {/* gcc Cally 스타일: 페르소나 선택 row */}
      <section className="mb-4 bg-slate-900/40 border border-slate-800 rounded-lg p-3">
        <div className="text-xs text-slate-300 mb-2">어떤 페르소나 시점으로 보시겠어요?</div>
        <div className="flex flex-wrap gap-1.5">
          {PERSONAS.map((p) => {
            const isActive = p.id === persona;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  // PersonaSwitch와 동기 — localStorage + URL query reload
                  window.localStorage.setItem('persona_id', p.id);
                  window.location.replace(`/chat?p=${encodeURIComponent(p.id)}`);
                }}
                className={
                  'text-xs px-3 py-1.5 rounded-full border transition-colors ' +
                  (isActive
                    ? 'bg-blue-500/20 border-blue-500/50 text-blue-200 font-medium'
                    : 'bg-slate-800/60 border-slate-700 text-slate-300 hover:bg-slate-700/60')
                }
              >
                {p.nameKr}
              </button>
            );
          })}
        </div>
      </section>

      {/* gcc Cally 스타일 환영 메시지 (대화 시작 전만) */}
      {messages.length === 0 && (
        <section className="mb-4 bg-gradient-to-br from-slate-900/60 to-slate-900/30 border border-slate-800 rounded-lg p-4">
          <h2 className="text-base font-bold text-white mb-1">
            안녕하세요, {ASSISTANT_NAME}예요 ⚡
          </h2>
          <p className="text-xs text-slate-300 mb-3 leading-relaxed">
            22대 국회 온톨로지에 대해 자연어로 물어보세요. <strong className="text-slate-100">286 의원</strong> · {' '}
            <strong className="text-slate-100">10건 의안</strong> · 표결·발언·기사 데이터를 {' '}
            <span className="text-amber-300 font-medium">
              {PERSONAS.find((p) => p.id === persona)?.nameKr ?? persona}
            </span>{' '}
            시점으로 분석해 드립니다.
          </p>
          <div className="text-[10px] uppercase tracking-wider text-amber-400 mb-2 flex items-center gap-1.5">
            <span className="inline-block w-1 h-1 rounded-full bg-amber-400" />
            💡 {PERSONAS.find((p) => p.id === persona)?.nameKr} 추천 질문 ({Math.min(samplesForPersona.length, 5)}개)
          </div>
          <div className="flex flex-col gap-1.5">
            {samplesForPersona.slice(0, 5).map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => void send(s.label)}
                disabled={streaming}
                className="text-left text-xs px-3 py-2 rounded bg-slate-800/80 hover:bg-blue-500/15 hover:border-blue-500/40 border border-slate-700 text-slate-200 disabled:opacity-40 transition-colors"
              >
                {s.label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-[10px] text-slate-500">
            페르소나를 바꾸면 {ASSISTANT_NAME}의 어조와 KPI 우선순위, 추천 질문이 함께 바뀝니다.
          </p>
        </section>
      )}

      {/* 대화 시작 후 추천 질문 (compact) */}
      {messages.length > 0 && (
        <div className="mb-4">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
            💡 추천 질문 — {PERSONAS.find((p) => p.id === persona)?.nameKr ?? persona}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {samplesForPersona.slice(0, 5).map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => void send(s.label)}
                disabled={streaming}
                className="text-[11px] px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40"
              >
                {s.label.length > 30 ? s.label.slice(0, 30) + '…' : s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ━━━ gcc 패턴: phase ordered list (chip 누적, 답변 박스와 시각 분리) ━━━ */}
      {(streaming || phases.length > 0) && (
        <div className="mb-3 px-3 py-2 bg-slate-900/40 border border-slate-700 rounded-lg">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-2">
            <span className={`inline-block w-1.5 h-1.5 rounded-full bg-amber-400 ${streaming ? 'animate-pulse' : ''}`} />
            에이전트 진행 — {phases.length}단계
          </div>
          <ol className="flex flex-wrap items-center gap-1.5">
            {phases.map((p, i) => (
              <li
                key={i}
                className={
                  'flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded border ' + (
                    p.name.startsWith('tool:')
                      ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                      : 'bg-blue-500/15 border-blue-500/40 text-blue-200'
                  )
                }
              >
                <span className="text-[9px] opacity-60">{i + 1}.</span>
                <span className="font-semibold">{p.name.replace('tool:', '🔧 ')}</span>
                {p.detail && <span className="opacity-70">— {p.detail}</span>}
              </li>
            ))}
            {streaming && (
              <li className="text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700 bg-slate-800/50 text-slate-400 animate-pulse">
                다음 단계…
              </li>
            )}
          </ol>
        </div>
      )}

      {/* ━━━ 답변 영역 ━━━ */}
      <div className="text-[9px] uppercase tracking-widest text-slate-500 mb-1.5 mt-3">
        답변 · 데스크 응답
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-5">
        {/* Thread + input */}
        <div>
          <div ref={scrollRef} className="max-h-[60vh] overflow-y-auto mb-4 pr-1">
            <ChatThread messages={messages} streaming={streaming} assistantName={ASSISTANT_NAME} />
          </div>

          {error && (
            <div className="mb-3 p-2 bg-red-900/30 border border-red-700/50 text-red-300 rounded text-xs">
              {error}
            </div>
          )}

          <form onSubmit={onSubmit} className="flex gap-2">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={`${ASSISTANT_NAME}에게 질문하세요...`}
              disabled={streaming}
              className="flex-1 px-3 py-2 bg-slate-900 border border-slate-700 rounded-md text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={streaming || !draft.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-md disabled:opacity-40"
            >
              {streaming ? '…' : '전송'}
            </button>
            {messages.length > 0 && !streaming && (
              <>
                <button
                  type="button"
                  onClick={downloadMarkdown}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs rounded-md"
                  title="대화를 Markdown으로 저장"
                >MD</button>
                <button
                  type="button"
                  onClick={printPdf}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs rounded-md"
                  title="브라우저 PDF 인쇄"
                >PDF</button>
              </>
            )}
          </form>

          {/* 후속 질문 (응답 끝나면 표시) */}
          {followups.length > 0 && !streaming && (
            <div className="mt-3 pt-3 border-t border-slate-800">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">💡 후속 질문</div>
              <div className="flex flex-wrap gap-1.5">
                {followups.map((f) => {
                  // chip에 *명시적 topic keyword* 포함되면 fctx skip — 새 topic 매칭 우선.
                  // 추상 chip만 fctx 적용 (직전 topic 유지). 사용자 신고: 모든 추가 질문 AI →
                  // chip 자체가 topic explicit이라 prepend 불필요.
                  const TOPIC_RE = /AI|인공지능|주거|환경|기후|복지|보건|교육|경제|재정|개인정보|GDPR|외교|안보|지역구|위원회|표결|이상치/;
                  const explicit = TOPIC_RE.test(f);
                  return (
                    <button
                      key={f}
                      type="button"
                      onClick={() => {
                        if (explicit) {
                          void send(f);
                        } else {
                          const lastUser = [...messages].reverse().find((m) => m.role === 'user')?.text ?? '';
                          void send(lastUser ? `${lastUser} — ${f}` : f);
                        }
                      }}
                      className="text-[11px] px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-700 border border-slate-700 hover:border-amber-500/50 text-slate-200"
                    >{f}</button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Tool call panel */}
        <ToolCallPanel calls={tools} />
      </div>
    </div>
  );
}
