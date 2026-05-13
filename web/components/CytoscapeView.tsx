'use client';

/**
 * CytoscapeView - 고급 1-hop subgraph 시각화 (Phase 5 Track 5-7).
 *
 * 4 패턴 모두 적용:
 * 1. 이미지 노드 — Person은 placeholder 아바타 (ADR-0004: 모든 의원 동일, 정파 중립)
 * 2. [relation="..."] 셀렉터 — 엣지 타입별 색상·두께·점선
 * 3. fcose + compound — Committee가 등장하면 자동으로 그룹 박스 (정당 그룹화는 회피)
 * 4. 1-hop 이웃 강조 — 노드 클릭 시 이웃 외 노드 dim, 배경 클릭 reset
 *
 * 의존성:
 * - cytoscape 3.31 + cytoscape-fcose 2.2
 *
 * 노드 타입 색상 (ADR-0004: 정당 색·이념 색 미사용):
 *   Bill 파랑 / Person 자주 / Vote 주황 / Article 녹색 / Topic 청록
 *   Statement 분홍 / Committee 녹색 / Party 자주 / Agency 노랑
 */
import React, { useEffect, useRef } from 'react';
import type { Core, ElementDefinition } from 'cytoscape';
import type { Subgraph } from '../lib/api-client';

// fcose extension은 client에서만 register.
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
      }
      _fcoseRegistered = true;
    } catch {
      // fcose 로드 실패 시 cose로 fallback.
    }
  }
  return cytoscapeFn;
}

// 노드 타입별 색상 (정당 색 미사용).
const NODE_COLORS: Record<string, string> = {
  Bill: '#2563eb',
  Person: '#7c3aed',
  Vote: '#ea580c',
  Article: '#16a34a',
  Topic: '#0891b2',
  Statement: '#ec4899',
  Committee: '#059669',
  Party: '#9333ea',
  Agency: '#d97706',
  Advertisement: '#f59e0b',
  Reader: '#6366f1',
  default: '#6b7280',
};

// Placeholder 아바타 (data URI SVG, base64 인코딩) - 모든 Person 노드 동일.
// ADR-0004 정치 중립성 - 실 인물 사진 미사용.
const AVATAR_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
  + '<circle cx="32" cy="32" r="32" fill="#7c3aed"/>'
  + '<circle cx="32" cy="24" r="10" fill="white"/>'
  + '<path d="M14 56 a18 18 0 0 1 36 0 z" fill="white"/>'
  + '</svg>',
);
const AVATAR_DATA_URI = `data:image/svg+xml;utf8,${AVATAR_SVG}`;

// 엣지 관계별 스타일.
interface EdgeStyle {
  color: string;
  width: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
}

const EDGE_STYLES: Record<string, EdgeStyle> = {
  PROPOSED: { color: '#2563eb', width: 3, lineStyle: 'solid' },
  CO_PROPOSED: { color: '#2563eb', width: 2, lineStyle: 'dashed' },
  VOTED: { color: '#ea580c', width: 3, lineStyle: 'solid' },
  VOTE_ON: { color: '#9ca3af', width: 2, lineStyle: 'solid' },
  MEMBER_OF: { color: '#16a34a', width: 2, lineStyle: 'dashed' },
  BELONGS_TO: { color: '#7c3aed', width: 1.5, lineStyle: 'solid' },
  ABOUT: { color: '#0891b2', width: 2, lineStyle: 'dotted' },
  AT: { color: '#9ca3af', width: 1, lineStyle: 'dashed' },
  MENTIONS: { color: '#ec4899', width: 1.5, lineStyle: 'dotted' },
  REFERENCES: { color: '#9ca3af', width: 1, lineStyle: 'dotted' },
  READ: { color: '#ec4899', width: 1.5, lineStyle: 'dotted' },
  CANDIDATE: { color: '#d97706', width: 2, lineStyle: 'dashed' },
  CHOSE: { color: '#d97706', width: 3, lineStyle: 'solid' },
  CONSIDERED: { color: '#d97706', width: 1.5, lineStyle: 'dashed' },
  OVERSEES: { color: '#d97706', width: 2, lineStyle: 'solid' },
  BY: { color: '#6b7280', width: 1, lineStyle: 'solid' },
  default: { color: '#9ca3af', width: 1.5, lineStyle: 'solid' },
};


export function CytoscapeView({ subgraph, height = 400 }: { subgraph: Subgraph; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    let mounted = true;
    let cy: Core | null = null;

    (async () => {
      if (!containerRef.current) return;
      const cytoscape = await loadCytoscape();
      if (!mounted || !containerRef.current) return;

      // Compound 추론: MEMBER_OF 엣지가 있으면 source(Person) → target(Committee) parent 관계로.
      const parentMap = new Map<string, string>();
      for (const e of subgraph.edges) {
        if (e.type === 'MEMBER_OF') parentMap.set(e.source, e.target);
      }
      const parentIds = new Set(parentMap.values());

      const elements: ElementDefinition[] = [];

      // Compound 부모 노드 먼저 (예: Committee).
      for (const node of subgraph.nodes) {
        if (parentIds.has(node.id)) {
          elements.push({
            data: {
              id: node.id,
              label: shortLabel(node),
              nodeType: node.label,
              isCompound: 1,
            },
          });
        }
      }
      // 자식·일반 노드.
      for (const node of subgraph.nodes) {
        if (parentIds.has(node.id)) continue; // 이미 compound로 추가됨
        elements.push({
          data: {
            id: node.id,
            label: shortLabel(node),
            nodeType: node.label,
            parent: parentMap.get(node.id),
            isRoot: node.id === subgraph.root_id ? 1 : 0,
          },
        });
      }
      // 엣지 (MEMBER_OF는 compound 계층으로 표현되므로 명시 엣지 생략).
      subgraph.edges.forEach((e, idx) => {
        if (e.type === 'MEMBER_OF' && parentMap.has(e.source)) return;
        elements.push({
          data: {
            id: `${e.source}-${e.target}-${idx}`,
            source: e.source,
            target: e.target,
            relation: e.type,
            label: e.type,
          },
        });
      });

      const style = buildStyle();

      cy = cytoscape({
        container: containerRef.current,
        elements,
        style,
        layout: {
          name: _fcoseRegistered ? 'fcose' : 'cose',
          animate: false,
          padding: 30,
          nodeDimensionsIncludeLabels: true,
          randomize: false,
        },
        wheelSensitivity: 0.25,
      });

      // ─── 1-hop 이웃 강조 인터랙션 ──────────────────────────────────────
      cy.on('tap', 'node', (evt) => {
        const target = evt.target;
        const neighborhood = target.closedNeighborhood();
        cy?.elements().addClass('faded');
        neighborhood.removeClass('faded');
      });
      cy.on('tap', (evt) => {
        if (evt.target === cy) {
          cy?.elements().removeClass('faded');
        }
      });

      cyRef.current = cy;
    })();

    return () => {
      mounted = false;
      if (cy) cy.destroy();
    };
  }, [subgraph]);

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-200 bg-gray-50 flex items-center justify-between text-xs">
        <span className="text-gray-700">
          1-hop subgraph: <strong>{subgraph.root_id}</strong>
        </span>
        <span className="text-gray-500">
          {subgraph.nodes.length} 노드 · {subgraph.edges.length} 엣지 · <em>노드 클릭 → 이웃 강조</em>
        </span>
      </div>
      <div ref={containerRef} style={{ width: '100%', height }} />
      <Legend />
    </div>
  );
}


function shortLabel(node: { id: string; data?: Record<string, unknown> }): string {
  const d = node.data ?? {};
  for (const k of ['title', 'name', 'label']) {
    const v = d[k];
    if (typeof v === 'string' && v) {
      return v.length > 14 ? v.slice(0, 14) + '…' : v;
    }
  }
  return node.id.length > 12 ? node.id.slice(0, 12) + '…' : node.id;
}


function buildStyle() {
  // 노드 + 엣지 + 상태(faded·compound) 스타일을 동적 구성.
  const baseStyles: Array<{ selector: string; style: Record<string, unknown> }> = [
    // ─── 기본 노드 (색상 원) ───────────────────────────────────────────────
    {
      selector: 'node',
      style: {
        'background-color': (ele: { data: (k: string) => string }) =>
          NODE_COLORS[ele.data('nodeType')] ?? NODE_COLORS.default,
        label: 'data(label)',
        color: '#ffffff',
        'font-size': 10,
        'text-valign': 'center',
        'text-halign': 'center',
        'text-outline-color': '#111827',
        'text-outline-width': 0.5,
        width: 'mapData(isRoot, 0, 1, 38, 56)',
        height: 'mapData(isRoot, 0, 1, 38, 56)',
        'border-width': 'mapData(isRoot, 0, 1, 1, 3)',
        'border-color': '#1f2937',
      },
    },
    // ─── Person 노드: placeholder 아바타 background-image ────────────────
    {
      selector: 'node[nodeType = "Person"]',
      style: {
        'background-image': `url("${AVATAR_DATA_URI}")`,
        'background-fit': 'cover',
        'background-clip': 'node',
        'background-color': '#ffffff',
        label: 'data(label)',
        'text-margin-y': 8,
        'text-valign': 'bottom',
        color: '#1f2937',
        'text-outline-color': '#ffffff',
        'text-outline-width': 2,
        'font-size': 9,
      },
    },
    // ─── Compound 노드 (Committee 그룹 박스) ─────────────────────────────
    {
      selector: 'node[isCompound = 1]',
      style: {
        'background-color': '#f0fdf4',
        'background-opacity': 0.5,
        'border-width': 2,
        'border-color': '#16a34a',
        'border-style': 'dashed',
        'text-valign': 'top',
        'text-halign': 'center',
        'text-margin-y': -5,
        color: '#15803d',
        'font-size': 11,
        'font-weight': 'bold' as unknown as number,
        'text-outline-width': 0,
        shape: 'round-rectangle',
        padding: 18 as unknown as number,
      },
    },
    // ─── Faded 상태 (1-hop 강조 시 외부 노드) ────────────────────────────
    {
      selector: '.faded',
      style: {
        opacity: 0.2,
      },
    },
    // ─── 기본 엣지 ───────────────────────────────────────────────────────
    {
      selector: 'edge',
      style: {
        width: EDGE_STYLES.default.width,
        'line-color': EDGE_STYLES.default.color,
        'target-arrow-color': EDGE_STYLES.default.color,
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': 9,
        color: '#374151',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.85,
        'text-background-padding': 1,
      },
    },
  ];

  // 엣지 관계별 셀렉터 (Track 5-7 핵심).
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
    <div className="px-3 py-2 border-t border-gray-200 bg-gray-50 text-[10px] text-gray-600 space-y-1">
      <div className="flex flex-wrap gap-2">
        <span className="font-semibold text-gray-700">노드:</span>
        {Object.entries(NODE_COLORS)
          .filter(([k]) => k !== 'default')
          .map(([type, color]) => (
            <span key={type} className="inline-flex items-center gap-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: color }}
                aria-hidden
              />
              {type}
            </span>
          ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <span className="font-semibold text-gray-700">관계:</span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-4 h-0.5" style={{ backgroundColor: '#2563eb' }} aria-hidden />
          PROPOSED
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 border-t-2 border-dashed" style={{ borderColor: '#16a34a' }} aria-hidden />
          MEMBER_OF
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 border-t-2 border-dotted" style={{ borderColor: '#0891b2' }} aria-hidden />
          ABOUT
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-4 h-0.5" style={{ backgroundColor: '#ea580c' }} aria-hidden />
          VOTED
        </span>
      </div>
    </div>
  );
}
