import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output produces a minimal Node server bundle in .next/standalone
  // — used by the production Docker image so the container doesn't carry the
  // whole node_modules tree.
  output: "standalone",
  // Backend serves images through /api/images/* — already proxied via API_BASE,
  // so Next.js Image optimization isn't needed and would just add overhead.
  images: { unoptimized: true },
};

export default nextConfig;
