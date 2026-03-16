import { NextRequest, NextResponse } from "next/server";
import { getAdminOffers } from "@/lib/admin";
import { requireAdmin } from "@/lib/auth";
import type { OfferStatus } from "@prisma/client";

export async function GET(req: NextRequest) {
  const authError = requireAdmin(req);
  if (authError) return authError;

  const sp = req.nextUrl.searchParams;
  const status = sp.get("status") as OfferStatus | null;
  const page = sp.get("page") ? parseInt(sp.get("page")!) : 1;
  const pageSize = sp.get("pageSize") ? parseInt(sp.get("pageSize")!) : 20;

  try {
    const result = await getAdminOffers({ status: status ?? undefined, page, pageSize });
    return NextResponse.json(result);
  } catch (error) {
    console.error("[GET /api/admin/offers]", error);
    return NextResponse.json({ error: "Error" }, { status: 500 });
  }
}
