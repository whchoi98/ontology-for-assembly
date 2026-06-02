'use client';

/**
 * /objects/[Class]/[id] — 단일 객체 디테일 + 온톨로지 관계 그래프.
 *
 * 디자인 참고: search.naver.com 인물 검색 결과 (이재명 페이지)
 *   - 상단 hero: 사진 + 이름 + 정당 + 지역구 + composite score
 *   - 좌측: 9 활동 메트릭 사이드
 *   - 우측: 큰 온톨로지 관계 그래프 (multi-hop) — 본 페이지의 메인
 *   - 하단: depth slider + 관련 의원 그리드 (같은 위원회)
 *
 * Class별 분기:
 *   - Person: 의원 hero + 메트릭 사이드 + 온톨로지 관계 그래프
 *   - Bill/Vote/Topic/Article: 기본 메타 + 온톨로지 관계 그래프
 */
import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CytoscapeView } from '../../../../components/CytoscapeView';
import { readPersonaIdSync } from '../../../../components/PersonaSwitch';
import { TIER_GROUP_KR } from '../../../../lib/personas';
import type { Subgraph } from '../../../../lib/api-client';
import type { PersonaId, Tier } from '../../../../lib/personas';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';


interface NewsItem {
  title: string;
  link: string;
  description: string;
  pub_date: string;
  source: string;
}

interface ObjectInsight {
  text: string;
  political_balance_score: number;
  alarm: boolean;
  tier_group_kr: string;
  persona_id: string;
}


interface MemberAnalytics {
  composite_score: number;
  plenary_attendance_pct?: number;
  committee_attendance_pct?: number;
  bills_proposed?: number;
  bills_co_proposed?: number;
  floor_votes?: number;
  party_alignment_pct?: number;
  statements?: number;
  media_mentions_30d?: number;
}

interface PersonData {
  name?: string;
  party_id?: string;
  district_id?: string;
  district?: string;
  reelection?: string;
  committee?: string;
  profile_image_url?: string;
  analytics?: MemberAnalytics;
  [k: string]: unknown;
}


export default function ObjectDetailPage() {
  const params = useParams<{ type: string; id: string }>();
  const cls = params.type;
  const id = decodeURIComponent(params.id);

  const [data, setData] = useState<PersonData | null>(null);
  const [subgraph, setSubgraph] = useState<Subgraph | null>(null);
  const [depth, setDepth] = useState<1 | 2 | 3>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 연관 기사
  const [news, setNews] = useState<NewsItem[]>([]);
  // Sonnet 4.6 페르소나별 인사이트
  const [persona, setPersona] = useState<PersonaId>('editorial');
  const [insight, setInsight] = useState<ObjectInsight | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);

  const load = useCallback(async (d: 1 | 2 | 3) => {
    setLoading(true); setError(null);
    try {
      const r = await fetch(
        `${BASE}/api/objects/${cls}/${encodeURIComponent(id)}?depth=${d}`,
        { cache: 'no-store' },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const payload = await r.json();
      setData(payload.data as PersonData);
      setSubgraph(payload.subgraph ?? null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [cls, id]);

  useEffect(() => { void load(depth); }, [load, depth]);

  // 페르소나 로드 + 의원 뉴스 fetch
  useEffect(() => {
    setPersona(readPersonaIdSync() as PersonaId);
    if (cls === 'Person') {
      fetch(`${BASE}/api/members/${encodeURIComponent(id)}/news?limit=5`, { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : null)
        .then((d) => { if (d?.items) setNews(d.items); })
        .catch(() => setNews([]));
    }
  }, [cls, id]);

  async function generateInsight() {
    setInsightLoading(true);
    try {
      const r = await fetch(
        `${BASE}/api/objects/${cls}/${encodeURIComponent(id)}/insight?persona_id=${persona}`,
        { cache: 'no-store' },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setInsight(d as ObjectInsight);
    } catch (e) {
      setInsight({
        text: `(인사이트 생성 실패: ${e})`,
        political_balance_score: 0, alarm: true,
        tier_group_kr: '', persona_id: persona,
      });
    } finally {
      setInsightLoading(false);
    }
  }

  const isPerson = cls === 'Person';
  const photo = data?.profile_image_url;
  const name = data?.name as string | undefined;
  const party = (data?.party_id ?? data?.party) as string | undefined;
  const district = (data?.district_id ?? data?.district) as string | undefined;
  const reelection = data?.reelection as string | undefined;
  const committee = data?.committee as string | undefined;
  const analytics = data?.analytics;

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="mb-4 text-xs text-slate-500">
        <Link href="/objects" className="hover:text-slate-300">Object Explorer</Link>
        <span className="mx-2">/</span>
        <Link href={`/objects/${cls}`} className="hover:text-slate-300">{cls}</Link>
        <span className="mx-2">/</span>
        <span className="font-mono text-slate-400">{id}</span>
      </nav>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700/50 text-red-300 rounded text-sm">
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="text-center py-12 text-slate-400 text-sm animate-pulse">조회 중...</div>
      )}

      {/* Person Hero — 네이버 인물 페이지 패턴 */}
      {isPerson && data && (
        <header className="mb-6 p-6 bg-gradient-to-br from-slate-900/80 to-slate-900/40 border border-slate-800 rounded-lg">
          <div className="flex items-start gap-6">
            {/* 사진 */}
            <div className="shrink-0">
              {photo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={photo} alt={name ?? id}
                     className="w-32 h-32 rounded-lg object-cover bg-slate-800 border border-slate-700" />
              ) : (
                <div className="w-32 h-32 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-4xl text-slate-500">
                  {name ? name.charAt(0) : '?'}
                </div>
              )}
            </div>

            {/* 메타 */}
            <div className="flex-1 min-w-0">
              <h1 className="text-3xl font-bold text-white tracking-tight mb-1">{name ?? id}</h1>
              <div className="flex flex-wrap items-center gap-2 mb-3 text-sm">
                {party && (
                  <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">{party}</span>
                )}
                {district && <span className="text-slate-400">{district}</span>}
                {reelection && (
                  <span className="text-[11px] text-slate-500 uppercase tracking-wider">{reelection}</span>
                )}
              </div>
              {committee && (
                <div className="text-[11px] text-slate-400 mb-3">
                  <span className="uppercase tracking-wider text-slate-500 mr-2">소속 위원회</span>{committee}
                </div>
              )}

              {/* 종합 점수 progress bar */}
              {analytics && (
                <div className="mb-1">
                  <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                    <span className="uppercase tracking-wider">22대 종합 활동 점수</span>
                    <span className="font-mono text-amber-400">{analytics.composite_score.toFixed(1)} / 100</span>
                  </div>
                  <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-1.5 bg-gradient-to-r from-blue-500 to-amber-400 rounded-full"
                         style={{ width: `${Math.min(100, analytics.composite_score)}%` }} />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 9 메트릭 chips */}
          {analytics && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-2 mt-5 pt-5 border-t border-slate-800">
              <Metric label="본회의 출석" value={analytics.plenary_attendance_pct} suffix="%" />
              <Metric label="상임위 출석" value={analytics.committee_attendance_pct} suffix="%" />
              <Metric label="발의" value={analytics.bills_proposed} suffix="건" />
              <Metric label="공동발의" value={analytics.bills_co_proposed} suffix="건" />
              <Metric label="표결 참여" value={analytics.floor_votes} suffix="회" />
              <Metric label="정당 일치" value={analytics.party_alignment_pct} suffix="%" />
              <Metric label="발언" value={analytics.statements} suffix="회" />
              <Metric label="언론 30일" value={analytics.media_mentions_30d} suffix="회" />
              <Metric label="종합" value={analytics.composite_score} accent />
            </div>
          )}
        </header>
      )}

      {/* 비-Person 클래스 간단 hero */}
      {!isPerson && data && (
        <header className="mb-6 p-5 bg-slate-900/40 border border-slate-800 rounded-lg">
          <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">{cls}</div>
          <h1 className="text-2xl font-bold text-white tracking-tight mb-2">
            {(data.title as string) ?? (data.name as string) ?? id}
          </h1>
          <div className="text-xs font-mono text-slate-500">{id}</div>
        </header>
      )}

      {/* 온톨로지 관계 그래프 — 메인 영역 */}
      <section className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">온톨로지 관계 그래프</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">
              이 {isPerson ? '의원' : cls.toLowerCase()}을(를) 중심으로 의안·표결·소속·발언 등의 관계를 펼침.
              더블클릭으로 추가 1-hop 확장.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">depth</span>
            {[1, 2, 3].map((d) => (
              <button
                key={d}
                onClick={() => setDepth(d as 1 | 2 | 3)}
                className={
                  'text-xs px-2.5 py-1 rounded border transition-colors ' +
                  (depth === d
                    ? 'bg-blue-500/20 border-blue-500/50 text-blue-200 font-semibold'
                    : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500')
                }
                title={d === 1 ? 'in-memory 즉각' : `Neptune Cypher ${d}-hop`}
              >
                {d}-hop
              </button>
            ))}
          </div>
        </div>

        {subgraph ? (
          <CytoscapeView subgraph={subgraph} height={580} expandable={true} />
        ) : !loading && (
          <div className="border border-slate-800 rounded-lg p-6 text-center text-slate-500 text-sm">
            관계 데이터가 없습니다.
          </div>
        )}
      </section>

      {/* Sonnet 4.6 페르소나별 인사이트 */}
      <section className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">AI 인사이트</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Sonnet 4.6 + 페르소나별 어조·관심사 · 정치 중립성 가드 자동 적용
            </p>
          </div>
          <button
            onClick={generateInsight}
            disabled={insightLoading}
            className="text-xs px-3 py-1.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20 disabled:opacity-40"
          >
            {insightLoading ? '생성 중...' : `${persona} 페르소나로 분석`}
          </button>
        </div>
        {insight ? (
          <article className="bg-slate-900/40 border border-slate-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3 text-[10px] uppercase tracking-wider">
              <span className="text-slate-500">audience:</span>
              <span className="text-amber-300">{insight.tier_group_kr || TIER_GROUP_KR[(persona as PersonaId in TIER_GROUP_KR ? persona : 'editorial') as Tier]}</span>
              <span className="ml-auto text-slate-500">balance: </span>
              <span className={insight.alarm ? 'text-amber-400' : 'text-emerald-400'}>
                {insight.political_balance_score.toFixed(2)}
              </span>
              {insight.alarm && <span className="text-amber-400">⚠</span>}
            </div>
            <div className="chat-markdown text-sm text-slate-200">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{insight.text}</ReactMarkdown>
            </div>
          </article>
        ) : (
          <div className="border border-dashed border-slate-700 rounded-lg p-6 text-center text-slate-500 text-sm">
            상단 버튼을 눌러 페르소나별 AI 인사이트를 생성하세요.
            <br />
            <span className="text-[11px] text-slate-600 mt-1 block">
              페르소나는 사이드바에서 토글 가능 — 같은 객체에 대해 6가지 청중용 분석 비교
            </span>
          </div>
        )}
      </section>

      {/* 네이버 뉴스 — Person 클래스 한정 연관 기사 */}
      {isPerson && news.length > 0 && (
        <section className="mb-6">
          <h2 className="text-base font-bold text-white tracking-tight mb-1">연관 기사</h2>
          <p className="text-[11px] text-slate-500 mb-3">
            네이버 뉴스 검색 — {name} 의원 관련 최근 기사
          </p>
          <div className="space-y-2">
            {news.map((n, i) => (
              <a
                key={i}
                href={n.link}
                target="_blank"
                rel="noopener noreferrer"
                className="block p-3 bg-slate-900/40 border border-slate-800 rounded hover:border-slate-600 transition-colors"
              >
                <div className="text-sm font-semibold text-slate-100 mb-1">{n.title}</div>
                <div className="text-xs text-slate-400 leading-relaxed line-clamp-2 mb-1.5">
                  {n.description}
                </div>
                <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                  <span className="uppercase tracking-wider">{n.source}</span>
                  <span>·</span>
                  <span>{n.pub_date.slice(0, 16)}</span>
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      {/* 페이지 다른 객체 진입 hint */}
      <div className="text-[11px] text-slate-500 leading-relaxed">
        <strong className="text-slate-300 uppercase tracking-wider mr-1.5">Tip</strong>
        온톨로지 관계 그래프의 노드를 더블클릭하면 그 객체를 중심으로 추가 1-hop이 펼쳐집니다 (Neptune Cypher multi-hop).
        다른 의원을 보려면 <Link href="/members" className="text-blue-300 hover:underline">의원 디렉토리</Link> 또는 <Link href="/mindmap" className="text-blue-300 hover:underline">온톨로지 관계 그래프</Link> 탐색기로 이동.
      </div>
    </div>
  );
}


function Metric({
  label, value, suffix = '', accent = false,
}: {
  label: string;
  value?: number;
  suffix?: string;
  accent?: boolean;
}) {
  const display = value === undefined ? '—' :
    (suffix === '%' ? value.toFixed(1) : Math.round(value));
  return (
    <div className={`bg-slate-800/40 rounded p-2 border ${accent ? 'border-amber-500/40' : 'border-slate-800'}`}>
      <div className="text-[9px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`font-mono text-sm font-semibold ${accent ? 'text-amber-300' : 'text-slate-200'}`}>
        {display}
        {value !== undefined && <span className="text-[10px] text-slate-500 ml-0.5">{suffix}</span>}
      </div>
    </div>
  );
}
