/**
 * DataSourceBadge - 모든 시나리오 페이지 상단·hit 옆에 노출.
 *
 * 데이터 출처 투명성 (spec §5.3) - real/synthetic/external 색상 구분.
 */
import React from 'react';

type Source = 'real' | 'synthetic' | 'external';

const CONFIG: Record<Source, { label: string; bg: string; fg: string }> = {
  real: { label: '실 데이터', bg: 'bg-badge-real', fg: 'text-white' },
  synthetic: { label: '합성', bg: 'bg-badge-synthetic', fg: 'text-white' },
  external: { label: '외부', bg: 'bg-badge-external', fg: 'text-white' },
};

export function DataSourceBadge({
  source,
  size = 'sm',
}: {
  source: string;
  size?: 'sm' | 'xs';
}) {
  const config = CONFIG[source as Source] ?? {
    label: source,
    bg: 'bg-gray-500',
    fg: 'text-white',
  };
  const sizeCls = size === 'xs' ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2 py-1';
  return (
    <span
      className={`inline-flex items-center rounded-md font-medium ${sizeCls} ${config.bg} ${config.fg}`}
      title={`출처: ${config.label}`}
    >
      {config.label}
    </span>
  );
}
