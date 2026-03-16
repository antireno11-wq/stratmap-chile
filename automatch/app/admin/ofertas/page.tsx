"use client";

import { useState, useEffect, useCallback } from "react";
import { formatCLP } from "@/lib/utils";

type OfferStatus = "NEW" | "CONTACTED" | "NEGOTIATING" | "ACCEPTED" | "REJECTED";

interface Offer {
  id: string;
  name: string;
  email: string;
  phone: string;
  offerAmount: number;
  financing: boolean;
  message?: string | null;
  status: OfferStatus;
  createdAt: string;
  vehicle: { brand: string; model: string; year: number };
}

const STATUS_LABELS: Record<OfferStatus, string> = {
  NEW: "Nueva",
  CONTACTED: "Contactado",
  NEGOTIATING: "Negociando",
  ACCEPTED: "Aceptada",
  REJECTED: "Rechazada",
};

const STATUS_COLORS: Record<OfferStatus, string> = {
  NEW: "bg-blue-100 text-blue-800 border-blue-200",
  CONTACTED: "bg-amber-100 text-amber-800 border-amber-200",
  NEGOTIATING: "bg-purple-100 text-purple-800 border-purple-200",
  ACCEPTED: "bg-emerald-100 text-emerald-800 border-emerald-200",
  REJECTED: "bg-red-100 text-red-800 border-red-200",
};

const ALL_STATUSES: OfferStatus[] = ["NEW", "CONTACTED", "NEGOTIATING", "ACCEPTED", "REJECTED"];

export default function AdminOfertasPage() {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<OfferStatus | "">("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [updating, setUpdating] = useState<string | null>(null);

  const fetchOffers = useCallback(async () => {
    setLoading(true);
    try {
      const sp = new URLSearchParams();
      if (filterStatus) sp.set("status", filterStatus);
      sp.set("page", String(page));
      const res = await fetch(`/api/admin/offers?${sp.toString()}`);
      const data = await res.json();
      setOffers(data.data ?? []);
      setTotal(data.total ?? 0);
      setTotalPages(data.totalPages ?? 1);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, page]);

  useEffect(() => { fetchOffers(); }, [fetchOffers]);

  const updateStatus = async (offerId: string, status: OfferStatus) => {
    setUpdating(offerId);
    try {
      await fetch(`/api/admin/offers/${offerId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await fetchOffers();
    } finally {
      setUpdating(null);
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ofertas</h1>
          <p className="text-slate-500 text-sm mt-1">{total} ofertas totales</p>
        </div>

        {/* Filter by status */}
        <select
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value as OfferStatus | ""); setPage(1); }}
          className="text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Todos los estados</option>
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="text-center py-12 text-slate-500">Cargando...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Auto</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Contacto</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Monto</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Financ.</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Fecha</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Estado</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {offers.map((offer) => (
                  <tr key={offer.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">
                        {offer.vehicle.brand} {offer.vehicle.model}
                      </p>
                      <p className="text-xs text-slate-500">{offer.vehicle.year}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{offer.name}</p>
                      <p className="text-xs text-slate-500">{offer.email}</p>
                      <p className="text-xs text-slate-500">{offer.phone}</p>
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      {formatCLP(offer.offerAmount)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {offer.financing ? (
                        <span className="text-emerald-600 font-medium text-xs">Sí</span>
                      ) : (
                        <span className="text-slate-400 text-xs">No</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {new Date(offer.createdAt).toLocaleDateString("es-CL")}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${STATUS_COLORS[offer.status]}`}
                      >
                        {STATUS_LABELS[offer.status]}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={offer.status}
                        disabled={updating === offer.id}
                        onChange={(e) => updateStatus(offer.id, e.target.value as OfferStatus)}
                        className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                      >
                        {ALL_STATUSES.map((s) => (
                          <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {offers.length === 0 && (
              <div className="text-center py-12 text-slate-500">
                No hay ofertas aún.
              </div>
            )}
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          {page > 1 && (
            <button
              onClick={() => setPage(p => p - 1)}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-100"
            >
              ← Anterior
            </button>
          )}
          <span className="text-sm text-slate-600">Pág. {page} / {totalPages}</span>
          {page < totalPages && (
            <button
              onClick={() => setPage(p => p + 1)}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-100"
            >
              Siguiente →
            </button>
          )}
        </div>
      )}
    </div>
  );
}
