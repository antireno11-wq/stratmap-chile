import { NextRequest, NextResponse } from "next/server";
import { getListingById, getSimilarListings } from "@/lib/vehicles";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const listing = await getListingById(id);

    if (!listing) {
      return NextResponse.json({ error: "Publicación no encontrada" }, { status: 404 });
    }

    const similar = await getSimilarListings(
      listing.id,
      listing.vehicle.brand,
      listing.vehicle.model,
      listing.vehicle.year
    );

    return NextResponse.json({ listing, similar });
  } catch (error) {
    console.error("[GET /api/vehicles/[id]]", error);
    return NextResponse.json({ error: "Error al obtener vehículo" }, { status: 500 });
  }
}
