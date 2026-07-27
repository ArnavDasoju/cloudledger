import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  devIndicators: false,
  // Static export for production (served by FastAPI)
  // In dev, use Next.js dev server with API proxy via rewrites
  ...(isProd ? { output: "export" } : {}),
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
