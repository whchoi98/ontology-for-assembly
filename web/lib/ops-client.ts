/**
 * 운영 콘솔 API 클라이언트 (Phase 5 Track 5-2).
 *
 * 5 패널 데이터 fetch + 타입드 응답. server / client 양용.
 */

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
const SERVER_BASE = process.env.INTERNAL_API_BASE_URL ?? PUBLIC_BASE;

function baseUrl(): string {
  return typeof window === 'undefined' ? SERVER_BASE : PUBLIC_BASE;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}


export interface IngestPanel {
  output_dir: string | null;
  last_updated: string | null;
  file_counts: Record<string, number>;
  source_distribution: Record<string, number>;
  note: string;
}

export interface GuardrailPanel {
  total_invocations: number;
  total_blocked: number;
  total_alarms_low_balance: number;
  avg_balance_score: number;
  blocked_by_topic: Record<string, number>;
  threshold: number;
}

export interface MemoryPanel {
  store_id: string | null;
  active_sessions_estimate: number;
  namespaces: string[];
  note: string;
}

export interface QualityPanel {
  last_run_iso: string | null;
  total_cases: number;
  pass_count: number;
  pass_rate: number;
  avg_balance_score: number | null;
  note: string;
}

export interface TraceEntry {
  ts_iso: string;
  persona_id: string;
  scenario_code: string;
  model_id: string;
  political_balance_score: number;
  alarm: boolean;
  alarm_reason: string | null;
  blocked_topics: string[];
  duration_ms: number;
}

export interface TracePanel {
  buffer_size: number;
  entries: TraceEntry[];
}

export const opsApi = {
  ingest: () => getJson<IngestPanel>('/api/ops/ingest'),
  guardrail: () => getJson<GuardrailPanel>('/api/ops/guardrail'),
  memory: () => getJson<MemoryPanel>('/api/ops/memory'),
  wowQuality: () => getJson<QualityPanel>('/api/ops/wow-quality'),
  trace: (limit = 20) => getJson<TracePanel>(`/api/ops/trace?limit=${limit}`),
};
