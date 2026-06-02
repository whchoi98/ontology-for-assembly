'use client';

/**
 * /mindmap — 온톨로지 관계 그래프 landing page (다단계 홉 그래프 탐색기).
 *
 * 진입 흐름:
 *   1. 시작 클래스 선택 (의원·의안·표결·주제·기사 5개)
 *   2. root 객체 선택
 *      - 의원: 286명 카드 그리드 (composite_score 순)
 *      - 기타: instance list dropdown
 *   3. depth slider (1=in-memory 즉각 / 2-3=Neptune Cypher multi-hop)
 *   4. CytoscapeView로 온톨로지 관계 그래프 렌더링 + 더블클릭 expand-on-click
 *
 * 백엔드:
 *   - GET /api/members           의원 디렉토리 (286명 + 사진 + 메트릭)
 *   - GET /api/objects/{Class}   instance list
 *   - GET /api/objects/{Class}/{id}?depth=N  hybrid (in-memory or Neptune)
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CytoscapeView } from '../../components/CytoscapeView';
import type { Subgraph } from '../../lib/api-client';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';


type RootClass = 'Person' | 'Bill' | 'Vote' | 'Topic' | 'Article';

const CLASS_META: Record<RootClass, { kr: string; en: string; desc: string }> = {
  Person:  { kr: '의원', en: 'Person',  desc: '286명 — 협력·표결·소속 위원회' },
  Bill:    { kr: '의안', en: 'Bill',    desc: '발의자·공동발의·표결·카테고리' },
  Vote:    { kr: '표결', en: 'Vote',    desc: '의안·찬반·정당 분포' },
  Topic:   { kr: '주제', en: 'Topic',   desc: '의안·기사·발언 묶음' },
  Article: { kr: '기사', en: 'Article', desc: '참조 의원·의안·토픽' },
};


interface MemberInfo {
  assembly_id: string;
  name: string;
  party: string;
  district: string;
  profile_image_url: string;
  analytics: { composite_score: number };
}

interface InstanceListItem {
  [k: string]: unknown;
  source?: string;
}


export default function MindmapPage() {
  const router = useRouter();
  const [rootClass, setRootClass] = useState<RootClass>('Person');
  const [rootId, setRootId] = useState<string | null>(null);
  const [depth, setDepth] = useState<1 | 2 | 3>(1);
  const [subgraph, setSubgraph] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 클래스별 인스턴스 캐시
  const [members, setMembers] = useState<MemberInfo[]>([]);
  const [instances, setInstances] = useState<InstanceListItem[]>([]);
  const [search, setSearch] = useState('');

  // 의원 286명 로드
  useEffect(() => {
    if (rootClass !== 'Person') return;
    fetch(`${BASE}/api/members`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => setMembers(d.members))
      .catch(() => setMembers([]));
  }, [rootClass]);

  // 기타 클래스 인스턴스 로드 (lazy, dropdown용)
  useEffect(() => {
    if (rootClass === 'Person') return;
    fetch(`${BASE}/api/objects/${rootClass}?limit=100`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => setInstances(d.items ?? []))
      .catch(() => setInstances([]));
  }, [rootClass]);

  // root + depth 변경 시 subgraph fetch
  const loadSubgraph = useCallback(async (id: string, d: 1 | 2 | 3) => {
    setLoading(true); setError(null);
    try {
      const r = await fetch(
        `${BASE}/api/objects/${rootClass}/${encodeURIComponent(id)}?depth=${d}`,
        { cache: 'no-store' },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSubgraph(data.subgraph ?? { root_id: id, nodes: [{ id, label: rootClass, data: data.data }], edges: [] });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [rootClass]);

  function pickRoot(id: string) {
    // Person 클래스: 네이버 인물 페이지 패턴의 상세 페이지로 routing
    // (hero + 9 메트릭 + 큰 온톨로지 관계 그래프 + AI 인사이트 + 연관 기사)
    if (rootClass === 'Person') {
      router.push(`/objects/Person/${encodeURIComponent(id)}`);
      return;
    }
    // 기타 클래스: 같은 페이지 안에서 root 변경 + 온톨로지 관계 그래프 펼침
    setRootId(id);
    void loadSubgraph(id, depth);
  }

  function changeDepth(d: 1 | 2 | 3) {
    setDepth(d);
    if (rootId) void loadSubgraph(rootId, d);
  }

  function changeClass(c: RootClass) {
    setRootClass(c);
    setRootId(null);
    setSubgraph(null);
    setSearch('');
  }

  // 의원 필터 + 정렬
  const filteredMembers = members
    .filter((m) => !search || m.name.includes(search) || m.party.includes(search) || m.district.includes(search))
    .sort((a, b) => b.analytics.composite_score - a.analytics.composite_score);

  // 기타 클래스의 ID/label 추출 — 클래스별 *우선순위*로 ID 필드 선택.
  // 이전 버그: Vote는 `vote_id`와 `bill_id`를 둘 다 가지므로 `?? bill_id` 순서면
  // bill_id가 먼저 매치 → Vote class에 Bill ID로 호출 → 404.
  const idFieldByClass: Record<RootClass, string[]> = {
    Person:  ['assembly_id', 'id'],
    Bill:    ['bill_id', 'id'],
    Vote:    ['vote_id', 'id'],
    Topic:   ['topic_id', 'id'],
    Article: ['article_id', 'id'],
  };
  const instanceItems = instances.map((it) => {
    const fields = idFieldByClass[rootClass] ?? ['id'];
    let id = '';
    for (const f of fields) {
      const v = it[f];
      if (typeof v === 'string' && v) { id = v; break; }
    }
    // backend가 합성한 summary_label 우선 (예: Vote → "2026-04-15 가결")
    const label = String(it.summary_label ?? it.title ?? it.name ?? it.label ?? id);
    // 검색 대상 텍스트 — title/name/category/content/topic_ids/referenced_person_ids 등
    // 모두 join → free-text 키워드 매칭 가능 (주제·내용·의원 등).
    const searchableParts: string[] = [label, id];
    for (const f of ['title', 'name', 'category', 'content', 'summary_text', 'status', 'date', 'result']) {
      const v = it[f];
      if (typeof v === 'string') searchableParts.push(v);
    }
    for (const f of ['topic_ids', 'referenced_person_ids', 'referenced_bill_ids']) {
      const v = it[f];
      if (Array.isArray(v)) searchableParts.push(v.join(' '));
    }
    return {
      id, label,
      data: it,
      searchable: searchableParts.join(' ').toLowerCase(),
    };
  }).filter((x) => x.id);

  // 사용자 free-text search로 필터 + 20개 cap
  const filteredInstances = instanceItems.filter(
    (it) => !search || it.searchable.includes(search.toLowerCase()),
  ).slice(0, 20);

  return (
    <div>
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-xs font-mono text-slate-500">/mindmap</span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 font-medium border border-blue-500/30">
            온톨로지 온톨로지 관계 그래프
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 font-medium border border-amber-500/30">
            다단계 홉
          </span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-1 tracking-tight">온톨로지 관계 그래프 탐색</h1>
        <p className="text-sm text-slate-400">
          의원·의안·표결·주제·기사를 시작점으로 1-3 홉 관계 그래프를 펼쳐 탐색.
          depth=1은 즉각 응답(in-memory), depth ≥ 2는 Neptune Cypher multi-hop traversal.
          노드 더블클릭 → 그 노드 중심으로 추가 확장.
        </p>
      </header>

      {/* Step 1: 시작 클래스 picker */}
      <section className="mb-5">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
          1. 시작 객체 유형
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {(Object.keys(CLASS_META) as RootClass[]).map((c) => {
            const meta = CLASS_META[c];
            const active = rootClass === c;
            return (
              <button
                key={c}
                onClick={() => changeClass(c)}
                className={
                  'p-3 rounded-lg border text-left transition-colors ' +
                  (active
                    ? 'bg-blue-500/15 border-blue-500/50 text-blue-200'
                    : 'bg-slate-900/40 border-slate-800 text-slate-300 hover:border-slate-600')
                }
              >
                <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">{meta.en}</div>
                <div className="font-semibold text-base">{meta.kr}</div>
                <div className="text-[10px] text-slate-500 mt-1 leading-snug">{meta.desc}</div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Step 2: root id picker */}
      {!rootId && (
        <section className="mb-5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
            2. {CLASS_META[rootClass].kr} 선택
          </div>

          {rootClass === 'Person' ? (
            <>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="이름·정당·지역구 검색..."
                className="w-full mb-3 px-3 py-2 bg-slate-900 border border-slate-700 rounded text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
              />
              <div className="text-xs text-slate-500 mb-2">
                {filteredMembers.length}명 (composite_score 순)
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 max-h-96 overflow-y-auto pr-1">
                {filteredMembers.slice(0, 60).map((m) => (
                  <button
                    key={m.assembly_id}
                    onClick={() => pickRoot(m.assembly_id)}
                    className="p-2 rounded bg-slate-900/40 border border-slate-800 hover:border-blue-500/50 text-left transition-colors group"
                  >
                    <div className="flex items-center gap-2">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={m.profile_image_url} alt={m.name}
                           className="w-10 h-10 rounded-full object-cover bg-slate-800"
                           onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.3'; }} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-slate-200 truncate group-hover:text-white">{m.name}</div>
                        <div className="text-[9px] text-slate-500 truncate">{m.party}</div>
                        <div className="text-[9px] text-amber-400/80">{m.analytics.composite_score.toFixed(1)}</div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`${CLASS_META[rootClass].kr} 검색 — 주제·내용·의원·날짜·상태 등 키워드`}
                className="w-full mb-3 px-3 py-2 bg-slate-900 border border-slate-700 rounded text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
              />
              <div className="text-xs text-slate-500 mb-2">
                {filteredInstances.length} / {instanceItems.length}개 인스턴스
                {search && <span className="ml-1 text-amber-400">· 검색 결과</span>}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-96 overflow-y-auto pr-1">
                {filteredInstances.map((it) => (
                  <button
                    key={it.id}
                    onClick={() => pickRoot(it.id)}
                    className="p-2 rounded bg-slate-900/40 border border-slate-800 hover:border-blue-500/50 text-left transition-colors"
                  >
                    {/* 라벨 (가독성 우선 — line-clamp 제거, 줄바꿈 허용) */}
                    <div className="text-xs font-semibold text-slate-100 leading-snug break-words" title={it.label}>
                      {it.label || '(라벨 없음)'}
                    </div>
                    {/* 클래스별 메타 정보 (safe access — it.data 없으면 skip) */}
                    {rootClass === 'Bill' && typeof it.data?.category === 'string' && it.data.category && (
                      <div className="mt-1 text-[10px] text-cyan-300 truncate">
                        {it.data.category}{typeof it.data.status === 'string' && it.data.status ? ` · ${it.data.status}` : ''}
                      </div>
                    )}
                    {rootClass === 'Vote' && typeof it.data?.result === 'string' && (
                      <div className="mt-1 text-[10px] text-amber-300">
                        결과: {it.data.result === 'passed' ? '가결' : it.data.result === 'rejected' ? '부결' : String(it.data.result)}
                        {typeof it.data?.attendance_count === 'number' ? ` · 참석 ${it.data.attendance_count}명` : ''}
                      </div>
                    )}
                    {rootClass === 'Topic' && typeof it.data?.category === 'string' && it.data.category && (
                      <div className="mt-1 text-[10px] text-cyan-300">
                        분류: {it.data.category}
                      </div>
                    )}
                    {rootClass === 'Article' && Array.isArray(it.data?.topic_ids) && (it.data.topic_ids as string[]).length > 0 && (
                      <div className="mt-1 text-[10px] text-emerald-300 truncate">
                        토픽: {(it.data.topic_ids as string[]).slice(0, 2).join(', ')}
                      </div>
                    )}
                    <div className="mt-1 text-[9px] font-mono text-slate-500 truncate">{it.id}</div>
                  </button>
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {/* Step 3: depth slider + 온톨로지 관계 그래프 */}
      {rootId && (
        <section>
          <div className="flex items-center justify-between mb-3 p-3 bg-slate-900/40 border border-slate-800 rounded-lg">
            <div className="flex items-center gap-3">
              <button
                onClick={() => { setRootId(null); setSubgraph(null); }}
                className="text-xs text-slate-400 hover:text-white"
                title="다른 root 선택"
              >
                ← 다시 선택
              </button>
              <span className="text-sm text-slate-200">
                <span className="text-amber-400 font-semibold">{CLASS_META[rootClass].kr}</span>
                <span className="ml-2 text-slate-200">
                  {instanceItems.find((it) => it.id === rootId)?.label ?? ''}
                </span>
                <span className="font-mono text-[10px] text-slate-600 ml-2">{rootId}</span>
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-slate-500">depth:</span>
              {[1, 2, 3].map((d) => (
                <button
                  key={d}
                  onClick={() => changeDepth(d as 1 | 2 | 3)}
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

          {error && (
            <div className="mb-3 p-3 bg-red-900/30 border border-red-700/50 text-red-300 rounded text-sm">
              {error}
            </div>
          )}

          {loading && (
            <div className="text-center py-8 text-slate-400 text-sm animate-pulse tracking-wider">
              {depth === 1 ? 'in-memory subgraph' : `Neptune ${depth}-hop traversal`} 조회 중...
            </div>
          )}

          {!loading && subgraph && (
            <CytoscapeView subgraph={subgraph} height={600} expandable={true} />
          )}

          <div className="mt-3 text-[11px] text-slate-500 leading-relaxed">
            <strong className="text-slate-300 uppercase text-[10px] tracking-wider mr-1.5">Tip</strong>
            노드를 한 번 클릭하면 1-hop 이웃 강조, 더블클릭하면 그 노드를 중심으로 추가 1-hop 확장 (depth=2 Neptune query).
            depth slider로 처음부터 multi-hop 가능.
          </div>
        </section>
      )}
    </div>
  );
}
