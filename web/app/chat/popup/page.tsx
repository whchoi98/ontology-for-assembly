'use client';

/**
 * Floating chat popup — gcc Cally 패턴 단일 대화 thread.
 *
 * Sidebar·TopBar 없는 standalone window. 헤더·페르소나 row·환영 카드·추천 질문은
 * 메인 /chat 페이지와 동일하지만 *축소 layout*. mode=agentic 단일 stream.
 *
 * 사용자 신고: floating chat이 *예전 3-stage 구조* — gcc Cally처럼 단일 thread로.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { chatStream } from '../../../lib/api-client';
import { PERSONAS, type PersonaId } from '../../../lib/personas';


const ASSISTANT_NAME = '데스크';

// 페르소나별 추천 질문 5개씩
const SAMPLES: Record<PersonaId, string[]> = {
  editorial: [
    'AI 관련 의안 발의 상위 5명 + 공동발의 네트워크',
    '청년 주거지원 법안 발의 추이와 핵심 발의자',
    '환경·기후 의안 중 양당 협력 사례',
    '재선 이상 의원의 발의·표결 패턴 비교',
    '국방 위원회 최근 1년 발의 의안 카테고리',
  ],
  data_ai: [
    '의안 카테고리 엔트로피 + 정당별 비교',
    '표결 일치율 95% CI 추정 + 시계열 변화',
    '의원 클러스터 KMeans + feature importance',
    '의안 통과 가능성 logistic regression',
    '본회의·상임위 출석률 분포 분산 분석',
  ],
  ad_sales: [
    'AI 입법 콘텐츠 광고 매칭 score',
    '광고주 평판 보호 trade-off 분석',
    '시나리오 G ROI 시뮬레이션',
    'AdMatchDecision trace 거절 사유',
    '카테고리별 광고 적합도 분석',
  ],
  general_reader: [
    '내 지역구 의원이 어떤 활동을 했는지',
    'AI 법안이 통과되면 생활에 영향은?',
    '본회의 출석률 높은 의원 top 5',
    '청년 정책 법안 어떤 것이 발의되었나요?',
    '환경 법안 양당 협력 사례는?',
  ],
  paid_subscriber: [
    '22대 임기 AI 입법 심층 분석 PDF',
    '핵심 의원 3명 발의·표결·발언 timeline',
    '카테고리별 통과율 + 외부 신호 cross',
    '지역구 × 발의 토픽 cross-tab',
    '협력 클러스터 분기별 변화',
  ],
  b2b: [
    'AI 산업 영향 법안 JSON',
    '재생에너지 정책 영향 + 통과 가능성',
    '데이터 거버넌스 법안 모니터링',
    '특정 산업 위원회 입법 활동 인덱스',
    '청년 주거 법안 + KOSIS 통계',
  ],
};


interface ChatMsg {
  role: 'user' | 'assistant';
  text: string;
}

// 페르소나별 후속 질문 (응답 후 자동 표시 — explicit topic 포함)
const FOLLOWUPS: Record<PersonaId, string[]> = {
  editorial: [
    '청년 주거 입법 트렌드',
    '환경·기후 양당 협력 사례',
    '복지 카테고리 통과율',
    '교육 정책 cross-tab',
    '외교·안보 표결 분석',
  ],
  data_ai: [
    '주거 sample expansion 가설',
    '환경 표결 일치율 95% CI',
    '복지 cluster modularity',
    '교육 cohort variance',
    '경제 logistic regression',
  ],
  ad_sales: [
    '주거 광고 매칭 score',
    '환경 콘텐츠 CTR 시뮬',
    '경제 광고 적합도',
    '복지 premium CPM 분석',
    '교육 학부모 타겟팅',
  ],
  general_reader: [
    '내 지역구 의원 활동',
    '청년 주거 법안',
    '환경 양당 협력',
    '복지 노인 정책',
    '교육 정책 알기',
  ],
  paid_subscriber: [
    '주거 시계열 PDF',
    '환경 의원 비교',
    '복지 lifecycle',
    '교육 trend 분석',
    '경제 카테고리 cross-tab',
  ],
  b2b: [
    '주거 impact_score',
    '환경 산업 영향',
    '경제 KOSIS 연결',
    '복지 보험 산업',
    '개인정보 GDPR 비교',
  ],
};


export default function ChatPopupPage() {
  const [persona, setPersona] = useState<PersonaId>('editorial');
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [phases, setPhases] = useState<{ name: string }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // URL query parameter persona
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const p = params.get('persona') as PersonaId | null;
    if (p && PERSONAS.some((x) => x.id === p)) setPersona(p);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'auto' });
  }, [messages.length]);

  const send = useCallback(async (q: string) => {
    if (!q.trim() || streaming) return;
    setStreaming(true);
    setPhases([]);
    setMessages((prev) => [...prev, { role: 'user', text: q }, { role: 'assistant', text: '' }]);
    setDraft('');

    let assistantText = '';
    try {
      await chatStream(q, {
        onEvent: (e) => {
          if (e.type === 'phase') {
            setPhases((p) => [...p, { name: e.data.stage ?? 'phase' }]);
          } else if (e.type === 'log') {
            const label = e.data.tool_called || e.data.agent_invoked || 'unknown';
            setPhases((p) => [...p, { name: `tool:${label}` }]);
          } else if (e.type === 'delta' && e.data.stage === 'agentic') {
            assistantText += e.data.text;
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last.role === 'assistant') copy[copy.length - 1] = { ...last, text: assistantText };
              return copy;
            });
          }
        },
      }, {
        personaId: persona,
        mode: 'agentic',
      });
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', text: `에러: ${String(err)}` }]);
    } finally {
      setStreaming(false);
    }
  }, [persona, streaming]);

  const samples = SAMPLES[persona] ?? SAMPLES.editorial;
  const personaName = PERSONAS.find((p) => p.id === persona)?.nameKr ?? persona;

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100">
      {/* gcc Cally 패턴 헤더 (compact) */}
      <header className="px-3 py-2 border-b border-slate-800 flex-shrink-0">
        <div className="flex items-baseline gap-2 mb-0.5">
          <h1 className="text-base font-bold text-white">{ASSISTANT_NAME}</h1>
          <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-500/15 border border-blue-500/30 text-blue-300">
            Assembly Insight AI
          </span>
          <button
            type="button"
            onClick={() => {
              if (streaming) return;
              setMessages([]);
              setPhases([]);
              setDraft('');
            }}
            disabled={streaming}
            title="새 대화 시작"
            className="ml-auto text-[10px] px-2 py-0.5 rounded border border-slate-700 bg-slate-800/60 hover:bg-blue-500/15 hover:border-blue-500/40 text-slate-300 disabled:opacity-40"
          >
            ↻ 새로고침
          </button>
        </div>
        <div className="text-[10px] text-slate-400">
          <span className="text-amber-300 font-medium">{personaName}</span> 어조 · Sonnet 4.6 · 정치 중립성 가드
        </div>

        {/* 페르소나 선택 row */}
        <div className="mt-2 flex flex-wrap gap-1">
          {PERSONAS.map((p) => {
            const isActive = p.id === persona;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setPersona(p.id)}
                disabled={streaming}
                className={
                  'text-[10px] px-2 py-0.5 rounded-full border transition-colors ' +
                  (isActive
                    ? 'bg-blue-500/20 border-blue-500/50 text-blue-200 font-medium'
                    : 'bg-slate-800/60 border-slate-700 text-slate-300 hover:bg-slate-700/60 disabled:opacity-40')
                }
              >
                {p.nameKr}
              </button>
            );
          })}
        </div>
      </header>

      {/* 환영 카드 + 추천 질문 (대화 시작 전) */}
      {messages.length === 0 && (
        <div className="px-3 py-3 border-b border-slate-800">
          <h2 className="text-sm font-bold text-white mb-1">
            안녕하세요, {ASSISTANT_NAME}예요 ⚡
          </h2>
          <p className="text-[11px] text-slate-300 mb-2 leading-relaxed">
            22대 국회 온톨로지를 <span className="text-amber-300 font-medium">{personaName}</span> 시점으로 분석해 드립니다.
          </p>
          <div className="text-[9px] uppercase tracking-wider text-amber-400 mb-1.5">
            💡 추천 질문 ({samples.length}개)
          </div>
          <div className="flex flex-col gap-1">
            {samples.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void send(s)}
                disabled={streaming}
                className="text-left text-[11px] px-2 py-1.5 rounded bg-slate-800/80 hover:bg-blue-500/15 hover:border-blue-500/40 border border-slate-700 text-slate-200 disabled:opacity-40 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[9px] text-slate-500">
            페르소나를 바꾸면 {ASSISTANT_NAME}의 어조와 추천 질문이 함께 바뀝니다.
          </p>
        </div>
      )}

      {/* 채팅 thread */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              'mb-2 px-3 py-2 rounded-lg text-[11px] leading-relaxed ' +
              (m.role === 'user'
                ? 'bg-blue-500/15 border border-blue-500/40 text-slate-100 ml-6'
                : 'bg-slate-900/60 border border-slate-800 text-slate-200 mr-6')
            }
          >
            {m.role === 'assistant' ? (
              <div className="chat-markdown prose-invert">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text || '…'}</ReactMarkdown>
              </div>
            ) : (
              <div className="whitespace-pre-wrap">{m.text}</div>
            )}
          </div>
        ))}
      </div>

      {/* 후속 질문 chip — 대화 시작 후 + streaming 없을 때 (사용자 신고: popup에도 followup) */}
      {messages.length > 0 && !streaming && (
        <div className="px-3 py-1.5 border-t border-slate-800 bg-slate-900/30">
          <div className="text-[9px] uppercase tracking-wider text-amber-400 mb-1">💡 후속 질문</div>
          <div className="flex flex-wrap gap-1">
            {(FOLLOWUPS[persona] ?? FOLLOWUPS.editorial).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => void send(f)}
                className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800/60 hover:bg-blue-500/15 hover:border-blue-500/40 border border-slate-700 text-slate-200"
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 에이전트 진행 (gcc 패턴 phase ordered list) */}
      {(streaming || phases.length > 0) && (
        <div className="px-3 py-1.5 border-t border-slate-800 bg-slate-900/40">
          <div className="text-[9px] uppercase tracking-wider text-slate-500 mb-1 flex items-center gap-1.5">
            <span className={`inline-block w-1 h-1 rounded-full bg-amber-400 ${streaming ? 'animate-pulse' : ''}`} />
            에이전트 진행 — {phases.length}단계
          </div>
          <div className="flex flex-wrap gap-1">
            {phases.map((p, i) => (
              <span
                key={i}
                className={
                  'text-[9px] font-mono px-1.5 py-0.5 rounded border ' +
                  (p.name.startsWith('tool:')
                    ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                    : 'bg-blue-500/15 border-blue-500/40 text-blue-200')
                }
              >
                {p.name.replace('tool:', '🔧 ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 입력창 */}
      <form
        onSubmit={(e) => { e.preventDefault(); void send(draft); }}
        className="px-3 py-2 border-t border-slate-800 flex gap-2 flex-shrink-0"
      >
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`${ASSISTANT_NAME}에게 질문하세요...`}
          disabled={streaming}
          className="flex-1 px-2 py-1.5 text-xs bg-slate-900 border border-slate-700 rounded text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          disabled={streaming || !draft.trim()}
          className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white font-medium rounded disabled:opacity-40"
        >
          {streaming ? '...' : '전송'}
        </button>
      </form>
    </div>
  );
}
