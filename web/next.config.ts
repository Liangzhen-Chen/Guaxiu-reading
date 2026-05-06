import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "https://api.xiugua-reading.cn/api/:path*",
      },
    ];
  },
};

export default nextConfig;
