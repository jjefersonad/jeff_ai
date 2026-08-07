import type { NextConfig } from "next";

// Server-side-only (no `NEXT_PUBLIC_` prefix — never inlined into the
// browser bundle) base URL for the rewrite proxy targets below. These
// rewrites run inside the Next.js server process, not the browser, so in
// Docker Compose it must use the internal service hostname + the
// container's actual listening port (`backend:8000` — NOT the host-mapped
// port 8001). In any other deployment (bare metal, Kubernetes, a managed
// platform) the backend address will differ, so it's overridable via env
// var instead of hardcoded.
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://backend:8000";

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
      // `/api/mcp/*` (change `retire-image-server`): antes servido pelo
      // container `image-server`, isolado do grafo do agente por processo;
      // hoje montado em `webapp.py`, no mesmo processo do `backend`.
      // `require_auth` (global no app) faz a mesma garantia agora.
      {
        source: "/api/mcp/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/mcp/:path*`,
      },
      // `/api/admin/*` (change `user-management`): API administrativa de
      // usuários (`GET/POST /admin/users`, `PATCH /admin/users/{id}`).
      // O `admin_users_router` no backend tem prefixo `/admin` (sem `/api/`),
      // ao contrário do `mcp_admin_router` que tem `/api/mcp`. Mantemos
      // `/api/admin/*` no rewrite para o frontend ter um único namespace
      // (`/api/...`) — ver `frontend/src/app/lib/adminUsers.ts`.
      {
        source: "/api/admin/:path*",
        destination: `${BACKEND_INTERNAL_URL}/admin/:path*`,
      },
    ];
  },
};

export default nextConfig;
