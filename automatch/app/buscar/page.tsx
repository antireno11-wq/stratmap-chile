import type { Metadata } from "next";
import { Suspense } from "react";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import { VehicleFilters } from "@/components/vehicles/vehicle-filters";
import { VehicleCard } from "@/components/vehicles/vehicle-card";
import { searchListings } from "@/lib/vehicles";
import type { VehicleSearchParams } from "@/types";
import { PageSpinner } from "@/components/ui/spinner";

export const metadata: Metadata = {
  title: "Buscar autos",
  description: "Busca autos usados en Chile y compara precios con el mercado.",
};

interface PageProps {
  searchParams: Promise<Record<string, string | undefined>>;
}

async function Results({ searchParams }: { searchParams: Record<string, string | undefined> }) {
  const params: VehicleSearchParams = {
    q: searchParams.q,
    brand: searchParams.brand,
    model: searchParams.model,
    yearMin: searchParams.yearMin ? parseInt(searchParams.yearMin) : undefined,
    yearMax: searchParams.yearMax ? parseInt(searchParams.yearMax) : undefined,
    priceMin: searchParams.priceMin ? parseInt(searchParams.priceMin) : undefined,
    priceMax: searchParams.priceMax ? parseInt(searchParams.priceMax) : undefined,
    mileageMax: searchParams.mileageMax ? parseInt(searchParams.mileageMax) : undefined,
    region: searchParams.region,
    transmission: searchParams.transmission,
    fuelType: searchParams.fuelType,
    sort: (searchParams.sort as VehicleSearchParams["sort"]) ?? "opportunity",
    page: searchParams.page ? parseInt(searchParams.page) : 1,
    pageSize: 20,
  };

  let result;
  try {
    result = await searchListings(params);
  } catch {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
        <div className="text-4xl">⚠️</div>
        <p className="text-slate-700 font-semibold">No se pudo conectar a la base de datos</p>
        <p className="text-slate-500 text-sm max-w-sm">
          Asegúrate de haber corrido las migraciones y el seed.{" "}
          <code className="bg-slate-100 px-1 rounded text-xs">npx prisma migrate dev && npx prisma db seed</code>
        </p>
      </div>
    );
  }

  const { data, total, totalPages, page } = result;
  const currentPage = page ?? 1;

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
        <div className="text-5xl">🔍</div>
        <p className="text-slate-700 font-semibold text-lg">Sin resultados</p>
        <p className="text-slate-500">
          No encontramos autos con esos filtros. Intenta ampliar tu búsqueda.
        </p>
      </div>
    );
  }

  const buildPageUrl = (p: number) => {
    const sp = new URLSearchParams(
      Object.entries(searchParams).filter(([, v]) => v !== undefined) as [string, string][]
    );
    sp.set("page", String(p));
    return `/buscar?${sp.toString()}`;
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500">
        <span className="font-semibold text-slate-700">{total}</span> publicaciones encontradas
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
        {data.map((listing) => (
          <VehicleCard key={listing.id} listing={listing} />
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-6">
          {currentPage > 1 && (
            <a
              href={buildPageUrl(currentPage - 1)}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-100 transition-colors"
            >
              ← Anterior
            </a>
          )}
          <span className="text-sm text-slate-600 px-4">
            Página {currentPage} de {totalPages}
          </span>
          {currentPage < totalPages && (
            <a
              href={buildPageUrl(currentPage + 1)}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-100 transition-colors"
            >
              Siguiente →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export default async function BuscarPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const q = sp.q ?? "";

  return (
    <>
      <Navbar />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">
            {q ? `Resultados para "${q}"` : "Buscar autos usados"}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Compara precios de mercado y detecta las mejores oportunidades
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar filters */}
          <div className="w-full lg:w-72 shrink-0">
            <Suspense fallback={<div className="bg-white rounded-xl border p-5 animate-pulse h-96" />}>
              <VehicleFilters />
            </Suspense>
          </div>

          {/* Results */}
          <div className="flex-1 min-w-0">
            <Suspense fallback={<PageSpinner />}>
              <Results searchParams={sp} />
            </Suspense>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
