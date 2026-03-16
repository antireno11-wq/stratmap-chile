import type { Metadata } from "next";
import { getAdminStats } from "@/lib/admin";
import { OPPORTUNITY_LABELS } from "@/lib/utils";

export const metadata: Metadata = { title: "Dashboard" };

const STATUS_LABELS: Record<string, string> = {
  NEW: "Nuevas",
  CONTACTED: "Contactadas",
  NEGOTIATING: "En negociación",
  ACCEPTED: "Aceptadas",
  REJECTED: "Rechazadas",
};

const STATUS_COLORS: Record<string, string> = {
  NEW: "bg-blue-100 text-blue-800",
  CONTACTED: "bg-amber-100 text-amber-800",
  NEGOTIATING: "bg-purple-100 text-purple-800",
  ACCEPTED: "bg-emerald-100 text-emerald-800",
  REJECTED: "bg-red-100 text-red-800",
};

async function DashboardContent() {
  let stats;
  try {
    stats = await getAdminStats();
  } catch {
    return (
      <div className="p-8 text-center text-slate-500">
        No se pudo conectar a la base de datos. Verifica que la DB esté corriendo y el seed esté completo.
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Vista general del estado del sistema</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Vehículos", value: stats.totalVehicles, icon: "🚗" },
          { label: "Publicaciones", value: stats.totalListings, icon: "📋" },
          { label: "Ofertas", value: stats.totalOffers, icon: "✉️" },
          { label: "Fuentes", value: stats.totalSources, icon: "🔌" },
        ].map((kpi) => (
          <div
            key={kpi.label}
            className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm"
          >
            <div className="text-2xl mb-2">{kpi.icon}</div>
            <p className="text-3xl font-bold text-slate-900">{kpi.value}</p>
            <p className="text-sm text-slate-500 mt-1">{kpi.label}</p>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Offers by status */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="font-semibold text-slate-900 mb-4">Ofertas por estado</h2>
          <div className="space-y-2">
            {Object.entries(stats.offersByStatus).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between py-1.5">
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_COLORS[status] ?? "bg-slate-100 text-slate-700"}`}
                >
                  {STATUS_LABELS[status] ?? status}
                </span>
                <span className="text-sm font-bold text-slate-800">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Opportunity distribution */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="font-semibold text-slate-900 mb-4">Score de oportunidad</h2>
          <div className="space-y-2">
            {Object.entries(stats.opportunityDistribution).map(([score, count]) => (
              <div key={score} className="flex items-center justify-between py-1.5">
                <span className="text-sm text-slate-700">
                  {OPPORTUNITY_LABELS[score as keyof typeof OPPORTUNITY_LABELS] ?? score}
                </span>
                <span className="text-sm font-bold text-slate-800">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Delta note */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-700">
        <strong>Delta promedio:</strong> {stats.avgMarketDelta > 0 ? "+" : ""}{stats.avgMarketDelta}% vs. mercado estimado en todas las publicaciones activas.
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  return <DashboardContent />;
}
