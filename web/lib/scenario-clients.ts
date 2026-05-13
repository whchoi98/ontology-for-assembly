/**
 * 시나리오별 API 클라이언트 모음 (Phase 4 시나리오 라우터들).
 *
 * api-client.ts는 기존 A·B·L 시나리오 + ops + objects 호출.
 * 본 파일은 Phase 4의 신규 시나리오(K·M·I·H·C·J·D·E·F·N·G) 호출.
 */
import type { PersonaId } from './personas';

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8080';

function baseUrl(): string {
  return typeof window === 'undefined'
    ? (process.env.INTERNAL_API_BASE_URL ?? PUBLIC_BASE)
    : PUBLIC_BASE;
}

async function getJson<T>(path: string, personaId?: PersonaId): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (personaId) headers['X-Persona-Id'] = personaId;
  const response = await fetch(`${baseUrl()}${path}`, { headers, cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}


// ─── 시나리오 K: 표결 이상치 ────────────────────────────────────────────────

export interface DeviatingPerson {
  person_id: string;
  name: string;
  party: string;
  choice: string;
  reason_hint: string | null;
}

export interface OutlierEntry {
  outlier_id: string;
  vote_id: string;
  bill_id: string;
  bill_title: string;
  vote_date: string;
  outlier_type: 'party_line_break' | 'swing_vote' | 'cross_party';
  label: string;
  description: string;
  deviation_score: number;
  expected_pattern: string;
  actual_pattern: string;
  deviating_persons: DeviatingPerson[];
  ai_label: string;
}

export interface OutlierListResponse {
  persona_id: PersonaId;
  scenario_code: string;
  total: number;
  outliers: OutlierEntry[];
  persona_note: string;
}

export interface OutlierDetailResponse {
  persona_id: PersonaId;
  outlier: OutlierEntry;
  extras: { persona_name_kr?: string; follow_up_hint?: string };
}

export const outlierApi = {
  list: (opts: { limit?: number; outlierType?: string; personaId?: PersonaId } = {}) => {
    const params = new URLSearchParams();
    if (opts.limit) params.set('limit', String(opts.limit));
    if (opts.outlierType) params.set('outlier_type', opts.outlierType);
    const q = params.toString();
    return getJson<OutlierListResponse>(`/api/outlier${q ? `?${q}` : ''}`, opts.personaId);
  },
  detail: (id: string, personaId?: PersonaId) =>
    getJson<OutlierDetailResponse>(`/api/outlier/${id}`, personaId),
};
