import Link from "next/link";
import type { ListingWithVehicleAndSource } from "@/types";
import { formatCLP, formatKm, formatPercentage } from "@/lib/utils";
import { OpportunityBadge } from "./opportunity-badge";

interface VehicleCardProps {
  listing: ListingWithVehicleAndSource;
}

const TRANSMISSION_LABELS = {
  MANUAL: "Manual",
  AUTOMATIC: "Automático",
  CVT: "CVT",
};

const FUEL_LABELS = {
  GASOLINE: "Bencina",
  DIESEL: "Diésel",
  ELECTRIC: "Eléctrico",
  HYBRID: "Híbrido",
  GAS: "Gas",
};

export function VehicleCard({ listing }: VehicleCardProps) {
  const { vehicle, source } = listing;
  const isDeal = listing.deltaPercentage < 0;

  return (
    <article className="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden group">
      {/* Image placeholder */}
      <div className="relative bg-slate-100 h-44 overflow-hidden">
        <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-1">
          <svg className="w-12 h-12 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9l2.45-4.9A2 2 0 017.24 3h9.52a2 2 0 011.8 1.1L21 9M3 9v9a2 2 0 002 2h14a2 2 0 002-2V9M3 9h18M9 17H7m10 0h-2" />
          </svg>
          <span className="text-xs font-medium opacity-40">Sin imagen</span>
        </div>
        {/* Source badge */}
        <div className="absolute top-2 left-2">
          <span className="bg-white/90 text-slate-600 text-xs font-medium px-2 py-1 rounded-md border border-slate-200">
            {source.name}
          </span>
        </div>
        {/* Opportunity badge */}
        <div className="absolute top-2 right-2">
          <OpportunityBadge score={listing.opportunityScore} size="sm" />
        </div>
      </div>

      {/* Content */}
      <div className="p-4 flex flex-col gap-3">
        {/* Title */}
        <div>
          <h3 className="font-semibold text-slate-900 text-base leading-tight group-hover:text-blue-600 transition-colors">
            {vehicle.brand} {vehicle.model}
          </h3>
          {vehicle.version && (
            <p className="text-sm text-slate-500 mt-0.5">{vehicle.version}</p>
          )}
        </div>

        {/* Meta */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-slate-600">
          <span className="font-medium">{vehicle.year}</span>
          <span>{formatKm(vehicle.mileage)}</span>
          <span>{TRANSMISSION_LABELS[vehicle.transmission]}</span>
          <span>{FUEL_LABELS[vehicle.fuelType]}</span>
        </div>

        <p className="text-xs text-slate-500 truncate">{vehicle.region}</p>

        {/* Pricing */}
        <div className="border-t border-slate-100 pt-3 flex flex-col gap-1">
          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold text-slate-900">
              {formatCLP(listing.listedPrice)}
            </span>
            <span
              className={`text-sm font-semibold ${isDeal ? "text-emerald-600" : "text-red-500"}`}
            >
              {formatPercentage(listing.deltaPercentage)}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Mercado estimado: {formatCLP(listing.marketEstimate)}</span>
          </div>
        </div>

        {/* CTA */}
        <Link
          href={`/autos/${listing.id}`}
          className="mt-1 w-full text-center text-sm font-medium bg-blue-600 text-white rounded-lg py-2.5 hover:bg-blue-700 active:bg-blue-800 transition-colors"
        >
          Ver detalle
        </Link>
      </div>
    </article>
  );
}
