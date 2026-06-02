/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',  // ECS Fargate deploy 호환
  reactStrictMode: true,
  experimental: {
    // CSRF: server actions은 known origins만 허용. wildcard 금지 (Kiro review gate).
    serverActions: {
      allowedOrigins: [
        'd1y2pud3gf6i25.cloudfront.net',           // assembly dev CloudFront
        'assembly.whchoi.net',                      // custom 도메인 (Route 53 alias)
        'localhost:3000', '127.0.0.1:3000',         // 로컬 dev
        ...(process.env.NEXT_ALLOWED_ORIGINS?.split(',') ?? []),  // env extension
      ],
    },
  },
};

module.exports = nextConfig;
