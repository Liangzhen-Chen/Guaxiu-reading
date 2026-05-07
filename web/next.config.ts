import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // Internal Vercel-to-ECS connection: the ECS backend (port 8000) has no TLS
        // termination, so this uses HTTP inside Vercel's internal network (not exposed
        // to the client). TLS between client and Vercel edge is handled by Vercel.
        destination: "http://122.51.236.219/api/:path*",
      },
    ];
  },
};

export default nextConfig;
