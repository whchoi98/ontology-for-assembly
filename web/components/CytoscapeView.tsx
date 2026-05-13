'use client';

/**
 * CytoscapeView - 1-hop subgraph 시각화 (Phase 5 Track 5-1).
 *
 * 입력: Subgraph (root_id, nodes, edges) - api-client.ts
 * 출력: Cytoscape force-directed 그래프
 *
 * 노드 타입별 색상 (ADR-0004: 정치 중립 - 정당 색 미사용):
 *   Bill        파랑   #2563eb
 *   Person      자주   #7c3aed
 *   Vote        주황   #ea580c
 *   Article     녹색   #16a34a
 *   Topic       청록   #0891b2
 *   Statement   분홍   #ec4899
 *   기타        회색   #6b7280
 */
import React, { useEffect, useRef } from 'react';
import type { Core, ElementDefinition } from 'cytoscape';
import type { Subgraph } from '../lib/api-client';

// SSR safety: cytoscape는 client에서만 동적 import.
async function loadCytoscape(): Promise<(opts: object) => Core> {
  const mod = await import('cytoscape');
  return (mod as unknown as { default: (opts: object) => Core }).default
    ?? (mod as unknown as (opts: object) => Core);
}

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
  default: '#6b7280',
};


export function CytoscapeView({ subgraph, height = 360 }: { subgraph: Subgraph; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;
    let cy: Core | null = null;

    (async () => {
      if (!containerRef.current) return;
      const cytoscape = await loadCytoscape();
      if (!mounted || !containerRef.current) return;

      const elements: ElementDefinition[] = [
        ...subgraph.nodes.map((n) => ({
          data: {
            id: n.id,
            label: shortLabel(n),
            nodeType: n.label,
            isRoot: n.id === subgraph.root_id ? 1 : 0,
          },
        })),
        ...subgraph.edges.map((e, idx) => ({
          data: {
            id: `${e.source}-${e.target}-${idx}`,
            source: e.source,
            target: e.target,
            label: e.type,
          },
        })),
      ];

      cy = cytoscape({
        container: containerRef.current,
        elements,
        style: [
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
          {
            selector: 'edge',
            style: {
              width: 1.5,
              'line-color': '#9ca3af',
              'target-arrow-color': '#9ca3af',
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
        ],
        layout: {
          name: 'cose',
          animate: false,
          padding: 30,
          nodeDimensionsIncludeLabels: true,
        },
        wheelSensitivity: 0.25,
      });
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
          {subgraph.nodes.length} 노드 · {subgraph.edges.length} 엣지
        </span>
      </div>
      <div ref={containerRef} style={{ width: '100%', height }} />
      <Legend />
    </div>
  );
}


function shortLabel(node: { id: string; data?: Record<string, unknown> }): string {
  const d = node.data ?? {};
  const candidates = ['title', 'name', 'label'];
  for (const k of candidates) {
    const v = d[k];
    if (typeof v === 'string' && v) {
      return v.length > 12 ? v.slice(0, 12) + '…' : v;
    }
  }
  return node.id.length > 10 ? node.id.slice(0, 10) + '…' : node.id;
}


function Legend() {
  const entries = Object.entries(NODE_COLORS).filter(([k]) => k !== 'default');
  return (
    <div className="px-3 py-2 border-t border-gray-200 bg-gray-50 flex flex-wrap gap-2 text-[10px] text-gray-600">
      {entries.map(([type, color]) => (
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
  );
}
