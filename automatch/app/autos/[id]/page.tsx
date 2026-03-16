import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import { OpportunityBadge } from "@/components/vehicles/opportunity-badge";
import { VehicleCard } from "@/components/vehicles/vehicle-card";
import { OfferForm } from "@/components/offers/offer-form";
import { getListingById, getSimilarListings } from "@/lib/vehicles";
import { formatCLP, formatKm, formatPercentage } from "@/lib/utils";

interface PageProps {
  params: Promise<{ id: string }>;
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

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const listing = await getListingById(id);
  if (!listing) return { title: "Auto no encontrado" };

  const v = listing.vehicle;
  return {
    title: `${v.brand} ${v.model} ${v.year} — ${formatCLP(listing.listedPrice)}`,
    description: `${v.brand} ${v.model} ${v.version ?? ""} ${v.year}, ${formatKm(v.mileage)}, ${v.region}. Precio: ${formatCLP(listing.listedPrice)}.`,
  };
}

export default async function AutoDetailPage({ params }: PageProps) {
  const { id } = await params;
  const listing = await getListingById(id).catch(() => null);

  if (!listing) notFound();

  const { vehicle: v, source } = listing;
  const isDeal = listing.deltaPercentage < 0;
  const similar = await getSimilarListings(listing.id, v.brand, v.model, v.year).catch(() => []);

  return (
    <>
      <Navbar />
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-slate-500 mb-6 flex items-center gap-2">
          <Link href="/buscar" className="hover:text-blue-600 transition-colors">
            Buscar
          </Link>
          <span>›</span>
          <Link href={`/buscar?brand=${v.brand}`} className="hover:text-blue-600 transition-colors">
            {v.brand}
          </Link>
          <span>›</span>
          <span className="text-slate-700">{v.model}</span>
        </nav>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Left: images + details */}
          <div className="lg:col-span-2 space-y-6">
            {/* Image gallery placeholder */}
            <div className="bg-slate-100 rounded-2xl h-72 flex flex-col items-center justify-center text-slate-400 gap-2 border border-slate-200">
              <svg className="w-16 h-16 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 9l2.45-4.9A2 2 0 017.24 3h9.52a2 2 0 011.8 1.1L21 9M3 9v9a2 2 0 002 2h14a2 2 0 002-2V9M3 9h18M9 17H7m10 0h-2" />
              </svg>
              <p className="text-sm opacity-50">Galería de imágenes no disponible</p>
              <p className="text-xs opacity-40">Las imágenes reales se mostrarán al conectar fuentes</p>
            </div>

            {/* Vehicle info */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
              <div>
                <div className="flex flex-wrap gap-2 mb-3">
                  <OpportunityBadge score={listing.opportunityScore} size="md" />
                  <span className="bg-slate-100 text-slate-600 text-xs font-medium px-2.5 py-1 rounded-full border border-slate-200">
                    {source.name}
                  </span>
                </div>
                <h1 className="text-2xl font-bold text-slate-900">
                  {v.brand} {v.model} {v.version && <span className="text-slate-500 font-medium">{v.version}</span>}
                </h1>
                <p className="text-slate-600 mt-1">{v.year} · {v.region}</p>
              </div>

              {/* Attributes table */}
              <div className="border-t border-slate-100 pt-4">
                <h2 className="font-semibold text-slate-900 mb-3">Características</h2>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
                  {[
                    { label: "Año", value: v.year },
                    { label: "Kilometraje", value: formatKm(v.mileage) },
                    { label: "Transmisión", value: TRANSMISSION_LABELS[v.transmission] },
                    { label: "Combustible", value: FUEL_LABELS[v.fuelType] },
                    { label: "Región", value: v.region },
                    ...(v.comuna ? [{ label: "Comuna", value: v.comuna }] : []),
                    ...(v.color ? [{ label: "Color", value: v.color }] : []),
                    ...(v.doors ? [{ label: "Puertas", value: v.doors }] : []),
                    ...(v.engineCC ? [{ label: "Motor", value: `${v.engineCC} cc` }] : []),
                  ].map(({ label, value }) => (
                    <div key={label} className="flex flex-col gap-0.5">
                      <dt className="text-xs text-slate-500 uppercase tracking-wide">{label}</dt>
                      <dd className="text-sm font-medium text-slate-800">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              {/* Source */}
              {listing.originalUrl && (
                <div className="border-t border-slate-100 pt-4">
                  <p className="text-sm text-slate-500">
                    Publicado en{" "}
                    <a
                      href={listing.originalUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline font-medium"
                    >
                      {source.name}
                    </a>
                    {" "}(URL de ejemplo)
                  </p>
                </div>
              )}

              {/* Score explanation */}
              {listing.scoreExplanation && (
                <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
                  <h3 className="text-sm font-semibold text-slate-700 mb-1.5">Análisis de precio</h3>
                  <p className="text-sm text-slate-600 leading-relaxed">{listing.scoreExplanation}</p>
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Nivel de confianza: {listing.confidenceScore}/100
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: price card + offer form */}
          <div className="space-y-5">
            {/* Price card */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4 sticky top-20">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Precio publicado</p>
                <p className="text-3xl font-bold text-slate-900">{formatCLP(listing.listedPrice)}</p>
              </div>

              <div className="bg-slate-50 rounded-xl p-4 space-y-2 border border-slate-200">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">Estimado mercado</span>
                  <span className="font-semibold text-slate-800">{formatCLP(listing.marketEstimate)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">Diferencia</span>
                  <span className={`font-semibold ${isDeal ? "text-emerald-600" : "text-red-500"}`}>
                    {isDeal ? "" : "+"}{formatCLP(listing.deltaAmount)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">vs. mercado</span>
                  <span className={`font-bold text-base ${isDeal ? "text-emerald-600" : "text-red-500"}`}>
                    {formatPercentage(listing.deltaPercentage)}
                  </span>
                </div>
              </div>

              <div className="border-t border-slate-100 pt-3">
                <OpportunityBadge score={listing.opportunityScore} size="lg" className="w-full justify-center" />
              </div>
            </div>

            {/* Offer form */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h2 className="font-semibold text-slate-900 text-lg mb-4">Enviar oferta</h2>
              <OfferForm
                vehicleId={v.id}
                listingId={listing.id}
                listedPrice={listing.listedPrice}
              />
            </div>
          </div>
        </div>

        {/* Similar vehicles */}
        {similar.length > 0 && (
          <section className="mt-12">
            <h2 className="text-xl font-bold text-slate-900 mb-6">
              Autos similares — {v.brand} {v.model}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {similar.map((s) => (
                <VehicleCard key={s.id} listing={s} />
              ))}
            </div>
          </section>
        )}
      </main>
      <Footer />
    </>
  );
}
