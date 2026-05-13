'use client';

/**
 * GuidedTour - 6 페르소나 × 14 시나리오 추천 흐름 (Phase 5 Track 5-3).
 *
 * 청중·시연자 안내. 현재 선택된 페르소나에 맞춰 권장 시나리오 3-step flow를 보여줌.
 * 우측 하단 플로팅 버튼 → 모달.
 *
 * 데모 시 시연자가 "이번 페르소나가 보는 첫 화면은 X, 그 다음 Y, 마지막 Z" 흐름을
 * 청중에게 보여주는 도구.
 */
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  DEFAULT_PERSONA,
  PERSONAS,
  getPersona,
  type PersonaId,
} from '../lib/personas';

// 페르소나별 권장 데모 흐름 (시나리오 3-step + why).
interface TourStep {
  code: string;
  name: string;
  href: string;
  why: string;
  implemented: boolean;
}

const TOURS: Record<PersonaId, { headline: string; steps: TourStep[] }> = {
  editorial: {
    headline: '편집국 - 취재 보조 흐름',
    steps: [
      { code: 'A', name: '의미 검색', href: '/search', implemented: true,
        why: '내가 다룰 주제 발굴 - 관련 의안·의원 1-hop 그래프로 빠르게 파악' },
      { code: 'B', name: '3-stage 챗봇', href: '/chat', implemented: true,
        why: 'Agentic AI가 기사 초안 + 후속 취재 포인트까지 제안' },
      { code: 'K', name: '표결 이상치', href: '/outlier', implemented: false,
        why: '당론 이탈·스윙 보트 → 단독 보도 후보 (PDF 3페이지 시그니처)' },
    ],
  },
  data_ai: {
    headline: '데이터·AI 데스크 - 정량 분석 흐름',
    steps: [
      { code: 'E', name: '의원 클러스터링', href: '/cluster', implemented: false,
        why: 'KMeans + LLM 중립 라벨링으로 정치성향 클러스터 분석' },
      { code: 'J', name: '외부 신호 융합', href: '/external-signal', implemented: false,
        why: '뉴스+SNS+여론조사 cross-source - n·CI·CV 같은 통계 풍부' },
      { code: 'B', name: '3-stage 챗봇', href: '/chat', implemented: true,
        why: 'Agent vs Chatbot 차이를 직접 비교 - 도구 호출 횟수·sources 분석' },
    ],
  },
  ad_sales: {
    headline: '광고·세일즈 - 매출 + 거버넌스 흐름',
    steps: [
      { code: 'L', name: '광고 매칭 매트릭스', href: '/ad-match', implemented: true,
        why: '★ AI 거버넌스 메인 - keyword/embedding/Agent 3-way 차이' },
      { code: 'G', name: '기사 ROI', href: '/article-roi', implemented: false,
        why: 'Bayesian 시뮬레이션 - 광고 노출별 예상 매출' },
      { code: 'F', name: '룩어라이크', href: '/lookalike', implemented: false,
        why: '유사 의원·이슈 매칭으로 광고 인벤토리 효율화' },
    ],
  },
  general_reader: {
    headline: '일반 독자 - 친절 가이드 흐름',
    steps: [
      { code: 'A', name: '의미 검색', href: '/search', implemented: true,
        why: '"AI 입법"·"내 지역구 의원" 같은 자연스러운 질문으로 시작' },
      { code: 'B', name: '챗봇', href: '/chat', implemented: true,
        why: '어려운 정치 용어를 일상어로 풀어 설명' },
      { code: 'H', name: '지역구 지도', href: '/district-map', implemented: false,
        why: '17 시도 choropleth - 내 동네 의원 한눈에' },
    ],
  },
  paid_subscriber: {
    headline: '유료 구독자 - 심층 분석 흐름',
    steps: [
      { code: 'C', name: '기사 인사이트', href: '/insights', implemented: false,
        why: 'Code Interpreter 차트 + PDF 리포트로 저장' },
      { code: 'K', name: '표결 이상치', href: '/outlier', implemented: false,
        why: '관심 의원 모니터링 - 알림 설정 가능' },
      { code: 'M', name: '의원 정치 여정', href: '/journey', implemented: false,
        why: '발의·표결·발언 통합 timeline - 의원 비교 도구' },
    ],
  },
  b2b: {
    headline: '기업/B2B 정책 인텔리전스 흐름',
    steps: [
      { code: 'A', name: '의안 검색 (API)', href: '/search', implemented: true,
        why: '관심 정책 영역 의안을 JSON으로 fetch' },
      { code: 'J', name: '외부 신호', href: '/external-signal', implemented: false,
        why: '시장·산업 시그널과 입법 동향 cross-reference' },
      { code: 'K', name: '표결·발언 패턴', href: '/outlier', implemented: false,
        why: '규제 변화 조기 경보 - 알림 webhook' },
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
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 bg-blue-600 text-white text-sm px-3 py-2 rounded-full shadow-lg hover:bg-blue-700"
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
            className="bg-white rounded-lg max-w-xl w-full max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <header className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 uppercase mb-0.5">
                  {personaDef.emoji} {personaDef.nameKr} · {personaDef.tier}
                </div>
                <h2 className="font-bold text-lg">{tour.headline}</h2>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
                aria-label="닫기"
              >
                ×
              </button>
            </header>
            <div className="px-5 py-4 space-y-3">
              {tour.steps.map((step, idx) => {
                const inner = (
                  <article
                    className={
                      'border rounded-lg p-3 ' +
                      (step.implemented
                        ? 'border-blue-200 bg-blue-50 hover:bg-blue-100'
                        : 'border-gray-200 bg-gray-50 opacity-70')
                    }
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-gray-900 text-white">
                        Step {idx + 1}
                      </span>
                      <span className="font-mono text-xs text-gray-400">
                        시나리오 {step.code}
                      </span>
                      <h3 className="font-semibold text-gray-900 flex-1">{step.name}</h3>
                      {!step.implemented && (
                        <span className="text-[10px] text-gray-500">⏳ 후속 phase</span>
                      )}
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed">{step.why}</p>
                  </article>
                );
                return step.implemented ? (
                  <Link
                    key={idx}
                    href={step.href}
                    className="block"
                    onClick={() => setOpen(false)}
                  >
                    {inner}
                  </Link>
                ) : (
                  <div key={idx}>{inner}</div>
                );
              })}
            </div>
            <footer className="px-5 py-3 border-t border-gray-200 bg-gray-50 text-xs text-gray-500">
              ※ 페르소나를 좌측 사이드바에서 변경하면 다른 권장 흐름이 보입니다.
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
