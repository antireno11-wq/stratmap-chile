import type { Vehicle, Listing, Source, Offer, PriceSnapshot, OpportunityScore, OfferStatus } from "@prisma/client";

export type VehicleWithListings = Vehicle & {
  listings: (Listing & { source: Source })[];
};

export type ListingWithVehicleAndSource = Listing & {
  vehicle: Vehicle;
  source: Source;
};

export type OfferWithVehicle = Offer & {
  vehicle: Vehicle;
  listing: Listing | null;
};

export interface VehicleSearchParams {
  q?: string;
  brand?: string;
  model?: string;
  yearMin?: number;
  yearMax?: number;
  priceMin?: number;
  priceMax?: number;
  mileageMax?: number;
  region?: string;
  transmission?: string;
  fuelType?: string;
  sort?: "opportunity" | "price_asc" | "price_desc" | "year_desc" | "mileage_asc";
  page?: number;
  pageSize?: number;
}

export interface PaginatedResult<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export { OpportunityScore, OfferStatus };
