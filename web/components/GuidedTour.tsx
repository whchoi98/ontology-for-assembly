'use client';

/**
 * GuidedTour - 6 페르소나 × 14 시나리오 추천 흐름.
 *
 * 청중·시연자 안내. 현재 선택된 페르소나에 맞춰 권장 시나리오 4-step flow를 보여줌.
 * 우측 하단 플로팅 버튼 → 모달.
 *
 * 데모 시 시연자가 "이번 페르소나가 보는 첫 화면은 X, 그 다음 Y..." 흐름을 청중에게
 * 보여주는 도구. Phase 4 완료 - 14 시나리오 모두 implemented, 각 페르소나별 narrative
 * 키워드를 step.why에 반영.
 */
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  DEFAULT_PERSONA,
  PERSONAS,
  getPersona,
  type PersonaId,
} from '../lib/personas';


interface TourStep {
  code: string;
  name: string;
  href: string;
  why: string;
}

const TOURS: Record<PersonaId, { headline: string; steps: TourStep[] }> = {
  editorial: {
    headline: '편집국 - 취재 보조 흐름',
    steps: [
      { code: 'A', name: '의미 검색', href: '/search',
        why: '내가 다룰 주제 발굴 - 관련 의안·의원 1-hop subgraph로 빠르게 파악.' },
      { code: 'C', name: '기사 인사이트', href: '/insights',
        why: '60건 합성 풀 + 토픽 필터로 후속 취재 가능 인사이트 bullet 자동 추출.' },
      { code: 'K', name: '표결 이상치', href: '/outlier',
        why: '★ PDF 시그니처 - 당론 이탈·박빙·정파 초월 협력 3 유형 단독 보도 후보.' },
      { code: 'M', name: '의원 정치 여정', href: '/journey',
        why: '★ PDF 시그니처 - 단일 의원의 발의·표결·발언·위원회 통합 timeline.' },
      { code: 'B', name: '3-stage 챗봇', href: '/chat',
        why: 'Agentic AI가 기사 초안 + 후속 취재 포인트 제안. Chatbot vs Agent 비교.' },
    ],
  },
  data_ai: {
    headline: '데이터·AI 데스크 - 정량 분석 흐름',
    steps: [
      { code: 'E', name: '의원 클러스터링', href: '/cluster',
        why: '5 thematic cluster - 토픽 활동 vector 기반 cross-party 협력 그룹 발굴.' },
      { code: 'J', name: '외부 신호 융합', href: '/external-signal',
        why: '12주 시계열 - signal_leads / legislation_leads / decoupled 3 패턴.' },
      { code: 'N', name: '이슈 × 입법', href: '/issue-legislation',
        why: '8×4 heatmap + Top 5 강한 결합 - dataset 입력으로 바로 활용.' },
      { code: 'F', name: '룩어라이크', href: '/lookalike',
        why: 'cluster + activity proximity 결정적 cosine 유사도. Production은 embed-v4.' },
      { code: 'B', name: '3-stage 챗봇', href: '/chat',
        why: 'Agent vs Chatbot 호출 패턴 - 도구·sources·latency 정량 비교.' },
    ],
  },
  ad_sales: {
    headline: '광고·세일즈 - 매출 + 거버넌스 흐름',
    steps: [
      { code: 'L', name: '광고 매칭 매트릭스', href: '/ad-match',
        why: '★ AI 거버넌스 메인 - keyword/embedding/Agent 3-way 차이. Agent만 비위·비극에서 광고 거절.' },
      { code: 'G', name: '기사 ROI', href: '/article-roi',
        why: '비용·도달·전환 + CPM 매출 환산. 광고 인접 ROI 상위 기사 인벤토리 매칭.' },
      { code: 'F', name: '룩어라이크', href: '/lookalike',
        why: '유사 의원 군 발굴 - 캠페인 타겟팅에 활용.' },
      { code: 'D', name: '페르소나 매칭', href: '/persona-match',
        why: '콘텐츠 → 광고 적합 페르소나 즉시 분류. tone fit으로 광고 안전성 자동 점검.' },
      { code: 'H', name: '지역구 지도', href: '/district-map',
        why: '17 시도 활동 분포 - 지역 광고 인벤토리 데이터 확보.' },
    ],
  },
  general_reader: {
    headline: '일반 독자 - 친절 가이드 흐름',
    steps: [
      { code: 'A', name: '의미 검색', href: '/search',
        why: '"AI 입법"·"내 지역구 의원" 같은 자연스러운 질문으로 시작.' },
      { code: 'B', name: '챗봇', href: '/chat',
        why: '어려운 정치 용어를 일상어로 풀어 설명. 양당 정보 균형 인용.' },
      { code: 'H', name: '지역구 지도', href: '/district-map',
        why: '17 시도 choropleth - 내 동네 의원 한눈에. 시도 선택 시 활동 상세.' },
      { code: 'M', name: '의원 정치 여정', href: '/journey',
        why: '관심 의원의 1분기 활동을 시간순으로 한눈에. 발의·표결·발언 모두 포함.' },
      { code: 'C', name: '기사 인사이트', href: '/insights',
        why: '관심 토픽 필터로 기사 탐색. 정치 균형 점수 자동 노출.' },
    ],
  },
  paid_subscriber: {
    headline: '유료 구독자 - 심층 분석 흐름',
    steps: [
      { code: 'C', name: '기사 인사이트', href: '/insights',
        why: '60건 풀 + 토픽 필터. PDF 인사이트 리포트로 export 가능.' },
      { code: 'K', name: '표결 이상치', href: '/outlier',
        why: '★ 관심 의원 모니터링 - deviation_score + 패턴 라벨 + 후속 알림 hint.' },
      { code: 'M', name: '의원 정치 여정', href: '/journey',
        why: '★ 통합 timeline + PDF 리포트 export. 다른 의원과 비교 도구.' },
      { code: 'D', name: '페르소나 매칭', href: '/persona-match',
        why: '본인 관심사 기반 콘텐츠 자동 추천. affinity 매트릭스 투명 공개.' },
      { code: 'I', name: '편향·중립성', href: '/neutrality',
        why: 'ADR-0004 4-layer 가드레일 - 구독한 콘텐츠의 정치 균형 점수 직접 확인.' },
    ],
  },
  b2b: {
    headline: '기업/B2B 정책 인텔리전스 흐름',
    steps: [
      { code: 'A', name: '의안 검색 (API)', href: '/search',
        why: '관심 정책 영역 의안 JSON fetch. /api/search REST endpoint.' },
      { code: 'C', name: '기사 인사이트 (API)', href: '/insights',
        why: 'referenced_bill_ids·person_ids로 객체 그래프 자동 확장.' },
      { code: 'J', name: '외부 신호 (시계열)', href: '/external-signal',
        why: 'weeks[] 배열 시계열 - 자체 시계열 모델 입력으로 자동 추출.' },
      { code: 'K', name: '표결 이상치 (알림)', href: '/outlier',
        why: '규제 변화 조기 경보 - outlier 알림 webhook 연결.' },
      { code: 'G', name: '기사 ROI (단위 명시)', href: '/article-roi',
        why: 'metrics 키 KRW unit 명시 - 자체 dashboard 자동 통합 가능.' },
    ],
  },
};

const STORAGE_KEY = 'persona_id';


export function GuidedTour() {
  const [open, setOpen] = useState(false);
  const [persona, setPersona] = useState<PersonaId>(DEFAULT_PERSONA);

  useEffect(() => {
    const stored = (typeof window !== 'undefined'
      ? window.localStorage.getItem(STORAGE_KEY)
      : null) as PersonaId | null;
    if (stored && PERSONAS.some((p) => p.id === stored)) {
      setPersona(stored);
    }
  }, [open]);

  const tour = TOURS[persona] ?? TOURS[DEFAULT_PERSONA];
  const personaDef = getPersona(persona);

  return (
    <>
      {/* FloatingChat (bottom-6 right-6)과 중첩 회피 — 그 위로 80px 띄움 */}
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-24 right-6 z-40 bg-blue-600 text-white text-sm px-3 py-2 rounded-full shadow-lg hover:bg-blue-700"
        aria-label="가이드 투어 열기"
      >
        🗺️ 가이드
      </button>

      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-slate-900/40 rounded-lg max-w-xl w-full max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <header className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <div className="text-xs text-slate-400 uppercase mb-0.5">
                  {personaDef.emoji} {personaDef.nameKr} · {personaDef.tier}
                </div>
                <h2 className="font-bold text-lg">{tour.headline}</h2>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  추천 {tour.steps.length} step · 14/14 시나리오 활성
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-slate-500 hover:text-slate-300 text-2xl leading-none"
                aria-label="닫기"
              >
                ×
              </button>
            </header>
            <div className="px-5 py-4 space-y-3">
              {tour.steps.map((step, idx) => (
                <Link
                  key={`${step.code}-${idx}`}
                  href={step.href}
                  className="block"
                  onClick={() => setOpen(false)}
                >
                  <article className="border border-blue-200 bg-blue-500/15 hover:bg-blue-500/20 rounded-lg p-3 transition-colors">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-gray-900 text-white">
                        Step {idx + 1}
                      </span>
                      <span className="font-mono text-xs text-slate-500">
                        시나리오 {step.code}
                      </span>
                      <h3 className="font-semibold text-white flex-1">{step.name}</h3>
                    </div>
                    <p className="text-sm text-slate-200 leading-relaxed">{step.why}</p>
                  </article>
                </Link>
              ))}
            </div>
            <footer className="px-5 py-3 border-t border-slate-800 bg-slate-800/40 text-[11px] text-slate-400">
              ※ 좌측 사이드바에서 페르소나를 변경하면 다른 흐름이 보입니다.
              {' '}각 페르소나의 KPI·관심사 우선순위가 자동 반영됩니다.
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
