import type { Metadata } from "next";
import Link from "next/link";
import { getAdminVehicles } from "@/lib/admin";
import { formatCLP, formatKm, OPPORTUNITY_COLORS, OPPORTUNITY_LABELS } from "@/lib/utils";

export const metadata: Metadata = { title: "Autos" };

interface PageProps {
  searchParams: Promise<{ page?: string }>;
}

export default async function AdminVehiclesPage({ searchParams }: PageProps) {
  const { page: pageStr } = await searchParams;
  const page = pageStr ? parseInt(pageStr) : 1;

  let result;
  try {
    result = await getAdminVehicles({ page, pageSize: 25 });
  } catch {
    return (
      <div className="p-8 text-slate-500 text-center">
        Error al cargar vehículos. Verifica la conexión a la DB.
      </div>
    );
  }

  const { data, total, totalPages } = result;

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Autos</h1>
          <p className="text-slate-500 text-sm mt-1">{total} vehículos en el sistema</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Vehículo</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Año</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Km</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Región</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Precio</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Score</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Fuente</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Ofertas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((v) => {
                const listing = v.listings[0];
                return (
                  <tr key={v.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-medium text-slate-900">
                          {v.brand} {v.model}
                        </p>
                        {v.version && (
                          <p className="text-xs text-slate-500">{v.version}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{v.year}</td>
                    <td className="px-4 py-3 text-slate-700">{formatKm(v.mileage)}</td>
                    <td className="px-4 py-3 text-slate-600 text-xs max-w-32 truncate">
                      {v.region}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {listing ? formatCLP(listing.listedPrice) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {listing ? (
                        <span
                          className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${OPPORTUNITY_COLORS[listing.opportunityScore]}`}
                        >
                          {OPPORTUNITY_LABELS[listing.opportunityScore]}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">
                      {listing?.source?.name ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full">
                        {v._count.offers}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {data.length === 0 && (
          <div className="text-center py-12 text-slate-500">
            No hay vehículos. Corre el seed: <code className="bg-slate-100 px-1 rounded text-xs">npx prisma db seed</code>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          {page > 1 && (
            <Link
              href={`/admin/autos?page=${page - 1}`}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-100"
            >
              ← Anterior
            </Link>
          )}
          <span className="text-sm text-slate-600">
            Pág. {page} / {totalPages}
          </span>
          {page < totalPages && (
            <Link
              href={`/admin/autos?page=${page + 1}`}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-100"
            >
              Siguiente →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
