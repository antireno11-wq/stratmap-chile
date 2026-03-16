import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { password } = await req.json().catch(() => ({}));
  const secret = process.env.ADMIN_SECRET ?? "automatch-admin-2024";

  if (!password || password !== secret) {
    return NextResponse.json({ error: "No autorizado" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set("automatch_admin", "1", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("automatch_admin");
  return res;
}
