/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',  // ECS Fargate deploy 호환
  reactStrictMode: true,
  experimental: {
    serverActions: { allowedOrigins: ['*'] },  // PoC. production은 특정 도메인.
  },
};

module.exports = nextConfig;
