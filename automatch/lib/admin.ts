import { db } from "./db";
import type { OfferWithVehicle } from "../types";
import type { OfferStatus, Source } from "@prisma/client";

export interface AdminStats {
  totalVehicles: number;
  totalListings: number;
  totalOffers: number;
  totalSources: number;
  offersByStatus: Record<OfferStatus, number>;
  opportunityDistribution: Record<string, number>;
  avgMarketDelta: number;
}

export async function getAdminStats(): Promise<AdminStats> {
  const [
    totalVehicles,
    totalListings,
    totalOffers,
    totalSources,
    offersByStatus,
    opportunityDist,
    avgDelta,
  ] = await Promise.all([
    db.vehicle.count(),
    db.listing.count({ where: { isActive: true } }),
    db.offer.count(),
    db.source.count(),
    db.offer.groupBy({ by: ["status"], _count: { status: true } }),
    db.listing.groupBy({ by: ["opportunityScore"], _count: { opportunityScore: true } }),
    db.listing.aggregate({ _avg: { deltaPercentage: true } }),
  ]);

  const statusMap = {} as Record<OfferStatus, number>;
  const allStatuses: OfferStatus[] = ["NEW", "CONTACTED", "NEGOTIATING", "ACCEPTED", "REJECTED"];
  allStatuses.forEach((s) => (statusMap[s] = 0));
  offersByStatus.forEach((o) => (statusMap[o.status] = o._count.status));

  const oppMap: Record<string, number> = {};
  opportunityDist.forEach((o) => (oppMap[o.opportunityScore] = o._count.opportunityScore));

  return {
    totalVehicles,
    totalListings,
    totalOffers,
    totalSources,
    offersByStatus: statusMap,
    opportunityDistribution: oppMap,
    avgMarketDelta: Math.round(avgDelta._avg.deltaPercentage ?? 0),
  };
}

export interface AdminOfferParams {
  status?: OfferStatus;
  page?: number;
  pageSize?: number;
}

export async function getAdminOffers(params: AdminOfferParams = {}) {
  const { status, page = 1, pageSize = 20 } = params;

  const where = status ? { status } : {};

  const [total, data] = await Promise.all([
    db.offer.count({ where }),
    db.offer.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: {
        vehicle: true,
        listing: true,
      },
    }),
  ]);

  return {
    data: data as OfferWithVehicle[],
    total,
    page,
    pageSize,
    totalPages: Math.ceil(total / pageSize),
  };
}

export async function getAdminVehicles(params: { page?: number; pageSize?: number } = {}) {
  const { page = 1, pageSize = 25 } = params;

  const [total, data] = await Promise.all([
    db.vehicle.count(),
    db.vehicle.findMany({
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: {
        listings: {
          include: { source: true },
          where: { isActive: true },
          take: 1,
          orderBy: { deltaPercentage: "asc" },
        },
        _count: { select: { offers: true, listings: true } },
      },
    }),
  ]);

  return { data, total, page, pageSize, totalPages: Math.ceil(total / pageSize) };
}

export async function getAdminSources(): Promise<Source[]> {
  return db.source.findMany({
    orderBy: { name: "asc" },
    include: {
      _count: { select: { listings: true } },
    } as Parameters<typeof db.source.findMany>[0]["include"],
  });
}
