/**
 * FastAPI 백엔드 호출 클라이언트 (Server Component / Client 양용).
 *
 * 환경 변수:
 * - NEXT_PUBLIC_API_BASE_URL: 클라이언트 측 (browser)
 * - INTERNAL_API_BASE_URL: 서버 측 (Server Component) - VPC 내부 ALB 호출
 *
 * 모든 호출에 `X-Persona-Id` 자동 첨부.
 */

import type { PersonaId } from './personas';

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8080';
const SERVER_BASE = process.env.INTERNAL_API_BASE_URL ?? PUBLIC_BASE;


function isServer(): boolean {
  return typeof window === 'undefined';
}

function baseUrl(): string {
  return isServer() ? SERVER_BASE : PUBLIC_BASE;
}

export interface RequestOpts {
  personaId?: PersonaId;
  signal?: AbortSignal;
}

async function jsonFetch<T>(
  path: string,
  init: RequestInit,
  opts: RequestOpts = {},
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set('Content-Type', 'application/json');
  if (opts.personaId) headers.set('X-Persona-Id', opts.personaId);

  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers,
    signal: opts.signal,
    cache: 'no-store',  // PoC - 매 호출 최신 응답
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}


// ─── 시나리오 A: Search ─────────────────────────────────────────────────────

export interface SearchHit {
  id: string;
  score: number;
  source: 'real' | 'synthetic' | 'external';
  title: string;
  snippet: string;
  node_type: string;
  metadata: Record<string, unknown>;
}

export interface SubgraphNode {
  id: string;
  label: string;
  data: Record<string, unknown>;
}

export interface SubgraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface Subgraph {
  root_id: string;
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}

export interface SearchResponse {
  query: string;
  persona_id: PersonaId;
  scenario_code: string;
  cohort_used: string[];
  hits: SearchHit[];
  top_hit_subgraph: Subgraph | null;
  extras: Record<string, unknown>;
}

export async function search(
  q: string,
  opts: RequestOpts & { topK?: number; includeSubgraph?: boolean } = {},
): Promise<SearchResponse> {
  return jsonFetch<SearchResponse>(
    '/api/search',
    {
      method: 'POST',
      body: JSON.stringify({
        q,
        top_k: opts.topK ?? 10,
        include_subgraph: opts.includeSubgraph ?? true,
      }),
    },
    opts,
  );
}


// ─── 시나리오 B: Chat ───────────────────────────────────────────────────────

export type ChatMode = 'chatbot' | 'agent' | 'agentic' | 'compare';

export interface StageResult {
  stage: string;
  text: string;
  sources_used: Array<Record<string, unknown>>;
  tools_called: string[];
  agents_invoked: string[];
  political_balance_score: number;
  alarm: boolean;
  duration_ms: number;
  extras: Record<string, unknown>;
}

export interface ChatResponse {
  mode: ChatMode;
  persona_id: PersonaId;
  query: string;
  scenario_code: string;
  results: Record<string, StageResult>;
}

export async function chat(
  query: string,
  mode: ChatMode = 'compare',
  opts: RequestOpts = {},
): Promise<ChatResponse> {
  return jsonFetch<ChatResponse>(
    '/api/chat',
    {
      method: 'POST',
      body: JSON.stringify({ query, mode }),
    },
    opts,
  );
}


// ─── SSE streaming (Phase 5 Track 5-5) ──────────────────────────────────────

export type StreamEvent =
  | { type: 'phase'; data: { stage: string; status: string; approach?: string } }
  | { type: 'log'; data: { stage: string; tool_called?: string; agent_invoked?: string } }
  | { type: 'result'; data: { stage: string } & StageResult }
  | { type: 'done'; data: { total_ms: number; persona_id: string; query: string } };

export interface ChatStreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  onError?: (error: Error) => void;
}

/** POST /api/chat/stream SSE 소비. ReadableStream + manual parse. */
export async function chatStream(
  query: string,
  callbacks: ChatStreamCallbacks,
  opts: RequestOpts = {},
): Promise<void> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };
  if (opts.personaId) headers['X-Persona-Id'] = opts.personaId;

  let response: Response;
  try {
    response = await fetch(`${baseUrl()}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, mode: 'compare' }),
      signal: opts.signal,
    });
  } catch (e) {
    callbacks.onError?.(e as Error);
    return;
  }
  if (!response.ok || !response.body) {
    callbacks.onError?.(new Error(`SSE stream failed: ${response.status}`));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';

  // SSE 형식: "event: <name>\r\ndata: <json>\r\n\r\n" (sse-starlette) 또는 "\n\n".
  // 양쪽 지원을 위해 \r\n → \n 정규화 후 \n\n으로 split.
  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (e) {
      callbacks.onError?.(e as Error);
      return;
    }
    if (chunk.done) break;
    buf += decoder.decode(chunk.value, { stream: true });
    buf = buf.replace(/\r\n/g, '\n');  // CRLF → LF 정규화

    let sep: number;
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const rawEvent = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const parsed = parseSseEvent(rawEvent);
      if (parsed) callbacks.onEvent(parsed);
    }
  }
}


function parseSseEvent(raw: string): StreamEvent | null {
  let eventName = 'message';
  let dataStr = '';
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim();
    else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
  }
  if (!dataStr) return null;
  try {
    const data = JSON.parse(dataStr);
    return { type: eventName as StreamEvent['type'], data };
  } catch {
    return null;
  }
}


// ─── 시나리오 L: Ad Match ───────────────────────────────────────────────────

export type AdMatchMode = 'keyword' | 'embedding' | 'agent' | 'compare';

export interface AdMatchDecision {
  decision_id: string;
  mode: string;
  article_id: string;
  candidate_ad_ids: string[];
  chosen_ad_id: string | null;
  score: number;
  reason_text: string;
}

export interface AdMatchResponse {
  article_id: string;
  persona_id: PersonaId;
  mode: AdMatchMode;
  results: Record<string, AdMatchDecision>;
  governance_summary: {
    total_modes: number;
    modes_skipped_ads: string[];
    modes_chose_ads: Record<string, string>;
    key_message: string;
  };
}

export async function adMatch(
  articleId: string,
  mode: AdMatchMode = 'compare',
  opts: RequestOpts = {},
): Promise<AdMatchResponse> {
  return jsonFetch<AdMatchResponse>(
    '/api/ad-match',
    {
      method: 'POST',
      body: JSON.stringify({ article_id: articleId, mode }),
    },
    opts,
  );
}


// ─── Health ─────────────────────────────────────────────────────────────────

export async function healthz(): Promise<{ status: string }> {
  return jsonFetch<{ status: string }>('/healthz', { method: 'GET' });
}
