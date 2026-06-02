'use client';

/**
 * KoreaChoropleth - 17 시도 GeoJSON 기반 SVG 지도 (react-simple-maps).
 *
 * 데이터:
 *   - 지도 데이터: /skorea-provinces.geo.json (KOSTAT 2018 17 시도 polygon)
 *   - 비즈니스 데이터: SidoStats (name_kr, member_count, density_label, parties)
 *
 * ADR-0004 정치 중립성:
 *   - 정파(정당) 색 사용 금지 — density(의원 수 비례) blue scale만 채색
 *   - 단정적 평가성 라벨 회피
 */
import React, { useState } from 'react';
import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps';
import type { SidoStats } from '../lib/scenario-clients';


const GEO_URL = '/skorea-provinces.geo.json';

// density_label → 채도 단계 매핑 (다크 톤 blue scale)
const DENSITY_FILL: Record<string, string> = {
  '매우 높음': '#1d4ed8',   // blue-700
  '높음':     '#3b82f6',   // blue-500
  '보통':     '#60a5fa',   // blue-400
  '낮음':     '#93c5fd',   // blue-300
};
const DEFAULT_FILL = '#334155';   // slate-700 (데이터 없음)


// GeoJSON name_kr가 정확히 매치 안 되는 경우 mapping (특별자치)
const GEO_NAME_NORMALIZE: Record<string, string> = {
  '강원도': '강원특별자치도',
  '전라북도': '전북특별자치도',
};


export interface KoreaChoroplethProps {
  sido: SidoStats[];
  selectedKey?: string;
  onSelect?: (key: string) => void;
  height?: number;
}


export function KoreaChoropleth({
  sido, selectedKey, onSelect, height = 500,
}: KoreaChoroplethProps) {
  const [hoverName, setHoverName] = useState<string | null>(null);

  // GeoJSON feature의 name 속성 → SidoStats lookup
  // SidoStats.name_kr이 GeoJSON properties.name과 일치하도록.
  const byName = new Map<string, SidoStats>();
  for (const s of sido) {
    byName.set(s.name_kr, s);
    // 특별자치도 도입 전 명칭도 매핑
    const normalized = GEO_NAME_NORMALIZE[s.name_kr];
    if (normalized) byName.set(normalized, s);
  }

  function lookupFromGeoName(name: string): SidoStats | undefined {
    if (byName.has(name)) return byName.get(name);
    // GeoJSON이 옛 이름이면 (예: '강원도') → 신 이름 (예: '강원특별자치도')으로 정규화 후 lookup
    const normalized = GEO_NAME_NORMALIZE[name];
    if (normalized && byName.has(normalized)) return byName.get(normalized);
    // GeoJSON이 신 이름이면 (이미 매칭됐어야 함) → 역방향: byName에 옛 이름만 있는 경우 보정
    for (const [orig, newName] of Object.entries(GEO_NAME_NORMALIZE)) {
      if (newName === name && byName.has(orig)) return byName.get(orig);
    }
    return undefined;
  }

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-900/50 overflow-hidden">
      {/* legend */}
      <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between text-xs">
        <span className="text-slate-300 font-semibold">17 시도 의원 분포</span>
        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <span className="font-semibold">density:</span>
          {['낮음', '보통', '높음', '매우 높음'].map((d) => (
            <span key={d} className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: DENSITY_FILL[d] }} />
              {d}
            </span>
          ))}
        </div>
      </div>

      <div className="relative" style={{ background: '#0f172a' }}>
        <ComposableMap
          projection="geoMercator"
          projectionConfig={{ scale: 5500, center: [127.8, 36.3] }}
          width={800}
          height={height}
          style={{ width: '100%', height: 'auto' }}
        >
          <ZoomableGroup zoom={1}>
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map((geo) => {
                  const name = String(geo.properties.name ?? geo.properties.CTP_KOR_NM ?? '');
                  const stats = lookupFromGeoName(name);
                  const fill = stats ? (DENSITY_FILL[stats.density_label] ?? DEFAULT_FILL) : DEFAULT_FILL;
                  const isSelected = stats && stats.key === selectedKey;
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onMouseEnter={() => setHoverName(name)}
                      onMouseLeave={() => setHoverName(null)}
                      onClick={() => stats && onSelect?.(stats.key)}
                      style={{
                        default: {
                          fill,
                          stroke: '#1e293b',
                          strokeWidth: 0.5,
                          outline: 'none',
                          cursor: stats ? 'pointer' : 'default',
                        },
                        hover: {
                          fill,
                          stroke: '#fbbf24',
                          strokeWidth: 1.5,
                          outline: 'none',
                        },
                        pressed: { fill, outline: 'none' },
                      }}
                      strokeWidth={isSelected ? 2 : undefined}
                    />
                  );
                })
              }
            </Geographies>
          </ZoomableGroup>
        </ComposableMap>

        {/* hover tooltip */}
        {hoverName && (
          <div className="absolute top-2 right-2 bg-slate-900/95 border border-slate-700 rounded px-3 py-2 text-xs text-slate-100 pointer-events-none">
            {(() => {
              const s = lookupFromGeoName(hoverName);
              if (!s) return <span>{hoverName} <span className="text-slate-500">(데이터 없음)</span></span>;
              return (
                <>
                  <div className="font-semibold mb-1">{s.name_kr}</div>
                  <div className="text-slate-300">의원 {s.member_count}명</div>
                  <div className="text-slate-400">{s.density_label} · {s.activity.proposed} 발의</div>
                </>
              );
            })()}
          </div>
        )}
      </div>

      <div className="px-3 py-2 border-t border-slate-800 text-[10px] text-slate-500">
        클릭하여 시도 상세 보기. KOSTAT 2018 GeoJSON.
      </div>
    </div>
  );
}
