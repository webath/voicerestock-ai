import type { NextConfig } from "next";

// Το dashboard δεν μιλά ποτέ απευθείας με το ERP: μόνο με το App API (mock ή πραγματικό, ίδια endpoints)
// και με τον voice agent (στο VPS, μέσω του apps/voice/deploy/tunnel.sh). Proxy από τον ίδιο origin → χωρίς CORS.
const APP_API_URL = process.env.APP_API_URL ?? "http://localhost:8000";
const VOICE_URL = process.env.VOICE_URL ?? "http://localhost:8100";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/backend/:path*", destination: `${APP_API_URL}/api/:path*` },
      { source: "/voice-api/:path*", destination: `${VOICE_URL}/voice/:path*` },
    ];
  },
};

export default nextConfig;
