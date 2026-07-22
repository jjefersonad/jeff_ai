import type { NextConfig } from "next";

// Server-side-only (no `NEXT_PUBLIC_` prefix — never inlined into the
// browser bundle) base URLs for the rewrite proxy targets below. These
// rewrites run inside the Next.js server process, not the browser, so in
// Docker Compose they must use the internal service hostname + the
// container's actual listening port (`backend:8000`, `image-server:8080` —
// NOT the host-mapped ports 8001/8083). In any other deployment (bare
// metal, Kubernetes, a managed platform) the backend/image-server addresses
// will differ, so both are overridable via env var instead of hardcoded.
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://backend:8000";
const IMAGE_SERVER_INTERNAL_URL =
  process.env.IMAGE_SERVER_INTERNAL_URL ?? "http://image-server:8080";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Rotas de mídia e documentos servidas pelo `http.app` do backend
      // LangGraph (change `consolidate-http-routes-langgraph`).
      {
        source: "/api/images/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/images/:path*`,
      },
      {
        source: "/api/files/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/files/:path*`,
      },
      {
        source: "/api/references",
        destination: `${BACKEND_INTERNAL_URL}/api/references`,
      },
      {
        source: "/api/references/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/references/:path*`,
      },
      // `/api/mcp/*` continua no container `image-server` (processo
      // isolado do grafo do agente — REQ-001 do `mcp-client`).
      {
        source: "/api/mcp/:path*",
        destination: `${IMAGE_SERVER_INTERNAL_URL}/api/mcp/:path*`,
      },
    ];
  },
};

export default nextConfig;
