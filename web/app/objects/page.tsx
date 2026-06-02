'use client';

/**
 * Object Explorer 홈 - 31 클래스 그룹화 카드 (Phase 5 Track 5-6).
 *
 * 각 클래스 카드 클릭 → 인스턴스 리스트 페이지로 이동.
 */
import React, { useEffect, useState } from 'react';
import Link from 'next/link';

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

interface ClassMeta {
  name: string;
  group: string;
  implemented: boolean;
  fields: Array<{ name: string; type: string; required: boolean }>;
}

interface ClassesResponse {
  total_classes: number;
  implemented_count: number;
  groups: Record<string, ClassMeta[]>;
}

export default function ObjectsHomePage() {
  const [data, setData] = useState<ClassesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetch(`${PUBLIC_BASE}/api/ontology/classes`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: ClassesResponse) => {
        if (mounted) setData(d);
      })
      .catch((e) => {
        if (mounted) setError((e as Error).message);
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Object Explorer</h1>
        <p className="text-sm text-slate-300">
          {data && (
            <>
              <strong>{data.total_classes}</strong> 클래스 ·{' '}
              <strong>{data.implemented_count}</strong> 구현 ·{' '}
              <strong>{data.total_classes - data.implemented_count}</strong> 미구현
            </>
          )}
        </p>
      </header>

      {error && (
        <div className="border border-red-200 bg-red-500/15 text-red-300 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {loading && <p className="text-slate-400">로딩 중…</p>}

      {data && (
        <div className="space-y-6">
          {Object.entries(data.groups).map(([group, classes]) => (
            <section key={group}>
              <h2 className="font-semibold text-slate-100 mb-2 text-sm uppercase tracking-wide">
                {group} <span className="text-slate-500 font-normal">({classes.length})</span>
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {classes.map((cls) => (
                  <ClassCard key={cls.name} cls={cls} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}


function ClassCard({ cls }: { cls: ClassMeta }) {
  if (cls.implemented) {
    return (
      <Link
        href={`/objects/${cls.name}`}
        className="block border border-slate-800 rounded-md p-3 bg-slate-900/40 hover:border-blue-300 hover:shadow-sm transition"
      >
        <div className="font-semibold text-white text-sm">{cls.name}</div>
        <div className="text-xs text-slate-400 mt-1">
          {cls.fields.length} fields
        </div>
      </Link>
    );
  }
  return (
    <div className="border border-slate-800 bg-slate-800/40 rounded-md p-3 opacity-60">
      <div className="font-semibold text-slate-200 text-sm">{cls.name}</div>
      <div className="text-xs text-slate-500 mt-1">⏳ 후속 phase</div>
    </div>
  );
}
