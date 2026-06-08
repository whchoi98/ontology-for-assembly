'use client';

// 코드 지식 그래프 — web/public/codegraph/ 안의 graphify 결과 정적 자산을 임베드.
// 빌드: `graphify update . --force && cp graphify-out/* web/public/codegraph/`
// (AST-only, 빌드 시 LLM 호출 없음). 커뮤니티 한글 라벨만 Bedrock Sonnet 4.6로 오프라인 생성.
//
// gcc /codegraph 패턴 차용 — manifest stats, community labels/meta optional,
// fullscreen iframe, side panel community list. assembly 팔레트(slate) + AppShell
// (TopBar h-12 + max-w-7xl px-6 py-6)에 맞춰 inline 높이를 조정함.

import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, FileText, Code2, Maximize2, Minimize2, Tag } from 'lucide-react';

interface Manifest {
  total_nodes?: number;
  total_edges?: number;
  total_communities?: number;
  generated_at?: string;
  source_commit?: string;
  files_processed?: number;
  [k: string]: unknown;
}

type CommunityLabels = Record<string, string>;

type CommunityMeta = {
  label: string;
  description: string;
  key_concepts: string[];
  top_files: string[];
  node_count: number;
};

type CommunityMetaMap = Record<string, CommunityMeta>;

const STATIC_BASE = '/codegraph';

export default function CodeGraphPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  // inline 뷰가 default. 전체화면은 명시적 토글 (AppShell을 벗어나는 fixed inset-0).
  const [fullscreen, setFullscreen] = useState(false);
  const [communityLabels, setCommunityLabels] = useState<CommunityLabels | null>(null);
  const [communityMeta, setCommunityMeta] = useState<CommunityMetaMap | null>(null);
  const [communitySizes, setCommunitySizes] = useState<Record<string, number>>({});
  // 커뮤니티 패널 default-open — Sonnet 4.6 분석 결과(label/description/
  // key_concepts/대표파일)가 그래프 옆에 즉시 보임.
  const [showCommunityPanel, setShowCommunityPanel] = useState(true);

  useEffect(() => {
    fetch(`${STATIC_BASE}/manifest.json`, { cache: 'no-store' })
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((d) => setManifest(d as Manifest))
      .catch((e) => setManifestError(String(e)));

    fetch(`${STATIC_BASE}/community_labels.json`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setCommunityLabels(d as CommunityLabels); })
      .catch(() => { /* optional asset */ });

    fetch(`${STATIC_BASE}/community_meta.json`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setCommunityMeta(d as CommunityMetaMap); })
      .catch(() => { /* optional asset; falls back to labels-only mode */ });

    fetch(`${STATIC_BASE}/graph.json`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((g) => {
        if (!g?.nodes) return;
        const sizes: Record<string, number> = {};
        for (const n of g.nodes) {
          const c = String(n.community ?? '');
          if (c) sizes[c] = (sizes[c] ?? 0) + 1;
        }
        setCommunitySizes(sizes);
      })
      .catch(() => { /* graph.json optional */ });
  }, []);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen]);

  // graphify manifest schema is unversioned — handle both new (rollup) and
  // older (per-file {mtime,hash}) formats.
  const stats: Array<[string, string]> = [];
  if (manifest) {
    const nodes = (manifest.total_nodes as number) ?? (manifest.node_count as number);
    const edges = (manifest.total_edges as number) ?? (manifest.edge_count as number);
    const communities = (manifest.total_communities as number) ?? (manifest.community_count as number);
    const filesExplicit = (manifest.files_processed as number) ?? (manifest.file_count as number);
    if (nodes != null) stats.push(['노드', String(nodes)]);
    if (edges != null) stats.push(['엣지', String(edges)]);
    if (communities != null) stats.push(['커뮤니티', String(communities)]);
    if (filesExplicit != null) {
      stats.push(['파일', String(filesExplicit)]);
    } else {
      let n = 0;
      for (const v of Object.values(manifest)) {
        if (v && typeof v === 'object' && 'mtime' in (v as object)) n += 1;
      }
      if (n > 0) stats.push(['파일', String(n)]);
    }
    const commit = manifest.source_commit as string | undefined;
    if (commit) stats.push(['커밋', commit.slice(0, 8)]);
  }

  if (fullscreen) {
    return (
      <div className="fixed inset-0 z-50 bg-slate-950 flex flex-col">
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-700 bg-slate-900">
          <Code2 className="w-4 h-4 text-emerald-300" />
          <span className="text-xs font-semibold text-slate-100">코드 지식 그래프</span>
          {stats.length > 0 && (
            <span className="text-[10px] font-mono text-slate-400 ml-2">
              {stats.map(([k, v]) => `${k} ${v}`).join(' · ')}
            </span>
          )}
          {communityLabels && (
            <button
              type="button"
              onClick={() => setShowCommunityPanel((v) => !v)}
              className={[
                'ml-auto flex items-center gap-1.5 text-xs px-3 py-1 rounded-md border transition',
                showCommunityPanel
                  ? 'border-emerald-500 bg-emerald-500/15 text-emerald-100'
                  : 'border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300',
              ].join(' ')}
              title={`${Object.keys(communityLabels).length}개 커뮤니티 (Sonnet 4.6 분석)`}
            >
              <Tag className="w-3.5 h-3.5" /> 커뮤니티 ({Object.keys(communityLabels).length})
            </button>
          )}
          <a
            href={`${STATIC_BASE}/GRAPH_REPORT.md`}
            target="_blank"
            rel="noreferrer"
            className={`flex items-center gap-1.5 text-xs px-3 py-1 rounded-md border border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300 transition ${communityLabels ? '' : 'ml-auto'}`}
            title="GRAPH_REPORT.md"
          >
            <FileText className="w-3.5 h-3.5" /> 리포트
          </a>
          <button
            type="button"
            onClick={() => setFullscreen(false)}
            className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-md border border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300 transition"
            title="전체화면 해제 (ESC)"
          >
            <Minimize2 className="w-3.5 h-3.5" /> 해제 (ESC)
          </button>
        </div>
        <div className="flex-1 min-h-0 flex">
          <iframe
            title="graphify code graph (fullscreen)"
            src={`${STATIC_BASE}/graph.html`}
            className="flex-1 min-w-0"
            style={{ border: 0 }}
          />
          {showCommunityPanel && communityLabels && (
            <CommunityListPanel
              labels={communityLabels}
              meta={communityMeta}
              sizes={communitySizes}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] min-h-[600px]">
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Code2 className="w-5 h-5 text-emerald-300" />
          <h1 className="text-lg font-bold text-slate-50">코드 지식 그래프</h1>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-200">
            graphify
          </span>
        </div>

        {stats.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {stats.map(([k, v]) => (
              <span
                key={k}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-700 bg-slate-900 text-slate-300"
              >
                <span className="text-slate-500">{k}</span> <span className="text-slate-100">{v}</span>
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-1.5 ml-auto">
          {communityLabels && (
            <button
              type="button"
              onClick={() => setShowCommunityPanel((v) => !v)}
              className={[
                'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border transition',
                showCommunityPanel
                  ? 'border-emerald-500 bg-emerald-500/15 text-emerald-100'
                  : 'border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300',
              ].join(' ')}
              title={`${Object.keys(communityLabels).length}개 커뮤니티 라벨 (LLM 의미 분석)`}
            >
              <Tag className="w-3.5 h-3.5" /> 커뮤니티 ({Object.keys(communityLabels).length})
            </button>
          )}
          <button
            type="button"
            onClick={() => setFullscreen(true)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-emerald-500/50 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 transition font-semibold"
            title="페이지 안에서 전체화면 (ESC로 해제)"
          >
            <Maximize2 className="w-3.5 h-3.5" /> 전체화면
          </button>
          <a
            href={`${STATIC_BASE}/graph.html`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300 transition"
            title="새 탭에서 열기"
          >
            <ExternalLink className="w-3.5 h-3.5" /> 새 탭
          </a>
          <a
            href={`${STATIC_BASE}/GRAPH_REPORT.md`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300 transition"
            title="GRAPH_REPORT.md"
          >
            <FileText className="w-3.5 h-3.5" /> 리포트
          </a>
          <a
            href={`${STATIC_BASE}/graph.json`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300 transition"
            title="graph.json"
          >
            JSON
          </a>
        </div>
      </div>

      {manifestError && (
        <p className="text-[11px] text-rose-300 mb-2">manifest.json 로드 실패 — {manifestError}</p>
      )}

      <p className="text-[11px] text-slate-500 mb-2">
        이 프로젝트의 <em>코드베이스 자체</em>를 그래프로 — Python AST + TypeScript / TSX 파싱으로 추출한 클래스 / 함수 / import 관계.
        서드파티 <code className="text-slate-300">graphify</code> 스킬이 생성한 정적 자산을 그대로 임베드 — 빌드 시 LLM 호출 없음, 개인정보 / 시크릿 미포함.
        코드 변경 후 갱신: <code className="text-slate-300">bash scripts/refresh_codegraph.sh</code> → web 이미지 재배포.
      </p>

      <div className="flex-1 min-h-0 flex gap-3 overflow-hidden">
        <div className="flex-1 min-h-0 min-w-0 rounded-lg border border-slate-700 bg-slate-950 overflow-hidden">
          <iframe
            title="graphify code graph"
            src={`${STATIC_BASE}/graph.html`}
            className="w-full h-full block"
            style={{ border: 0 }}
          />
        </div>
        {showCommunityPanel && communityLabels && (
          <CommunityListPanel
            labels={communityLabels}
            meta={communityMeta}
            sizes={communitySizes}
          />
        )}
      </div>
    </div>
  );
}


function CommunityListPanel({
  labels, meta, sizes,
}: {
  labels: Record<string, string>;
  meta: CommunityMetaMap | null;
  sizes: Record<string, number>;
}) {
  const [filter, setFilter] = useState('');
  const [expandedCid, setExpandedCid] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const entries = Object.entries(labels).map(([cid, label]) => {
      const m = meta?.[cid];
      return {
        cid,
        label,
        size: m?.node_count ?? sizes[cid] ?? 0,
        description: m?.description ?? '',
        key_concepts: m?.key_concepts ?? [],
        top_files: m?.top_files ?? [],
      };
    });
    entries.sort((a, b) => b.size - a.size);
    if (!filter) return entries;
    const q = filter.toLowerCase();
    return entries.filter((e) =>
      e.label.toLowerCase().includes(q) ||
      e.cid.includes(q) ||
      e.description.toLowerCase().includes(q) ||
      e.key_concepts.some((c) => c.toLowerCase().includes(q)) ||
      e.top_files.some((f) => f.toLowerCase().includes(q)),
    );
  }, [labels, meta, sizes, filter]);

  return (
    <aside className="w-80 shrink-0 rounded-lg border border-slate-700 bg-slate-900 flex flex-col overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-700 flex items-center gap-2">
        <Tag className="w-3.5 h-3.5 text-emerald-300" />
        <span className="text-xs font-semibold text-slate-100">코드 커뮤니티</span>
        <span className="text-[10px] font-mono text-slate-400 ml-auto">
          {sorted.length}/{Object.keys(labels).length}
        </span>
      </div>
      <div className="px-3 py-2 border-b border-slate-700">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="라벨·설명·파일·개념 검색…"
          className="w-full text-xs bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-100 outline-none focus:border-emerald-500"
        />
      </div>
      <ul className="flex-1 overflow-y-auto text-xs divide-y divide-slate-700/50">
        {sorted.map((entry) => {
          const expanded = expandedCid === entry.cid;
          // 항상 카드 형태로 description/files를 노출 — expand는 부가 정보.
          // description이 없으면 첫 top_file을 자동 fallback 라인으로 사용.
          const fallbackHint = entry.top_files[0]
            ? entry.top_files[0].split('/').slice(-2).join('/')
            : '';
          return (
            <li key={entry.cid}>
              <button
                type="button"
                onClick={() => setExpandedCid(expanded ? null : entry.cid)}
                className="w-full text-left px-3 py-2 hover:bg-slate-800 transition block"
                title="클릭하여 전체 상세 정보 펼치기/접기"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-[10px] text-slate-500 shrink-0">
                    #{entry.cid}
                  </span>
                  <span className="text-slate-100 font-semibold flex-1 min-w-0 truncate">
                    {entry.label}
                  </span>
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 shrink-0">
                    {entry.size} 노드
                  </span>
                </div>
                {entry.description ? (
                  <p className="text-[11px] text-slate-300 leading-snug line-clamp-2 mb-1">
                    {entry.description}
                  </p>
                ) : fallbackHint ? (
                  <p className="text-[10px] font-mono text-slate-500 truncate" title={entry.top_files[0]}>
                    {fallbackHint}
                  </p>
                ) : null}
                {entry.key_concepts.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {entry.key_concepts.slice(0, 3).map((c) => (
                      <span
                        key={c}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-200 border border-emerald-500/30"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                )}
              </button>
              {expanded && entry.top_files.length > 0 && (
                <div className="px-3 pb-2.5 pt-1 bg-slate-800/40">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
                    대표 파일 ({entry.top_files.length})
                  </div>
                  <ul className="space-y-0.5 font-mono text-[10px]">
                    {entry.top_files.map((f) => (
                      <li key={f} className="text-slate-300 truncate" title={f}>
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
        {sorted.length === 0 && (
          <li className="px-3 py-4 text-center text-slate-500 text-[11px]">
            매칭되는 커뮤니티가 없습니다.
          </li>
        )}
      </ul>
      <div className="px-3 py-1.5 border-t border-slate-700 text-[10px] text-slate-500">
        {meta
          ? '라벨·설명·핵심 개념·대표 파일 — Bedrock Sonnet 4.6 자동 추출. 클릭하여 펼쳐보기.'
          : '라벨은 Bedrock Sonnet 4.6이 각 커뮤니티의 중심 노드를 분석해 자동 생성.'}
      </div>
    </aside>
  );
}
