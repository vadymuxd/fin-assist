import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_COOKIE, expectedToken } from "@/lib/auth";

export async function proxy(request: NextRequest) {
  const cookie = request.cookies.get(AUTH_COOKIE)?.value;
  const expected = await expectedToken();

  if (cookie === expected) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  const from = request.nextUrl.pathname + request.nextUrl.search;
  if (from && from !== "/login") {
    url.searchParams.set("from", from);
  } else {
    url.searchParams.delete("from");
  }
  return NextResponse.redirect(url);
}

export const config = {
  matcher: [
    // Run on everything except the login page, the login API, static assets, and metadata files.
    "/((?!login|api/login|_next/static|_next/image|favicon.ico|apple-icon|icon|manifest.webmanifest|robots.txt|sitemap.xml).*)",
  ],
};
