import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // ADR-0004: 정치 중립성 시각 디자인 - 정당 색 미사용. 카테고리 기반만.
        'badge-real':      '#15803d',   // 녹색 (real data)
        'badge-synthetic': '#ca8a04',   // 노란색 (synthetic)
        'badge-external':  '#1d4ed8',   // 파란색 (external)
        'alarm':           '#dc2626',   // 빨강 (정치 균형 알람)
        'warn':            '#f59e0b',   // 노랑 (낮은 균형 점수)
      },
    },
  },
  plugins: [],
};

export default config;
