/**
 * 시나리오별 API 클라이언트 모음 (Phase 4 시나리오 라우터들).
 *
 * api-client.ts는 기존 A·B·L 시나리오 + ops + objects 호출.
 * 본 파일은 Phase 4의 신규 시나리오(K·M·I·H·C·J·D·E·F·N·G) 호출.
 */
import type { PersonaId } from './personas';

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

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


// ─── 시나리오 M: 의원 정치 여정 (PDF 시그니처 ★) ───────────────────────────

export interface JourneyEvent {
  event_id: string;
  date: string;
  event_type: 'proposed' | 'co_proposed' | 'voted' | 'statement' | 'committee_join';
  title: string;
  description: string;
  related_id: string | null;
  icon: string;
}

export interface JourneyResponse {
  persona_id: PersonaId;
  person_id: string;
  person_name: string;
  party: string | null;
  term: number;
  district: string | null;
  summary: string;
  events: JourneyEvent[];
  stats: {
    total_events: number;
    proposed: number;
    co_proposed: number;
    voted: number;
    statements: number;
    committees: number;
    period_start: string;
    period_end: string;
  };
  extras: {
    persona_name_kr?: string;
    tone?: string;
    follow_up_hint?: string;
    premium_cta?: string;
    guide_hint?: string;
    api_response_hint?: string;
  };
}

export interface AvailablePerson {
  person_id: string;
  name: string;
  party: string | null;
  district: string | null;
  highlighted: boolean;
}

export interface AvailablePersonsResponse {
  available_persons: AvailablePerson[];
}

export const journeyApi = {
  listPersons: () => getJson<AvailablePersonsResponse>('/api/journey/persons'),
  detail: (personId: string, personaId?: PersonaId) =>
    getJson<JourneyResponse>(`/api/journey/${personId}`, personaId),
};


// ─── 시나리오 I: 편향·중립성 가드레일 (ADR-0004 시연) ─────────────────────

export interface BalanceComponents {
  party_mention_balance: number;
  citation_score: number;
  assertion_penalty: number;
  parties_mentioned: string[];
  total_party_mentions: number;
  citation_count: number;
  assertion_count: number;
}

export interface NeutralitySample {
  sample_id: string;
  label: '낮음' | '중간' | '양호' | '우수';
  description: string;
  text: string;
  score: number;
  components: BalanceComponents;
  alarm: boolean;
}

export interface NeutralitySamplesResponse {
  persona_id: PersonaId;
  samples: NeutralitySample[];
  threshold: number;
  note: string;
}

export interface NeutralityScoreResponse {
  text: string;
  score: number;
  alarm: boolean;
  components: BalanceComponents;
  guardrail_passed: boolean;
  blocked_topics: string[];
  persona_id: PersonaId;
  interpretation: string;
}

export interface NeutralityArchLayer {
  layer: number;
  name: string;
  where: string;
  description: string;
  is_active: boolean;
}

export interface NeutralityArchitectureResponse {
  persona_id: PersonaId;
  layers: NeutralityArchLayer[];
  adr_reference: string;
  party_catalog: string[];
  weights: {
    party_balance: number;
    citation: number;
    assertion_penalty: number;
    alarm_threshold: number;
  };
}

export interface NeutralityRecentTrace {
  ts_iso: string;
  persona_id: PersonaId;
  scenario_code: string;
  political_balance_score: number;
  alarm: boolean;
  alarm_reason: string | null;
  blocked_topics: string[];
}

export interface NeutralityRecentResponse {
  persona_id: PersonaId;
  traces: NeutralityRecentTrace[];
  counters: {
    total_invocations: number;
    total_blocked: number;
    total_alarms_low_balance: number;
    avg_balance_score: number;
    blocked_by_topic: Record<string, number>;
  };
  threshold: number;
}

async function postJson<T>(path: string, body: unknown, personaId?: PersonaId): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (personaId) headers['X-Persona-Id'] = personaId;
  const response = await fetch(`${baseUrl()}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const neutralityApi = {
  samples: (personaId?: PersonaId) =>
    getJson<NeutralitySamplesResponse>('/api/neutrality/samples', personaId),
  architecture: (personaId?: PersonaId) =>
    getJson<NeutralityArchitectureResponse>('/api/neutrality/architecture', personaId),
  recent: (limit = 20, personaId?: PersonaId) =>
    getJson<NeutralityRecentResponse>(`/api/neutrality/recent?limit=${limit}`, personaId),
  score: (text: string, personaId?: PersonaId) =>
    postJson<NeutralityScoreResponse>('/api/neutrality/score', { text }, personaId),
};


// ─── 시나리오 H: 지역구 지도 ───────────────────────────────────────────────

export interface SidoStats {
  key: string;
  name_kr: string;
  short_kr: string;
  kostat_code: string;
  grid_row: number;
  grid_col: number;
  member_count: number;
  parties: Record<string, number>;
  activity: { proposed: number; voted: number; statements: number };
  density_label: string;
}

export interface SidoMember {
  person_id: string;
  name: string;
  party: string;
  district: string;
  activity_summary: string;
}

export interface DistrictMapSummaryResponse {
  persona_id: PersonaId;
  total_members: number;
  total_districts: number;
  sido: SidoStats[];
  persona_hint: string;
}

export interface DistrictMapDetailResponse {
  persona_id: PersonaId;
  sido: SidoStats;
  members: SidoMember[];
  summary: string;
  extras: {
    persona_name_kr?: string;
    tone?: string;
    follow_up_hint?: string;
    premium_cta?: string;
    guide_hint?: string;
    api_response_hint?: string;
  };
}

export const districtMapApi = {
  summary: (personaId?: PersonaId) =>
    getJson<DistrictMapSummaryResponse>('/api/district-map/summary', personaId),
  detail: (sidoKey: string, personaId?: PersonaId) =>
    getJson<DistrictMapDetailResponse>(`/api/district-map/${sidoKey}`, personaId),
};


// ─── 시나리오 C: 기사 인사이트 ─────────────────────────────────────────────

export interface TopicLink {
  topic_id: string;
  name: string;
  category: string;
}

export interface ArticleListEntry {
  article_id: string;
  title: string;
  published_at: string;
  author: string;
  topic_count: number;
  referenced_persons: number;
  referenced_bills: number;
  primary_topic: TopicLink | null;
}

export interface ArticleListResponse {
  persona_id: PersonaId;
  total: number;
  offset: number;
  limit: number;
  topic_filter: string | null;
  articles: ArticleListEntry[];
}

export interface TopicsResponse {
  persona_id: PersonaId;
  total: number;
  topics: TopicLink[];
}

export interface InsightDetailResponse {
  persona_id: PersonaId;
  article_id: string;
  title: string;
  content: string;
  published_at: string;
  author: string;
  topics: TopicLink[];
  referenced_person_ids: string[];
  referenced_bill_ids: string[];
  political_balance_score: number;
  balance_alarm: boolean;
  summary: string;
  insights: string[];
  extras: {
    persona_name_kr?: string;
    tone?: string;
    follow_up_hint?: string;
    cohort_hint?: string;
    ad_hint?: string;
    guide_hint?: string;
    premium_cta?: string;
    api_response_hint?: string;
  };
}

export const insightsApi = {
  topics: (personaId?: PersonaId) =>
    getJson<TopicsResponse>('/api/insights/topics', personaId),
  articles: (
    opts: { offset?: number; limit?: number; topicId?: string; personaId?: PersonaId } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.offset != null) params.set('offset', String(opts.offset));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    if (opts.topicId) params.set('topic_id', opts.topicId);
    const q = params.toString();
    return getJson<ArticleListResponse>(
      `/api/insights/articles${q ? `?${q}` : ''}`, opts.personaId,
    );
  },
  detail: (articleId: string, personaId?: PersonaId) =>
    getJson<InsightDetailResponse>(`/api/insights/articles/${articleId}`, personaId),
};


// ─── 시나리오 J: 외부 신호 융합 ────────────────────────────────────────────

export type FusionPattern = 'signal_leads' | 'legislation_leads' | 'decoupled';

export interface WeeklyPoint {
  week_iso: string;
  signal_count: number;
  bill_count: number;
}

export interface TopicFusion {
  fusion_id: string;
  topic_id: string;
  topic_name: string;
  pattern: FusionPattern;
  pattern_label: string;
  weeks: WeeklyPoint[];
  peak_signal_week: string;
  peak_legislation_week: string;
  lag_weeks: number;
  correlation_hint: number;
  narrative: string;
  sources: string[];
}

export interface FusionListResponse {
  persona_id: PersonaId;
  scenario_code: 'J';
  total: number;
  pattern_filter: FusionPattern | null;
  fusions: TopicFusion[];
  persona_note: string;
}

export interface FusionDetailResponse {
  persona_id: PersonaId;
  fusion: TopicFusion;
  extras: {
    persona_name_kr?: string;
    tone?: string;
    follow_up_hint?: string;
    analysis_hint?: string;
    premium_cta?: string;
    api_response_hint?: string;
  };
}

export const externalSignalApi = {
  list: (opts: { pattern?: FusionPattern; personaId?: PersonaId } = {}) => {
    const params = new URLSearchParams();
    if (opts.pattern) params.set('pattern', opts.pattern);
    const q = params.toString();
    return getJson<FusionListResponse>(
      `/api/external-signal${q ? `?${q}` : ''}`, opts.personaId,
    );
  },
  detail: (fusionId: string, personaId?: PersonaId) =>
    getJson<FusionDetailResponse>(`/api/external-signal/${fusionId}`, personaId),
};


// ─── 시나리오 D: 페르소나 매칭 ─────────────────────────────────────────────

export interface PersonaScore {
  persona_id: PersonaId;
  name_kr: string;
  score: number;
  topic_affinity: number;
  kpi_keyword_match: number;
  tone_fit: number;
  reasons: string[];
}

export interface MatchResult {
  persona_id: PersonaId;
  source_kind: 'article' | 'text';
  source_id: string | null;
  title: string;
  content_excerpt: string;
  topic_categories: string[];
  balance_score: number;
  scores: PersonaScore[];
  top_persona_id: PersonaId;
  rationale: string;
}

export interface AffinityMatrixResponse {
  persona_id: PersonaId;
  matrix: Record<string, Record<string, number>>;
  weights: { topic_affinity: number; kpi_keyword: number; tone_fit: number };
  note: string;
}

export const personaMatchApi = {
  matrix: (personaId?: PersonaId) =>
    getJson<AffinityMatrixResponse>('/api/persona-match/matrix', personaId),
  article: (articleId: string, personaId?: PersonaId) =>
    getJson<MatchResult>(`/api/persona-match/article/${articleId}`, personaId),
  text: (text: string, topicCategoryHints?: string[], personaId?: PersonaId) =>
    postJson<MatchResult>(
      '/api/persona-match/text',
      { text, topic_category_hints: topicCategoryHints },
      personaId,
    ),
};


// ─── 시나리오 E: 의원 클러스터링 ───────────────────────────────────────────

export interface ClusterMember {
  person_id: string;
  name: string;
  party: string;
  district: string;
  activity_score: number;
}

export interface ClusterEntry {
  cluster_id: string;
  label: string;
  dominant_topics: string[];
  description: string;
  member_count: number;
  members: ClusterMember[];
  parties_represented: string[];
  cross_party_share: number;
  avg_activity: { proposed: number; voted: number; statements: number };
  coherence_score: number;
  insight: string;
}

export interface ClusterListResponse {
  persona_id: PersonaId;
  total: number;
  clusters: ClusterEntry[];
  persona_note: string;
}

export interface ClusterDetailResponse {
  persona_id: PersonaId;
  cluster: ClusterEntry;
  extras: {
    persona_name_kr?: string;
    tone?: string;
    follow_up_hint?: string;
    premium_cta?: string;
    api_response_hint?: string;
  };
}

export const clusterApi = {
  list: (personaId?: PersonaId) =>
    getJson<ClusterListResponse>('/api/cluster', personaId),
  detail: (clusterId: string, personaId?: PersonaId) =>
    getJson<ClusterDetailResponse>(`/api/cluster/${clusterId}`, personaId),
};


// ─── 시나리오 F: 룩어라이크 ────────────────────────────────────────────────

export interface LookalikeSeed {
  person_id: string;
  name: string;
  party: string;
  district: string;
  cluster_label: string;
}

export interface LookalikeCandidate {
  person_id: string;
  name: string;
  party: string;
  district: string;
  similarity: number;
  cluster_id: string;
  cluster_label: string;
  activity_score: number;
  factors: string[];
  cross_party_signal: boolean;
}

export interface LookalikeResult {
  persona_id: PersonaId;
  seed_person_id: string;
  seed_name: string;
  seed_party: string;
  seed_cluster_id: string | null;
  seed_cluster_label: string | null;
  candidates: LookalikeCandidate[];
  narrative: string;
  sources: string[];
  extras: {
    persona_name_kr?: string;
    tone?: string;
    follow_up_hint?: string;
    analysis_hint?: string;
    premium_cta?: string;
    api_response_hint?: string;
  };
}

export interface LookalikeSeedsResponse {
  persona_id: PersonaId;
  total: number;
  seeds: LookalikeSeed[];
}

export const lookalikeApi = {
  seeds: (personaId?: PersonaId) =>
    getJson<LookalikeSeedsResponse>('/api/lookalike/seeds', personaId),
  detail: (personId: string, topK = 5, personaId?: PersonaId) =>
    getJson<LookalikeResult>(`/api/lookalike/${personId}?top_k=${topK}`, personaId),
};


// ─── 시나리오 N: 이슈×입법 상관 ────────────────────────────────────────────

export interface ActivityIntensity {
  activity: string;
  value: number;
  intensity_label: '매우 높음' | '높음' | '보통' | '낮음';
}

export interface IssueRow {
  issue_id: string;
  issue_name: string;
  category: string;
  activities: ActivityIntensity[];
  dominant_activity: string;
}

export interface IssueCorrelation {
  issue_id: string;
  issue_name: string;
  activity: string;
  intensity: number;
  correlation_label: string;
  insight: string;
}

export interface IssueLegislationMatrix {
  persona_id: PersonaId;
  activity_types: string[];
  rows: IssueRow[];
  top_correlations: IssueCorrelation[];
  sources: string[];
  persona_note: string;
}

export const issueLegislationApi = {
  matrix: (personaId?: PersonaId) =>
    getJson<IssueLegislationMatrix>('/api/issue-legislation', personaId),
};


// ─── 시나리오 G: 기사 ROI ──────────────────────────────────────────────────

export interface RoiMetrics {
  cost_won: number;
  reach_pv: number;
  reach_share: number;
  avg_dwell_sec: number;
  conv_value_won: number;
  roi_pct: number;
}

export interface PersonaKpi {
  persona_id: PersonaId;
  name_kr: string;
  kpi_label: string;
  kpi_value: string;
  note: string;
}

export interface RoiEntry {
  article_id: string;
  title: string;
  primary_topic: string | null;
  metrics: RoiMetrics;
  persona_kpis: PersonaKpi[];
  sources: string[];
}

export interface RoiListResponse {
  persona_id: PersonaId;
  total: number;
  offset: number;
  limit: number;
  entries: RoiEntry[];
  persona_note: string;
}

export interface RoiDetailResponse {
  persona_id: PersonaId;
  entry: RoiEntry;
  extras: {
    follow_up_hint?: string;
    ad_revenue_hint?: string;
    premium_cta?: string;
    api_response_hint?: string;
  };
}

export const articleRoiApi = {
  list: (opts: { offset?: number; limit?: number; personaId?: PersonaId } = {}) => {
    const params = new URLSearchParams();
    if (opts.offset != null) params.set('offset', String(opts.offset));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const q = params.toString();
    return getJson<RoiListResponse>(`/api/article-roi${q ? `?${q}` : ''}`, opts.personaId);
  },
  detail: (articleId: string, personaId?: PersonaId) =>
    getJson<RoiDetailResponse>(`/api/article-roi/${articleId}`, personaId),
};
