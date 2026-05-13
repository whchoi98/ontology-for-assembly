import Link from 'next/link';
import React from 'react';

/**
 * 홈 페이지 - 시나리오 카드 그리드.
 */

const CARDS: Array<{
  code: string;
  name: string;
  description: string;
  href: string;
  implemented: boolean;
  highlight?: string;
}> = [
  {
    code: 'A',
    name: '의미 검색',
    description: 'BM25(Nori) + Cohere KNN + RRF + rerank-v3로 의안·의원 검색. 1-hop subgraph.',
    href: '/search',
    implemented: true,
  },
  {
    code: 'B',
    name: '3-stage 챗봇',
    description:
      'Chatbot(RAG) / Agent(Tool Use) / Agentic AI(4 에이전트) 사이드바이사이드 비교 시연.',
    href: '/chat',
    implemented: true,
    highlight: '데모 메인',
  },
  {
    code: 'L',
    name: '광고 매칭 매트릭스',
    description:
      'keyword / embedding / Agent 3-way 비교. Agent만 비위 의혹·비극 콘텐츠에서 광고 거절.',
    href: '/ad-match',
    implemented: true,
    highlight: 'AI 거버넌스',
  },
  { code: 'C', name: '기사 인사이트', description: 'Code Interpreter 차트 + 한국어 요약.', href: '/insights', implemented: false },
  { code: 'D', name: '페르소나 매칭', description: '6 페르소나 KPI 가중치 그래프 워크.', href: '/persona-match', implemented: false },
  { code: 'E', name: '의원 클러스터링', description: 'KMeans + 중립 라벨링.', href: '/cluster', implemented: false },
  { code: 'F', name: '룩어라이크', description: 'Cohere embed-v4 + KNN top-X%.', href: '/lookalike', implemented: false },
  { code: 'G', name: '기사 ROI 시뮬', description: 'Bayesian 추정 + 분포 차트.', href: '/article-roi', implemented: false },
  { code: 'H', name: '지역구 지도', description: '17 시도 choropleth.', href: '/district-map', implemented: false },
  { code: 'I', name: '편향·중립성', description: 'political_balance_score + bias detector.', href: '/neutrality', implemented: false },
  { code: 'J', name: '외부 신호 융합', description: '뉴스 + SNS + 여론조사 cross-source.', href: '/external-signal', implemented: false },
  { code: 'K', name: '표결 이상치', description: '당론 이탈·스윙 보트 탐지.', href: '/outlier', implemented: false },
  { code: 'M', name: '의원 정치 여정', description: '발의·표결·발언 통합 timeline.', href: '/journey', implemented: false },
  { code: 'N', name: '이슈 × 입법', description: '토픽 트렌드 ↔ 법안 발의 산점도.', href: '/issue-legislation', implemented: false },
];

export default function HomePage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">14 시나리오 (A–N)</h1>
        <p className="text-gray-600">
          6 페르소나 × 14 시나리오. 같은 데이터를 청중에 맞춰 다르게 시연. 좌측 페르소나 토글로 전환.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CARDS.map((card) => {
          const inner = (
            <article
              className={
                'rounded-lg border p-4 transition-shadow ' +
                (card.implemented
                  ? 'border-gray-200 hover:shadow-md hover:border-blue-300 bg-white'
                  : 'border-gray-100 bg-gray-50 opacity-60')
              }
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-sm text-gray-400">시나리오 {card.code}</span>
                {card.highlight && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">
                    {card.highlight}
                  </span>
                )}
              </div>
              <h2 className="text-lg font-semibold mb-1.5 text-gray-900">{card.name}</h2>
              <p className="text-sm text-gray-600 leading-relaxed">{card.description}</p>
              {!card.implemented && (
                <div className="mt-3 text-xs text-gray-400">⏳ 후속 phase에서 구현</div>
              )}
            </article>
          );
          return card.implemented ? (
            <Link key={card.code} href={card.href} className="block">
              {inner}
            </Link>
          ) : (
            <div key={card.code}>{inner}</div>
          );
        })}
      </div>
    </div>
  );
}
