import { NextRequest, NextResponse } from "next/server";
import { updateOfferStatus } from "@/lib/offers";
import { requireAdmin } from "@/lib/auth";
import type { OfferStatus } from "@prisma/client";

const VALID_STATUSES: OfferStatus[] = ["NEW", "CONTACTED", "NEGOTIATING", "ACCEPTED", "REJECTED"];

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authError = requireAdmin(req);
  if (authError) return authError;

  try {
    const { id } = await params;
    const { status } = await req.json();

    if (!VALID_STATUSES.includes(status)) {
      return NextResponse.json({ error: "Estado inválido" }, { status: 400 });
    }

    const updated = await updateOfferStatus(id, status);
    return NextResponse.json(updated);
  } catch (error) {
    console.error("[PATCH /api/admin/offers/[id]]", error);
    return NextResponse.json({ error: "Error al actualizar oferta" }, { status: 500 });
  }
}
