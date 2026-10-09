import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Keep the demo UI clean: no floating dev-tools badge in the corner.
  devIndicators: false,
};

export default nextConfig;
