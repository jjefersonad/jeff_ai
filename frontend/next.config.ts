import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Rotas de mídia e documentos servidas pelo `http.app` do backend
      // LangGraph (change `consolidate-http-routes-langgraph`). Apontam para o
      // nome de serviço Docker `backend` na porta interna 8000 (mapeada para
      // 8001 no host). Os rewrites rodam server-side dentro do container
      // `frontend`, que resolve nomes da rede Docker — não `localhost`.
      {
        source: "/api/images/:path*",
        destination: "http://backend:8000/api/images/:path*",
      },
      {
        source: "/api/files/:path*",
        destination: "http://backend:8000/api/files/:path*",
      },
      {
        source: "/api/references",
        destination: "http://backend:8000/api/references",
      },
      {
        source: "/api/references/:path*",
        destination: "http://backend:8000/api/references/:path*",
      },
      // `/api/mcp/*` continua no container `image-server` (processo
      // isolado do grafo do agente — REQ-001 do `mcp-client`).
      {
        source: "/api/mcp/:path*",
        destination: "http://image-server:8080/api/mcp/:path*",
      },
    ];
  },
};

export default nextConfig;
