import { NextRequest, NextResponse } from "next/server";
import { createOffer } from "@/lib/offers";
import { z } from "zod";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const offer = await createOffer(body);
    return NextResponse.json(offer, { status: 201 });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        { error: "Datos inválidos", details: error.errors },
        { status: 400 }
      );
    }
    if (error instanceof Error && error.message === "Vehículo no encontrado") {
      return NextResponse.json({ error: error.message }, { status: 404 });
    }
    console.error("[POST /api/offers]", error);
    return NextResponse.json({ error: "Error al crear oferta" }, { status: 500 });
  }
}
