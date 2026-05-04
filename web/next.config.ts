import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://122.51.236.219:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
