import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/images/:path*",
        destination: "http://image-server:8080/api/images/:path*",
      },
      {
        source: "/api/files/:path*",
        destination: "http://image-server:8080/api/files/:path*",
      },
      {
        source: "/api/references",
        destination: "http://image-server:8080/api/references",
      },
      {
        source: "/api/references/:path*",
        destination: "http://image-server:8080/api/references/:path*",
      },
      {
        source: "/api/mcp/:path*",
        destination: "http://image-server:8080/api/mcp/:path*",
      },
    ];
  },
};

export default nextConfig;
