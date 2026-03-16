import type { Metadata } from "next";
import { getAdminSources } from "@/lib/admin";

export const metadata: Metadata = { title: "Fuentes" };

export default async function AdminFuentesPage() {
  let sources: Awaited<ReturnType<typeof getAdminSources>>;
  try {
    sources = await getAdminSources();
  } catch {
    return (
      <div className="p-8 text-slate-500 text-center">
        Error al cargar fuentes.
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Fuentes</h1>
        <p className="text-slate-500 text-sm mt-1">
          Orígenes de datos integrados. Para conectar fuentes reales, implementa el provider correspondiente en{" "}
          <code className="bg-slate-100 px-1 rounded text-xs">/sources/[slug]/index.ts</code>
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        {sources.map((source) => (
          <div
            key={source.id}
            className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3"
          >
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-slate-900">{source.name}</h2>
              <span
                className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                  source.active
                    ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                    : "bg-slate-100 text-slate-600 border-slate-200"
                }`}
              >
                {source.active ? "Activa" : "Inactiva"}
              </span>
            </div>

            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <dt className="text-slate-500">Slug</dt>
                <dd className="font-mono text-slate-700 text-xs bg-slate-100 px-1.5 py-0.5 rounded">
                  {source.slug}
                </dd>
              </div>
              {source.baseUrl && (
                <div className="flex justify-between">
                  <dt className="text-slate-500">URL base</dt>
                  <dd className="text-slate-700 text-xs truncate max-w-40">{source.baseUrl}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-slate-500">Publicaciones</dt>
                <dd className="font-semibold text-slate-900">
                  {(source as { _count?: { listings?: number } })._count?.listings ?? 0}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Modo</dt>
                <dd className="text-amber-700 font-medium text-xs bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  Mock
                </dd>
              </div>
            </dl>

            <div className="bg-slate-50 rounded-lg p-3 text-xs text-slate-600 border border-slate-200">
              <p className="font-medium mb-1">Para conectar la fuente real:</p>
              <code className="text-slate-700">
                sources/{source.slug}/index.ts → implementar fetchListings()
              </code>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 space-y-2 text-sm">
        <h3 className="font-semibold text-blue-900">Arquitectura de providers</h3>
        <p className="text-blue-700">
          Cada fuente implementa la interfaz <code className="bg-blue-100 px-1 rounded">BaseProvider</code>.
          Para conectar datos reales, implementa <code className="bg-blue-100 px-1 rounded">fetchListings()</code> en
          el provider correspondiente. Los datos se normalizan automáticamente y se calculan los scores.
        </p>
        <p className="text-blue-600 text-xs">
          Ver: <code>/sources/base.ts</code> para la interfaz base.
        </p>
      </div>
    </div>
  );
}
