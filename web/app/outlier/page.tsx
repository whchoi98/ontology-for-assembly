'use client';

/**
 * 시나리오 K - 표결 이상치 (PDF 시그니처 ★).
 *
 * 당론 이탈 · 박빙 표결 · 정파 초월 협력 패턴 - 3 유형 필터 + 상세 패널.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { readPersonaIdSync } from '../../components/PersonaSwitch';
import { outlierApi, type OutlierEntry, type OutlierListResponse } from '../../lib/scenario-clients';
import type { PersonaId } from '../../lib/personas';

type FilterType = '' | 'party_line_break' | 'swing_vote' | 'cross_party';

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  party_line_break: { label: '당론 이탈', color: 'bg-red-100 text-red-800' },
  swing_vote: { label: '박빙', color: 'bg-amber-100 text-amber-800' },
  cross_party: { label: '정파 초월 협력', color: 'bg-emerald-100 text-emerald-800' },
};


export default function OutlierPage() {
  const [data, setData] = useState<OutlierListResponse | null>(null);
  const [selected, setSelected] = useState<OutlierEntry | null>(null);
  const [filter, setFilter] = useState<FilterType>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (currentFilter: FilterType) => {
    setLoading(true);
    setError(null);
    try {
      const personaId = readPersonaIdSync() as PersonaId;
      const response = await outlierApi.list({
        outlierType: currentFilter || undefined,
        personaId,
      });
      setData(response);
      // 첫 entry 자동 선택
      if (response.outliers.length > 0 && !selected) {
        setSelected(response.outliers[0]);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    void load(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return (
    <div>
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-mono text-sm text-gray-400">시나리오 K</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">
            PDF 시그니처 ★
          </span>
        </div>
        <h1 className="text-2xl font-bold mb-1">표결 이상치 탐지</h1>
        <p className="text-sm text-gray-600">
          {data?.persona_note ?? '당론 이탈, 박빙 표결, 정파 초월 협력 패턴을 자동 탐지.'}
        </p>
      </header>

      {/* 유형 필터 */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {[
          { id: '' as FilterType, label: '전체' },
          { id: 'party_line_break' as FilterType, label: '당론 이탈' },
          { id: 'swing_vote' as FilterType, label: '박빙' },
          { id: 'cross_party' as FilterType, label: '정파 초월 협력' },
        ].map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={
              'text-xs px-3 py-1.5 rounded-md border ' +
              (filter === f.id
                ? 'border-blue-500 bg-blue-50 text-blue-800 font-medium'
                : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50')
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 text-red-800 rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}
      {loading && <p className="text-gray-500">로딩 중…</p>}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 리스트 */}
          <div className="space-y-2">
            {data.outliers.map((o) => (
              <OutlierCard
                key={o.outlier_id}
                outlier={o}
                active={selected?.outlier_id === o.outlier_id}
                onClick={() => setSelected(o)}
              />
            ))}
            {data.outliers.length === 0 && (
              <p className="text-sm text-gray-500 py-8 text-center">이상치 없음</p>
            )}
          </div>

          {/* 상세 패널 */}
          <div className="lg:sticky lg:top-4 self-start">
            {selected ? <OutlierDetail entry={selected} /> : (
              <p className="text-sm text-gray-400 italic p-4 text-center border border-dashed border-gray-200 rounded-md">
                왼쪽에서 이상치를 선택하세요.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


function OutlierCard({
  outlier,
  active,
  onClick,
}: {
  outlier: OutlierEntry;
  active: boolean;
  onClick: () => void;
}) {
  const typeMeta = TYPE_LABELS[outlier.outlier_type] ?? { label: outlier.outlier_type, color: 'bg-gray-100 text-gray-700' };
  return (
    <button
      onClick={onClick}
      className={
        'w-full text-left border rounded-md p-3 transition ' +
        (active
          ? 'border-blue-400 bg-blue-50'
          : 'border-gray-200 bg-white hover:border-blue-300')
      }
    >
      <div className="flex items-center justify-between mb-1">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeMeta.color}`}>
          {typeMeta.label}
        </span>
        <span className="text-xs text-gray-500 font-mono">
          dev {outlier.deviation_score.toFixed(2)}
        </span>
      </div>
      <h3 className="font-semibold text-gray-900 text-sm mb-0.5">
        {outlier.bill_title}
      </h3>
      <div className="text-xs text-gray-500">{outlier.vote_date} · {outlier.label}</div>
    </button>
  );
}


function OutlierDetail({ entry }: { entry: OutlierEntry }) {
  const typeMeta = TYPE_LABELS[entry.outlier_type] ?? { label: entry.outlier_type, color: 'bg-gray-100' };
  return (
    <section className="border border-gray-200 rounded-lg bg-white">
      <header className="px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeMeta.color}`}>
            {typeMeta.label}
          </span>
          <span className="text-xs text-gray-500 font-mono">
            deviation_score {entry.deviation_score.toFixed(2)}
          </span>
        </div>
        <h2 className="font-bold text-gray-900">{entry.bill_title}</h2>
        <div className="text-xs text-gray-500 mt-1">
          {entry.vote_date} · vote_id: <span className="font-mono">{entry.vote_id.slice(0, 30)}…</span>
        </div>
      </header>

      <div className="p-4 space-y-4 text-sm">
        <section>
          <h3 className="text-xs uppercase text-gray-500 mb-1">설명</h3>
          <p className="text-gray-800 leading-relaxed">{entry.description}</p>
        </section>

        <section className="grid grid-cols-2 gap-3 text-xs">
          <div className="border border-gray-100 rounded p-2 bg-gray-50">
            <div className="text-gray-500 uppercase text-[10px] mb-1">예상 패턴</div>
            <div className="text-gray-800">{entry.expected_pattern}</div>
          </div>
          <div className="border border-gray-100 rounded p-2 bg-gray-50">
            <div className="text-gray-500 uppercase text-[10px] mb-1">실제 패턴</div>
            <div className="text-gray-800">{entry.actual_pattern}</div>
          </div>
        </section>

        {entry.deviating_persons.length > 0 && (
          <section>
            <h3 className="text-xs uppercase text-gray-500 mb-2">
              이탈 의원 ({entry.deviating_persons.length}명)
            </h3>
            <ul className="space-y-1">
              {entry.deviating_persons.map((p) => (
                <li key={p.person_id} className="flex items-start gap-2 text-xs">
                  <span className="font-mono text-gray-400 shrink-0">{p.person_id}</span>
                  <span className="font-semibold text-gray-800">{p.name}</span>
                  <span className="text-gray-500">{p.party}</span>
                  <span className="text-gray-500">→ <strong>{p.choice}</strong></span>
                  {p.reason_hint && (
                    <span className="text-gray-500 italic">({p.reason_hint})</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="border-l-4 border-amber-400 bg-amber-50 p-3 rounded">
          <div className="text-[10px] uppercase text-amber-700 font-semibold mb-1">
            AI 패턴 라벨
          </div>
          <p className="text-amber-900 text-xs leading-relaxed">{entry.ai_label}</p>
        </section>
      </div>
    </section>
  );
}
