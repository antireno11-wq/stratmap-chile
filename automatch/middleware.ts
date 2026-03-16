import { NextRequest, NextResponse } from "next/server";

const ADMIN_COOKIE = "automatch_admin";
const ADMIN_LOGIN_PATH = "/admin/login";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Protect /admin/* routes (except /admin/login itself)
  if (pathname.startsWith("/admin") && pathname !== ADMIN_LOGIN_PATH) {
    const cookie = req.cookies.get(ADMIN_COOKIE);
    if (!cookie || cookie.value !== "1") {
      const loginUrl = req.nextUrl.clone();
      loginUrl.pathname = ADMIN_LOGIN_PATH;
      loginUrl.searchParams.set("redirect", pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
