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

export interface Persona {
  id: PersonaId;
  nameKr: string;
  tier: Tier;
  emoji: string;       // UI 시각 식별
  description: string;
}

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
