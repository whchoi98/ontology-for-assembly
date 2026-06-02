'use client';

/**
 * ChatThread — 메시지 list. 각 message bubble은 별도 memoized 컴포넌트.
 *
 * 깜빡임 방지 전략:
 * - MessageBubble을 React.memo로 wrap
 * - 비교 함수에서 *text · toolLogs* 변경만 re-render trigger
 * - prev message reference 동일 시 skip → 마지막 streaming 메시지만 re-paint
 */
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface ChatMsg {
  role: 'user' | 'assistant';
  text: string;
  toolLogs?: { tool: string; input?: unknown }[];
}


export const ChatThread = React.memo(function ChatThread({
  messages,
  streaming = false,
  assistantName = '데스크',
}: {
  messages: ChatMsg[];
  streaming?: boolean;
  assistantName?: string;
}) {
  return (
    <div className="space-y-4 pr-2">
      {messages.length === 0 && (
        <div className="text-xs text-slate-500 italic px-3 py-8 text-center border border-dashed border-slate-700 rounded-lg">
          질문을 입력하거나 위 추천을 클릭하면 대화가 여기에 표시됩니다.
        </div>
      )}
      {messages.map((m, i) => (
        <MessageBubble
          key={i}
          msg={m}
          isLast={i === messages.length - 1}
          streaming={streaming}
          assistantName={assistantName}
        />
      ))}
    </div>
  );
});


/**
 * 개별 메시지 bubble — memo 비교가 *text + toolLogs + isLast + streaming*만 검사.
 * 마지막 메시지가 아니면 *영구 같은 reference* → re-render skip.
 */
const MessageBubble = React.memo(function MessageBubble({
  msg, isLast, streaming, assistantName,
}: {
  msg: ChatMsg;
  isLast: boolean;
  streaming: boolean;
  assistantName: string;
}) {
  return (
    <div
      className={
        'p-3 rounded-lg border ' +
        (msg.role === 'user'
          ? 'bg-blue-500/10 border-blue-500/30 ml-12'
          : 'bg-slate-900/60 border-slate-700 mr-12')
      }
    >
      <div className="text-[10px] uppercase tracking-wider mb-1.5 text-slate-400">
        {msg.role === 'user' ? '사용자' : assistantName}
      </div>
      {msg.role === 'user' ? (
        <p className="text-sm whitespace-pre-wrap leading-relaxed text-slate-100">{msg.text}</p>
      ) : (
        <div className="chat-markdown text-sm text-slate-100 leading-relaxed">
          {msg.text ? (
            <>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
              {streaming && isLast && (
                <span className="inline-block w-1.5 h-3.5 bg-blue-400 ml-0.5 align-middle animate-pulse"></span>
              )}
            </>
          ) : streaming && isLast ? (
            <span className="italic text-slate-500">응답 생성 중...</span>
          ) : (
            <span className="italic text-slate-500">…</span>
          )}
        </div>
      )}
      {/* toolLogs는 ChatThread 외부의 ToolCallPanel 또는 progress 박스에서 표시 */}
      {/* (메시지 박스 안에 두면 매 chunk마다 같은 박스 update → 리프레시 보임) */}
    </div>
  );
}, (prev, next) => {
  // 가장 강력한 memo 비교 — text 변경 시만 re-render (toolLogs는 박스 외부 처리)
  // 이전 메시지 (isLast=false)는 절대 re-paint 안 함 → 깜빡임 0
  if (prev.msg !== next.msg) {
    if (prev.isLast !== next.isLast) return false;
    if (prev.isLast && prev.msg.text !== next.msg.text) return false;
  }
  if (prev.isLast && (prev.streaming !== next.streaming)) return false;
  return true;
});
