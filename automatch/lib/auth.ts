import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const ADMIN_COOKIE = "automatch_admin";

/**
 * Simple admin auth guard for API routes.
 * Returns a 401 response if not authenticated, undefined if ok.
 *
 * NOTE: This is an MVP-grade guard — not production-ready.
 * For production, replace with proper session management (NextAuth, Clerk, etc.)
 */
export function requireAdmin(req: NextRequest): NextResponse | undefined {
  const cookie = req.cookies.get(ADMIN_COOKIE);
  if (!cookie || cookie.value !== "1") {
    return NextResponse.json({ error: "No autorizado" }, { status: 401 });
  }
  return undefined;
}

/**
 * Server Action–compatible check.
 * Use in Server Components / Server Actions that need admin access.
 */
export async function isAdminSession(): Promise<boolean> {
  const cookieStore = await cookies();
  const cookie = cookieStore.get(ADMIN_COOKIE);
  return cookie?.value === "1";
}

export function setAdminCookie(res: NextResponse) {
  res.cookies.set(ADMIN_COOKIE, "1", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8, // 8 hours
  });
}

export function clearAdminCookie(res: NextResponse) {
  res.cookies.delete(ADMIN_COOKIE);
}
