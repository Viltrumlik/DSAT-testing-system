import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for PM2 deployment
  output: "standalone",

  // Don't let Next.js strip/add trailing slashes before rewrites fire —
  // Django uses APPEND_SLASH and expects them; mismatches cause redirect loops.
  skipTrailingSlashRedirect: true,

  // Proxy /api/* → backend in development.
  // Default: production server (real data). Override with API_PROXY_TARGET=http://localhost:8000
  // when you want to hit a local Django.
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    const target = process.env.API_PROXY_TARGET || "https://mastersat.uz";
    return [
      {
        source: "/api/:path*/",
        destination: `${target}/api/:path*/`,
      },
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },

  // Image optimization
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
    formats: ["image/webp", "image/avif"],
  },

  // Compress responses
  compress: true,

  // Power-optimize production builds
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
