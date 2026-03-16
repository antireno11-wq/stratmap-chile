import { NextRequest, NextResponse } from "next/server";
import { searchListings } from "@/lib/vehicles";
import type { VehicleSearchParams } from "@/types";

export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;

    const params: VehicleSearchParams = {
      q: sp.get("q") ?? undefined,
      brand: sp.get("brand") ?? undefined,
      model: sp.get("model") ?? undefined,
      yearMin: sp.get("yearMin") ? parseInt(sp.get("yearMin")!) : undefined,
      yearMax: sp.get("yearMax") ? parseInt(sp.get("yearMax")!) : undefined,
      priceMin: sp.get("priceMin") ? parseInt(sp.get("priceMin")!) : undefined,
      priceMax: sp.get("priceMax") ? parseInt(sp.get("priceMax")!) : undefined,
      mileageMax: sp.get("mileageMax") ? parseInt(sp.get("mileageMax")!) : undefined,
      region: sp.get("region") ?? undefined,
      transmission: sp.get("transmission") ?? undefined,
      fuelType: sp.get("fuelType") ?? undefined,
      sort: (sp.get("sort") as VehicleSearchParams["sort"]) ?? "opportunity",
      page: sp.get("page") ? parseInt(sp.get("page")!) : 1,
      pageSize: sp.get("pageSize") ? parseInt(sp.get("pageSize")!) : 20,
    };

    const result = await searchListings(params);
    return NextResponse.json(result);
  } catch (error) {
    console.error("[GET /api/vehicles]", error);
    return NextResponse.json({ error: "Error al buscar vehículos" }, { status: 500 });
  }
}
