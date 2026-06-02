/**
 * 6 페르소나 SSOT (web 측 mirror).
 *
 * 백엔드 `api.services.persona.PERSONA_REGISTRY`와 정합 유지 - 변경 시 양쪽 동시.
 * 향후 GET /api/personas로 fetch하도록 변환 가능.
 */

export type PersonaId =
  | 'editorial'
  | 'data_ai'
  | 'ad_sales'
  | 'general_reader'
  | 'paid_subscriber'
  | 'b2b';

export type Tier = 'staff' | 'b2c_free' | 'b2c_paid' | 'b2b';

// UI 그룹핑 (Sidebar·PersonaSwitch 헤더). 백엔드 TIER_GROUP_KR 미러.
export const TIER_GROUP_KR: Record<Tier, string> = {
  staff:    '미디어/신문사 내부용',
  b2c_free: '구독자용 (무료)',
  b2c_paid: '유료 구독자용',
  b2b:      'B2B 정책 인텔리전스',
};

export const TIER_GROUP_ORDER: Tier[] = ['staff', 'b2c_free', 'b2c_paid', 'b2b'];

export interface Persona {
  id: PersonaId;
  nameKr: string;
  tier: Tier;
  emoji: string;       // UI 시각 식별
  description: string;
}

// 페르소나별 *주력 시나리오* (top 4-5) — 사이드바 동적 정렬·하이라이트 SSOT.
// 백엔드 PERSONA_REGISTRY.scenario_priority 미러 (ADR-0002).
export const PERSONA_PRIMARY_SCENARIOS: Record<PersonaId, string[]> = {
  editorial:       ['C', 'B', 'K', 'M', 'A'],   // 편집국: 취재·기사·심층
  data_ai:         ['E', 'J', 'K', 'N', 'F'],   // 데이터·AI: 분석·통계
  ad_sales:        ['L', 'G', 'F', 'D'],         // 광고·세일즈: 매칭·ROI
  general_reader:  ['A', 'B', 'H', 'M'],         // 일반독자: 탐색·발견
  paid_subscriber: ['C', 'K', 'M', 'D', 'B'],   // 유료: 심층·PDF
  b2b:             ['A', 'C', 'J', 'K', 'N'],   // B2B: 정책 모니터링
};

// lucide icon name (PersonaSwitch에서 lucide-react import로 매핑).
// 사용자 신고: 페르소나 아이콘도 투명 fill + currentColor stroke 패턴 일관 적용.
export const PERSONA_ICON: Record<PersonaId, string> = {
  editorial:       'PenTool',         // 편집국 — 펜
  data_ai:         'LineChart',       // 데이터·AI — 차트
  ad_sales:        'Megaphone',       // 광고·세일즈 — 확성기
  general_reader:  'User',            // 일반 독자 — 사용자
  paid_subscriber: 'Crown',           // 유료 구독자 — 왕관
  b2b:             'Building2',       // B2B — 건물
};

export const PERSONAS: Persona[] = [
  {
    id: 'editorial',
    nameKr: '편집국',
    tier: 'staff',
    emoji: '✍️',
    description: '정치부 기자 - 취재·기사 작성 보조',
  },
  {
    id: 'data_ai',
    nameKr: '데이터·AI',
    tier: 'staff',
    emoji: '📊',
    description: '데이터·AI 데스크 - 정량 분석·통계',
  },
  {
    id: 'ad_sales',
    nameKr: '광고·세일즈',
    tier: 'staff',
    emoji: '🎯',
    description: '광고 매칭·평판 보호·매출',
  },
  {
    id: 'general_reader',
    nameKr: '일반 독자',
    tier: 'b2c_free',
    emoji: '👤',
    description: '일반 독자 (B2C 무료) - 친절 가이드',
  },
  {
    id: 'paid_subscriber',
    nameKr: '유료 구독자',
    tier: 'b2c_paid',
    emoji: '⭐',
    description: '유료 구독자 - 심층 분석·PDF·알림',
  },
  {
    id: 'b2b',
    nameKr: '기업/B2B',
    tier: 'b2b',
    emoji: '🏢',
    description: '정책 인텔리전스 - API·JSON 응답',
  },
];

export const DEFAULT_PERSONA: PersonaId = 'editorial';

export function getPersona(id: string | null): Persona {
  const found = PERSONAS.find((p) => p.id === id);
  return found ?? PERSONAS[0];
}
