'use client';

/**
 * CytoscapeView - 다단계 홉 온톨로지 관계 그래프 + 의원 사진 노드 + 다크 톤.
 *
 * UX 패턴 (open.assembly.go.kr searchVisualPage 참고):
 * - 처음에 root + 1-hop 표시 (concentric layout)
 * - leaf 노드 더블 클릭 → 그 노드를 root로 한 1-hop을 추가 fetch + merge (이미 있는 ID skip)
 * - 노드 단일 클릭 → closed neighborhood 강조 (외부 dim)
 * - 배경 클릭 → 강조 해제
 *
 * 노드 시각:
 * - Person: 의원 사진(profile_image_url) background-image + 이름 라벨
 *   (member_directory에 매칭된 노드만 사진. 그 외 SVG avatar placeholder)
 *   ADR-0004 정치 중립: 정당 색 미사용, 모든 의원 동일 border 색.
 * - 그 외 클래스(Bill/Vote/Article/Topic/...): 색상 원 + 라벨
 *
 * 의존성: cytoscape 3.31 + cytoscape-fcose 2.2
 */
import React, { useEffect, useRef, useState } from 'react';
import type { Core, ElementDefinition } from 'cytoscape';
import type { Subgraph, SubgraphNode, SubgraphEdge } from '../lib/api-client';

let _fcoseRegistered = false;

async function loadCytoscape(): Promise<(opts: object) => Core> {
  const mod = await import('cytoscape');
  const cytoscapeFn = ((mod as unknown as { default: (opts: object) => Core }).default
    ?? (mod as unknown as (opts: object) => Core)) as (opts: object) => Core;

  if (!_fcoseRegistered) {
    try {
      const fcoseMod = await import('cytoscape-fcose');
      const fcose = (fcoseMod as unknown as { default: unknown }).default ?? fcoseMod;
      const reg = (cytoscapeFn as unknown as { use: (ext: unknown) => void }).use;
      if (typeof reg === 'function') {
        reg.call(cytoscapeFn, fcose);
        _fcoseRegistered = true;
      }
    } catch { /* fallback cose */ }
  }
  return cytoscapeFn;
}


// 다크 노드 색상 (ADR-0004: 정당 색·이념 색 미사용)
const NODE_COLORS: Record<string, string> = {
  Bill:          '#3b82f6',
  Person:        '#a78bfa',
  Vote:          '#fb923c',
  Article:       '#34d399',
  Topic:         '#22d3ee',
  Statement:     '#f472b6',
  Committee:     '#10b981',
  Party:         '#c084fc',
  Agency:        '#fbbf24',
  Advertisement: '#fbbf24',
  Reader:        '#818cf8',
  default:       '#94a3b8',
};


const AVATAR_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
  + '<circle cx="32" cy="32" r="32" fill="#475569"/>'
  + '<circle cx="32" cy="24" r="10" fill="#cbd5e1"/>'
  + '<path d="M14 56 a18 18 0 0 1 36 0 z" fill="#cbd5e1"/>'
  + '</svg>',
);
const AVATAR_DATA_URI = `data:image/svg+xml;utf8,${AVATAR_SVG}`;


interface EdgeStyle { color: string; width: number; lineStyle: 'solid'|'dashed'|'dotted'; label: string }

const EDGE_STYLES: Record<string, EdgeStyle> = {
  PROPOSED:     { color: '#3b82f6', width: 3,   lineStyle: 'solid',  label: '발의' },
  CO_PROPOSED:  { color: '#3b82f6', width: 2,   lineStyle: 'dashed', label: '공동발의' },
  VOTED:        { color: '#fb923c', width: 3,   lineStyle: 'solid',  label: '표결' },
  VOTE_ON:      { color: '#64748b', width: 2,   lineStyle: 'solid',  label: '대상' },
  MEMBER_OF:    { color: '#10b981', width: 2,   lineStyle: 'dashed', label: '소속' },
  BELONGS_TO:   { color: '#a78bfa', width: 1.5, lineStyle: 'solid',  label: '소속 정당' },
  ABOUT:        { color: '#22d3ee', width: 2,   lineStyle: 'dotted', label: '관련 주제' },
  ASSIGNED_TO:  { color: '#10b981', width: 2,   lineStyle: 'dashed', label: '소관위' },
  AT:           { color: '#64748b', width: 1,   lineStyle: 'dashed', label: '회기' },
  MENTIONS:     { color: '#f472b6', width: 1.5, lineStyle: 'dotted', label: '언급' },
  REFERENCES:   { color: '#64748b', width: 1,   lineStyle: 'dotted', label: '참조' },
  READ:         { color: '#f472b6', width: 1.5, lineStyle: 'dotted', label: '독자 열람' },
  CANDIDATE:    { color: '#fbbf24', width: 2,   lineStyle: 'dashed', label: '광고 후보' },
  CHOSE:        { color: '#fbbf24', width: 3,   lineStyle: 'solid',  label: '광고 선정' },
  CONSIDERED:   { color: '#fbbf24', width: 1.5, lineStyle: 'dashed', label: '검토' },
  OVERSEES:     { color: '#fbbf24', width: 2,   lineStyle: 'solid',  label: '관할' },
  BY:           { color: '#94a3b8', width: 1,   lineStyle: 'solid',  label: '저자' },
  default:      { color: '#64748b', width: 1.5, lineStyle: 'solid',  label: '관계' },
};


/** 클래스명 → /api/objects/{type-slug} 매핑 (객체 expand fetch용) */
const CLASS_TO_TYPE_SLUG: Record<string, string> = {
  Bill: 'bill', Person: 'person', Vote: 'vote', Article: 'article',
  Topic: 'topic', Statement: 'statement', Committee: 'committee',
  Party: 'party', Agency: 'agency', Advertisement: 'advertisement',
  Reader: 'reader',
};


type NodeData = Record<string, unknown>;


export function CytoscapeView({
  subgraph,
  height = 500,
  expandable = true,
}: {
  subgraph: Subgraph;
  height?: number;
  expandable?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  // multi-hop: 추가 fetch한 노드/엣지 누적
  const [extra, setExtra] = useState<{ nodes: SubgraphNode[]; edges: SubgraphEdge[] }>({ nodes: [], edges: [] });
  const [expandingId, setExpandingId] = useState<string | null>(null);
  const [hopCount, setHopCount] = useState(1);

  // subgraph 변경 시 extra 리셋
  useEffect(() => {
    setExtra({ nodes: [], edges: [] });
    setHopCount(1);
  }, [subgraph.root_id]);

  async function expandNode(nodeId: string, nodeLabel: string, nodeData?: NodeData) {
    if (!expandable) return;
    const typeSlug = CLASS_TO_TYPE_SLUG[nodeLabel];
    if (!typeSlug) return;
    setExpandingId(nodeId);
    try {
      // dbltap = "더 깊이 보고 싶다" 시그널 → depth=2 (Neptune Cypher multi-hop traversal)
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/objects/${typeSlug}/${encodeURIComponent(nodeId)}?depth=2`,
        { cache: 'no-store' },
      );
      if (!resp.ok) return;
      const d = await resp.json();
      const sg = d.subgraph as Subgraph | null;
      if (!sg) return;
      const seen = new Set<string>([
        ...subgraph.nodes.map((n) => n.id),
        ...extra.nodes.map((n) => n.id),
      ]);
      const seenEdge = new Set<string>([
        ...subgraph.edges.map((e) => `${e.source}-${e.target}-${e.type}`),
        ...extra.edges.map((e) => `${e.source}-${e.target}-${e.type}`),
      ]);
      const newNodes = sg.nodes.filter((n) => !seen.has(n.id));
      const newEdges = sg.edges.filter((e) => !seenEdge.has(`${e.source}-${e.target}-${e.type}`));
      // 자기 자신은 추가 안 함 (이미 root)
      void nodeData;
      setExtra((prev) => ({
        nodes: [...prev.nodes, ...newNodes],
        edges: [...prev.edges, ...newEdges],
      }));
      setHopCount((h) => Math.max(h, 2));
    } finally {
      setExpandingId(null);
    }
  }

  useEffect(() => {
    let mounted = true;
    let cy: Core | null = null;

    (async () => {
      if (!containerRef.current) return;
      const cytoscape = await loadCytoscape();
      if (!mounted || !containerRef.current) return;

      const allNodes = [...subgraph.nodes, ...extra.nodes];
      const allEdges = [...subgraph.edges, ...extra.edges];

      // Compound 추론: MEMBER_OF
      const parentMap = new Map<string, string>();
      for (const e of allEdges) {
        if (e.type === 'MEMBER_OF') parentMap.set(e.source, e.target);
      }
      const parentIds = new Set(parentMap.values());

      const elements: ElementDefinition[] = [];
      for (const node of allNodes) {
        if (parentIds.has(node.id)) {
          elements.push({ data: { id: node.id, label: shortLabel(node), nodeType: node.label, isCompound: 1 } });
        }
      }
      for (const node of allNodes) {
        if (parentIds.has(node.id)) continue;
        const d = (node.data ?? {}) as NodeData;
        const photoUrl = typeof d.profile_image_url === 'string' ? d.profile_image_url : null;
        elements.push({
          data: {
            id: node.id,
            label: shortLabel(node),
            nodeType: node.label,
            parent: parentMap.get(node.id),
            isRoot: node.id === subgraph.root_id ? 1 : 0,
            photoUrl: photoUrl ?? (node.label === 'Person' ? AVATAR_DATA_URI : ''),
            hasPhoto: photoUrl ? 1 : 0,
          },
        });
      }
      allEdges.forEach((e, idx) => {
        if (e.type === 'MEMBER_OF' && parentMap.has(e.source)) return;
        const krLabel = (EDGE_STYLES[e.type] ?? EDGE_STYLES.default).label;
        elements.push({
          data: {
            id: `${e.source}-${e.target}-${idx}`,
            source: e.source, target: e.target,
            relation: e.type, label: krLabel,
          },
        });
      });

      cy = cytoscape({
        container: containerRef.current,
        elements,
        style: buildStyle(),
        layout: {
          name: _fcoseRegistered ? 'fcose' : 'cose',
          animate: false,
          padding: 40,
          nodeDimensionsIncludeLabels: true,
          randomize: false,
        } as object,
        wheelSensitivity: 0.25,
      });

      // 단일 클릭: 1-hop 강조
      cy.on('tap', 'node', (evt) => {
        const target = evt.target;
        const neighborhood = target.closedNeighborhood();
        cy?.elements().addClass('faded');
        neighborhood.removeClass('faded');
      });
      // 더블 클릭: multi-hop expand
      cy.on('dbltap', 'node', (evt) => {
        const target = evt.target;
        const nodeId = target.data('id');
        const nodeType = target.data('nodeType');
        if (nodeId && nodeType) {
          void expandNode(nodeId, nodeType);
        }
      });
      cy.on('tap', (evt) => {
        if (evt.target === cy) cy?.elements().removeClass('faded');
      });

      cyRef.current = cy;
    })();

    return () => { mounted = false; if (cy) cy.destroy(); };
  }, [subgraph, extra]);

  const totalNodes = subgraph.nodes.length + extra.nodes.length;
  const totalEdges = subgraph.edges.length + extra.edges.length;

  // 클래스별 노드 카운트 + 관계별 엣지 카운트
  const allNodes = [...subgraph.nodes, ...extra.nodes];
  const allEdges = [...subgraph.edges, ...extra.edges];
  const nodeClassCount: Record<string, number> = {};
  for (const n of allNodes) nodeClassCount[n.label] = (nodeClassCount[n.label] ?? 0) + 1;
  const edgeRelCount: Record<string, number> = {};
  for (const e of allEdges) edgeRelCount[e.type] = (edgeRelCount[e.type] ?? 0) + 1;

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-900 overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between text-xs">
        <span className="text-slate-300">
          🧠 온톨로지 관계 그래프 ({hopCount}-hop): <strong className="text-white">{subgraph.root_id}</strong>
        </span>
        <span className="text-slate-500">
          {totalNodes} 노드 · {totalEdges} 엣지
          {expandable && <span className="ml-2 text-amber-400/80">· 더블클릭 → 1-hop 확장</span>}
          {expandingId && <span className="ml-2 text-blue-400 animate-pulse">⏳</span>}
        </span>
      </div>
      {/* 통계 패널 — 클래스별 노드 + 관계별 엣지 분포 */}
      <div className="px-3 py-2 border-b border-slate-800 bg-slate-900/30 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px]">
        <div className="flex items-center gap-1.5">
          <span className="text-slate-500 font-semibold">노드:</span>
          {Object.entries(nodeClassCount).map(([cls, cnt]) => (
            <span key={cls} className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: NODE_COLORS[cls] ?? NODE_COLORS.default }} aria-hidden />
              <span className="text-slate-300">{cls}</span>
              <span className="font-mono text-slate-500">{cnt}</span>
            </span>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-slate-500 font-semibold">관계:</span>
          {Object.entries(edgeRelCount).map(([rel, cnt]) => {
            const s = EDGE_STYLES[rel] ?? EDGE_STYLES.default;
            return (
              <span key={rel} className="inline-flex items-center gap-1">
                <span className="inline-block w-3 h-0.5"
                      style={{ backgroundColor: s.color }} aria-hidden />
                <span className="text-slate-300">{s.label}</span>
                <span className="font-mono text-slate-500">{cnt}</span>
              </span>
            );
          })}
        </div>
      </div>
      <div ref={containerRef} style={{ width: '100%', height, background: '#0f172a' }} />
      <Legend />
    </div>
  );
}


function shortLabel(node: { id: string; label?: string; data?: NodeData }): string {
  const d = node.data ?? {};
  // summary_label 우선 (backend가 클래스별 사람-친화 라벨 합성).
  // 사용자 신고: Vote "V_PRC_..." + Article "art_synth_..." 같은 unique ID가
  // 온톨로지 관계 그래프에 그대로 보이는 가독성 issue.
  for (const k of ['summary_label', 'name', 'title', 'label']) {
    const v = d[k];
    if (typeof v === 'string' && v) {
      return v.length > 18 ? v.slice(0, 18) + '…' : v;
    }
  }
  return node.id.length > 14 ? node.id.slice(0, 14) + '…' : node.id;
}


function buildStyle() {
  // 클래스별 shape (시각적 차별화) — Person·Bill·Topic·Article·Vote·Committee 구분
  const SHAPE_BY_TYPE: Record<string, string> = {
    Person:     'ellipse',
    Bill:       'round-rectangle',
    Vote:       'octagon',
    Topic:      'hexagon',
    Article:    'round-diamond',
    Committee:  'round-rectangle',
    Party:      'tag',
    Statement:  'star',
    default:    'ellipse',
  };

  const baseStyles: Array<{ selector: string; style: Record<string, unknown> }> = [
    // ─── 기본 노드 ───
    {
      selector: 'node',
      style: {
        'background-color': (ele: { data: (k: string) => string }) =>
          NODE_COLORS[ele.data('nodeType')] ?? NODE_COLORS.default,
        shape: (ele: { data: (k: string) => string }) =>
          SHAPE_BY_TYPE[ele.data('nodeType')] ?? SHAPE_BY_TYPE.default,
        label: 'data(label)',
        color: '#e2e8f0',
        'font-size': 11,
        'font-weight': 600,
        'text-valign': 'center',
        'text-halign': 'center',
        'text-outline-color': '#020617',
        'text-outline-width': 2,
        width: 'mapData(isRoot, 0, 1, 50, 76)',
        height: 'mapData(isRoot, 0, 1, 50, 76)',
        'border-width': 'mapData(isRoot, 0, 1, 1, 4)',
        'border-color': (ele: { data: (k: string) => number }) =>
          ele.data('isRoot') === 1 ? '#fbbf24' : '#1e293b',
      },
    },
    // ─── Person 노드: 사진 background-image ───
    // bg-image-crossorigin: 'anonymous' 필수 — 국회 image (www.assembly.go.kr) 는
    // CORS `Allow-Origin: *` 응답하지만, Cytoscape 의 canvas 가 *crossorigin
    // attr 없는 외부 image* 를 draw 시 tainted → 이미지 render 안 됨. 명시 필요.
    {
      selector: 'node[nodeType = "Person"]',
      style: {
        'background-image': 'data(photoUrl)',
        'background-image-crossorigin': 'anonymous',
        'background-fit': 'cover',
        'background-clip': 'node',
        'background-color': '#1e293b',
        label: 'data(label)',
        'text-margin-y': 10,
        'text-valign': 'bottom',
        color: '#f1f5f9',
        'text-outline-color': '#020617',
        'text-outline-width': 2,
        'font-size': 10,
      },
    },
    // ─── Compound (Committee 그룹) ───
    {
      selector: 'node[isCompound = 1]',
      style: {
        'background-color': '#064e3b',
        'background-opacity': 0.3,
        'border-width': 2,
        'border-color': '#10b981',
        'border-style': 'dashed',
        'text-valign': 'top',
        'text-halign': 'center',
        'text-margin-y': -6,
        color: '#6ee7b7',
        'font-size': 12,
        'font-weight': 'bold' as unknown as number,
        'text-outline-width': 0,
        shape: 'round-rectangle',
        padding: 22 as unknown as number,
      },
    },
    // ─── Faded ───
    { selector: '.faded', style: { opacity: 0.15 } },
    // ─── 기본 엣지 ───
    {
      selector: 'edge',
      style: {
        width: EDGE_STYLES.default.width,
        'line-color': EDGE_STYLES.default.color,
        'target-arrow-color': EDGE_STYLES.default.color,
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': 8,
        color: '#94a3b8',
        'text-background-color': '#0f172a',
        'text-background-opacity': 0.85,
        'text-background-padding': 2,
      },
    },
  ];

  const edgeRelationStyles = Object.entries(EDGE_STYLES)
    .filter(([key]) => key !== 'default')
    .map(([relation, s]) => ({
      selector: `edge[relation = "${relation}"]`,
      style: {
        width: s.width,
        'line-color': s.color,
        'target-arrow-color': s.color,
        'line-style': s.lineStyle,
      },
    }));

  return [...baseStyles, ...edgeRelationStyles];
}


function Legend() {
  return (
    <div className="px-3 py-2 border-t border-slate-800 bg-slate-900/40 text-[10px] text-slate-400 space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-300">노드:</span>
        {Object.entries(NODE_COLORS)
          .filter(([k]) => k !== 'default')
          .map(([type, color]) => (
            <span key={type} className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} aria-hidden />
              {type}
            </span>
          ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-300">관계:</span>
        <Sample color="#3b82f6" label="PROPOSED" />
        <Sample color="#fb923c" label="VOTED" />
        <Sample color="#10b981" label="MEMBER_OF" style="dashed" />
        <Sample color="#22d3ee" label="ABOUT" style="dotted" />
        <Sample color="#f472b6" label="MENTIONS" style="dotted" />
      </div>
    </div>
  );
}


function Sample({ color, label, style = 'solid' }: { color: string; label: string; style?: string }) {
  const lineClass = style === 'dashed' ? 'border-t-2 border-dashed'
                  : style === 'dotted' ? 'border-t-2 border-dotted'
                  : '';
  return (
    <span className="inline-flex items-center gap-1">
      {style === 'solid'
        ? <span className="inline-block w-4 h-0.5" style={{ backgroundColor: color }} aria-hidden />
        : <span className={`inline-block w-4 h-0.5 ${lineClass}`} style={{ borderColor: color }} aria-hidden />
      }
      {label}
    </span>
  );
}
