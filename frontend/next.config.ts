import type { NextConfig } from "next";

// The browser calls /api/..., and Next.js forwards it to the FastAPI backend.
// This avoids CORS problems and keeps the backend address in one place.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
