'use client';

/**
 * Object Explorer - 클래스별 인스턴스 리스트 (Phase 5 Track 5-6).
 *
 * URL: /objects/{type}  예: /objects/Bill
 *
 * 인스턴스 리스트 + 페이징 + 단일 객체 디테일 인라인.
 */
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { CytoscapeView } from '../../../components/CytoscapeView';
import { DataSourceBadge } from '../../../components/DataSourceBadge';

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface ListResponse {
  type: string;
  total: number;
  offset: number;
  limit: number;
  items: Array<Record<string, unknown>>;
  display: { id?: string; label?: string; subtitle?: string };
  implemented: boolean;
}


export default function ClassListPage({ params }: { params: { type: string } }) {
  const type = decodeURIComponent(params.type);
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetch(`${PUBLIC_BASE}/api/objects/${type}?limit=20`, { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: ListResponse) => mounted && setData(d))
      .catch((e) => mounted && setError((e as Error).message))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [type]);

  async function viewDetail(id: string) {
    setSelectedId(id);
    setDetailData(null);
    try {
      const r = await fetch(`${PUBLIC_BASE}/api/objects/${type}/${encodeURIComponent(id)}`,
                            { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setDetailData(d);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <header className="mb-4">
        <Link href="/objects" className="text-xs text-blue-600 hover:underline">
          ← Object Explorer
        </Link>
        <h1 className="text-2xl font-bold mt-1">{type}</h1>
        {data && (
          <p className="text-sm text-slate-300 mt-1">
            <strong>{data.total}</strong> 인스턴스 · 페이지 {data.offset / data.limit + 1}
          </p>
        )}
      </header>

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {loading && <p className="text-slate-400">로딩 중…</p>}

      {data && !data.implemented && (
        <div className="border border-amber-400/30 bg-amber-500/10 text-amber-200 rounded-md p-3 text-sm mb-4">
          이 클래스는 dispatcher 미등록 - 후속 phase에서 데이터 연결 예정.
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-2">
            {data.items.map((item, idx) => {
              const idField = data.display.id ?? 'id';
              const labelField = data.display.label ?? idField;
              const subtitleField = data.display.subtitle;
              const id = String(item[idField] ?? `idx-${idx}`);
              const label = String(item[labelField] ?? id);
              const subtitle = subtitleField ? String(item[subtitleField] ?? '') : '';
              const source = String(item.source ?? 'real');
              const active = selectedId === id;
              return (
                <button
                  key={id}
                  onClick={() => viewDetail(id)}
                  className={
                    'w-full text-left border rounded-md p-3 transition ' +
                    (active
                      ? 'border-blue-400 bg-blue-500/15'
                      : 'border-slate-800 bg-slate-900/40 hover:border-blue-300')
                  }
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="font-semibold text-white text-sm">
                        {label.length > 60 ? label.slice(0, 60) + '…' : label}
                      </div>
                      {subtitle && (
                        <div className="text-xs text-slate-400 mt-0.5">{subtitle}</div>
                      )}
                      <div className="text-[10px] text-slate-500 font-mono mt-1">{id}</div>
                    </div>
                    <DataSourceBadge source={source} size="xs" />
                  </div>
                </button>
              );
            })}
            {data.items.length === 0 && (
              <p className="text-sm text-slate-400 py-8 text-center">
                인스턴스 없음
              </p>
            )}
          </div>

          {/* Detail panel */}
          <div className="lg:sticky lg:top-4 self-start">
            {detailData ? (
              <DetailPanel data={detailData} />
            ) : selectedId ? (
              <p className="text-sm text-slate-400 italic p-4 text-center">
                로딩 중…
              </p>
            ) : (
              <p className="text-sm text-slate-500 italic p-4 text-center border border-dashed border-slate-800 rounded-md">
                왼쪽 인스턴스를 선택하면 디테일이 표시됩니다.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


function DetailPanel({ data }: { data: Record<string, unknown> }) {
  const instance = data.data as Record<string, unknown> | undefined;
  const subgraph = data.subgraph as { root_id: string; nodes: Array<unknown>; edges: Array<unknown> } | null | undefined;
  return (
    <section className="border border-slate-800 rounded-lg bg-slate-900/40">
      <header className="px-4 py-2 border-b border-slate-800 bg-slate-800/40">
        <h2 className="font-semibold text-sm">디테일 - {String(data.id)}</h2>
      </header>
      <div className="p-4 space-y-3">
        {instance && (
          <div>
            <div className="text-xs uppercase text-slate-400 mb-1">필드</div>
            <dl className="text-xs space-y-1">
              {Object.entries(instance).map(([k, v]) => (
                <div key={k} className="flex gap-2 border-b border-slate-800 py-1">
                  <dt className="font-mono text-slate-300 shrink-0 w-32">{k}</dt>
                  <dd className="text-slate-100 break-all">{JSON.stringify(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {subgraph && (
          <div>
            <div className="text-xs uppercase text-slate-400 mb-2">1-hop subgraph</div>
            <CytoscapeView
              subgraph={subgraph as unknown as Parameters<typeof CytoscapeView>[0]['subgraph']}
              height={300}
            />
          </div>
        )}
      </div>
    </section>
  );
}
