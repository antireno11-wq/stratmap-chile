import { Prisma, Transmission, FuelType } from "@prisma/client";
import { db } from "./db";
import type { VehicleSearchParams, PaginatedResult, ListingWithVehicleAndSource } from "../types";

export async function searchListings(
  params: VehicleSearchParams
): Promise<PaginatedResult<ListingWithVehicleAndSource>> {
  const {
    q,
    brand,
    model,
    yearMin,
    yearMax,
    priceMin,
    priceMax,
    mileageMax,
    region,
    transmission,
    fuelType,
    sort = "opportunity",
    page = 1,
    pageSize = 20,
  } = params;

  const vehicleWhere: Prisma.VehicleWhereInput = {
    ...(brand && { brand: { equals: brand, mode: "insensitive" } }),
    ...(model && { model: { equals: model, mode: "insensitive" } }),
    ...(yearMin !== undefined || yearMax !== undefined
      ? { year: { gte: yearMin, lte: yearMax } }
      : {}),
    ...(mileageMax !== undefined && { mileage: { lte: mileageMax } }),
    ...(region && { region }),
    ...(transmission && { transmission: transmission as Transmission }),
    ...(fuelType && { fuelType: fuelType as FuelType }),
    ...(q && {
      OR: [
        { brand: { contains: q, mode: "insensitive" } },
        { model: { contains: q, mode: "insensitive" } },
        { version: { contains: q, mode: "insensitive" } },
      ],
    }),
  };

  const where: Prisma.ListingWhereInput = {
    isActive: true,
    vehicle: vehicleWhere,
    ...(priceMin !== undefined || priceMax !== undefined
      ? { listedPrice: { gte: priceMin, lte: priceMax } }
      : {}),
  };

  // Map sort to Prisma orderBy
  const scoreOrder: Record<string, number> = {
    VERY_GOOD_DEAL: 0,
    GOOD_DEAL: 1,
    FAIR_PRICE: 2,
    OVERPRICED: 3,
  };
  void scoreOrder; // suppress unused warning – used in post-sort for "opportunity"

  let orderBy: Prisma.ListingOrderByWithRelationInput;
  switch (sort) {
    case "price_asc":
      orderBy = { listedPrice: "asc" };
      break;
    case "price_desc":
      orderBy = { listedPrice: "desc" };
      break;
    case "year_desc":
      orderBy = { vehicle: { year: "desc" } };
      break;
    case "mileage_asc":
      orderBy = { vehicle: { mileage: "asc" } };
      break;
    case "opportunity":
    default:
      orderBy = { deltaPercentage: "asc" }; // most negative = best deal first
      break;
  }

  const [total, data] = await Promise.all([
    db.listing.count({ where }),
    db.listing.findMany({
      where,
      orderBy,
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: {
        vehicle: true,
        source: true,
      },
    }),
  ]);

  return {
    data: data as ListingWithVehicleAndSource[],
    total,
    page,
    pageSize,
    totalPages: Math.ceil(total / pageSize),
  };
}

export async function getListingById(
  id: string
): Promise<ListingWithVehicleAndSource | null> {
  const listing = await db.listing.findUnique({
    where: { id },
    include: {
      vehicle: true,
      source: true,
    },
  });
  return listing as ListingWithVehicleAndSource | null;
}

export async function getSimilarListings(
  currentListingId: string,
  brand: string,
  model: string,
  year: number,
  limit = 4
): Promise<ListingWithVehicleAndSource[]> {
  const results = await db.listing.findMany({
    where: {
      id: { not: currentListingId },
      isActive: true,
      vehicle: {
        brand: { equals: brand, mode: "insensitive" },
        model: { equals: model, mode: "insensitive" },
        year: { gte: year - 2, lte: year + 2 },
      },
    },
    orderBy: { deltaPercentage: "asc" },
    take: limit,
    include: {
      vehicle: true,
      source: true,
    },
  });
  return results as ListingWithVehicleAndSource[];
}

export async function getDistinctBrands(): Promise<string[]> {
  const result = await db.vehicle.findMany({
    distinct: ["brand"],
    select: { brand: true },
    orderBy: { brand: "asc" },
  });
  return result.map((r) => r.brand);
}

export async function getDistinctModels(brand?: string): Promise<string[]> {
  const result = await db.vehicle.findMany({
    where: brand ? { brand: { equals: brand, mode: "insensitive" } } : undefined,
    distinct: ["model"],
    select: { model: true },
    orderBy: { model: "asc" },
  });
  return result.map((r) => r.model);
}
