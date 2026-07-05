import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/images/:path*",
        destination: "http://image-server:8080/api/images/:path*",
      },
    ];
  },
};

export default nextConfig;
