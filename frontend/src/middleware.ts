import { NextRequest, NextResponse } from "next/server";

/** Matches backend `SESSION_COOKIE_NAME` in `backend/src/infrastructure/auth/sessions.py`. */
const SESSION_COOKIE_NAME = "session";
const PUBLIC_PATH_PREFIX = "/public";
const LOGIN_PATH = "/public/login";
const DEFAULT_PROTECTED_PATH = "/";

export function isPublicPath(pathname: string): boolean {
  return pathname === PUBLIC_PATH_PREFIX || pathname.startsWith(`${PUBLIC_PATH_PREFIX}/`);
}

/**
 * Only same-app relative paths are safe redirect targets. Rejects protocol-relative
 * ("//evil.com") and absolute ("https://evil.com") values to prevent open redirects.
 */
export function sanitizeRedirectTarget(candidate: string | null): string {
  if (!candidate) return DEFAULT_PROTECTED_PATH;
  if (!candidate.startsWith("/") || candidate.startsWith("//")) return DEFAULT_PROTECTED_PATH;
  if (candidate.includes("://")) return DEFAULT_PROTECTED_PATH;
  return candidate;
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  // Unauthenticated requests for the root path serve the public landing page
  // in place (rewrite, not redirect) so crawlers — including Google's OAuth
  // brand verification crawler — and human visitors without a session cookie
  // both receive 200 with real content at `/` instead of a redirect to
  // `/public/login`. See `public-marketing-landing-page` REQ-001 / REQ-004
  // and design D1 of change `google-oauth-verification-brand-fix`.
  if (pathname === "/" && !request.cookies.has(SESSION_COOKIE_NAME)) {
    return NextResponse.rewrite(new URL("/public/landing", request.url));
  }

  if (request.cookies.has(SESSION_COOKIE_NAME)) {
    return NextResponse.next();
  }

  const loginUrl = new URL(LOGIN_PATH, request.url);
  loginUrl.searchParams.set("redirect", sanitizeRedirectTarget(`${pathname}${search}`));
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Skip Next auth redirect for `/api/*` — those are proxied to the backend
  // (see `next.config.ts` rewrites). A missing cookie must become a JSON 401
  // from FastAPI, not an HTML redirect to `/public/login`.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
}
