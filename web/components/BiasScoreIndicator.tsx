'use client';

/**
 * BiasScoreIndicator - political_balance_score 시각화.
 *
 * ADR-0004 Layer 3 - 모든 LLM 응답 메타에 첨부되는 점수의 일관된 표시.
 * `score < threshold` (보통 0.8) 일 때 노란색 경고 → 운영 콘솔 알람과 색 통일.
 */
import React from 'react';

export type BiasScoreSize = 'sm' | 'md' | 'lg';

export interface BiasScoreIndicatorProps {
  score: number;            // 0.0 ~ 1.0
  threshold?: number;       // 알람 임계, default 0.8
  size?: BiasScoreSize;
  showLabel?: boolean;      // "score 0.92 / 양호" 라벨 표시
  alarm?: boolean;          // 명시적 알람 (안주면 score < threshold로 자동)
}

const TIER_LABEL = (s: number): string => {
  if (s >= 0.95) return '우수';
  if (s >= 0.8) return '양호';
  if (s >= 0.6) return '중간';
  return '낮음';
};

const TIER_COLOR = (s: number, threshold: number): { bar: string; text: string } => {
  if (s >= 0.95) return { bar: 'bg-emerald-500', text: 'text-emerald-300' };
  if (s >= threshold) return { bar: 'bg-blue-500', text: 'text-blue-300' };
  if (s >= 0.6) return { bar: 'bg-amber-500', text: 'text-amber-300' };
  return { bar: 'bg-red-500', text: 'text-red-300' };
};

const HEIGHT: Record<BiasScoreSize, string> = {
  sm: 'h-1.5',
  md: 'h-2.5',
  lg: 'h-3.5',
};

const FONT: Record<BiasScoreSize, string> = {
  sm: 'text-[10px]',
  md: 'text-xs',
  lg: 'text-sm',
};

export function BiasScoreIndicator({
  score,
  threshold = 0.8,
  size = 'md',
  showLabel = true,
  alarm,
}: BiasScoreIndicatorProps) {
  const clamped = Math.max(0, Math.min(1, score));
  const tier = TIER_LABEL(clamped);
  const isAlarm = alarm ?? (clamped < threshold);
  const { bar, text } = TIER_COLOR(clamped, threshold);

  return (
    <div className="w-full">
      {showLabel && (
        <div className={`flex items-center justify-between mb-1 ${FONT[size]}`}>
          <span className={`font-medium ${text}`}>
            score {clamped.toFixed(2)} / {tier}
          </span>
          {isAlarm && (
            <span className={`text-amber-300 font-medium ${FONT[size]}`}>
              ⚠ 알람
            </span>
          )}
        </div>
      )}
      <div
        className={`relative w-full ${HEIGHT[size]} bg-slate-700 rounded-full overflow-hidden`}
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-label={`political balance score ${clamped.toFixed(2)}`}
      >
        <div
          className={`${HEIGHT[size]} ${bar} transition-all duration-300`}
          style={{ width: `${clamped * 100}%` }}
        />
        {/* threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-gray-700"
          style={{ left: `${threshold * 100}%` }}
          title={`임계 ${threshold}`}
          aria-hidden
        />
      </div>
    </div>
  );
}
