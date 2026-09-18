/**
 * The browser talks to `/api/v1/*` on this origin; Next proxies it to the API.
 *
 * Why a rewrite rather than axios pointing straight at http://localhost:8000:
 * the API and the browser are not always on the same host. When they are not --
 * a container, a tunnel, the live preview this project is developed in --
 * `localhost` in the browser means the *user's* machine, and the request fails
 * with a connection error that looks like the API is down. A relative URL can
 * never have that problem, and it also means one build works everywhere.
 *
 * Override with NEXT_PUBLIC_API_URL to skip the proxy entirely (e.g. a deployed
 * API on another host, where CORS is already wide open).
 */
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${API_PROXY_TARGET}/api/v1/:path*` },
      { source: "/healthz", destination: `${API_PROXY_TARGET}/api/v1/health` },
    ];
  },
};

export default nextConfig;
