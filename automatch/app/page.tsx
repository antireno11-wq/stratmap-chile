import Link from "next/link";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";

export default function LandingPage() {
  return (
    <>
      <Navbar />
      <main className="flex-1">
        {/* Hero */}
        <section className="bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 text-white py-24 px-4">
          <div className="max-w-4xl mx-auto text-center space-y-6">
            <div className="inline-flex items-center gap-2 bg-blue-500/20 border border-blue-400/30 text-blue-300 text-sm font-medium px-4 py-1.5 rounded-full mb-2">
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
              MVP · Datos de demostración para Chile
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight">
              Encuentra autos usados con{" "}
              <span className="text-blue-400">mejor precio relativo</span> del mercado
            </h1>
            <p className="text-xl text-slate-300 max-w-2xl mx-auto leading-relaxed">
              AutoMatch reúne el mercado, compara precios y te ayuda a detectar
              oportunidades reales — sin buscar en 10 páginas distintas.
            </p>

            {/* Search bar */}
            <form
              action="/buscar"
              method="get"
              className="flex flex-col sm:flex-row gap-3 max-w-xl mx-auto mt-8"
            >
              <input
                type="text"
                name="q"
                placeholder="Ej: Toyota Corolla, Mazda 3, Kia Sportage..."
                className="flex-1 rounded-xl border border-slate-600 bg-white/10 backdrop-blur text-white placeholder:text-slate-400 px-4 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-8 py-3.5 rounded-xl transition-colors whitespace-nowrap"
              >
                Buscar autos
              </button>
            </form>

            <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-slate-400 pt-2">
              <Link href="/buscar" className="hover:text-slate-300 transition-colors underline underline-offset-2">
                Ver cómo funciona ↓
              </Link>
              <span>·</span>
              <span>92+ publicaciones de 4 fuentes</span>
            </div>
          </div>
        </section>

        {/* Stats bar */}
        <section className="bg-white border-b border-slate-200 py-6">
          <div className="max-w-5xl mx-auto px-4 grid grid-cols-2 sm:grid-cols-4 gap-6">
            {[
              { value: "92+", label: "Publicaciones" },
              { value: "4", label: "Fuentes integradas" },
              { value: "15+", label: "Marcas disponibles" },
              { value: "CLP", label: "Precios en pesos" },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <p className="text-2xl font-bold text-slate-900">{stat.value}</p>
                <p className="text-sm text-slate-500 mt-0.5">{stat.label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="como-funciona" className="py-20 px-4 bg-slate-50">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-slate-900">Cómo funciona AutoMatch</h2>
              <p className="text-slate-600 mt-3 text-lg">
                Tres pasos para encontrar el mejor auto al mejor precio
              </p>
            </div>
            <div className="grid sm:grid-cols-3 gap-8">
              {[
                {
                  step: "01",
                  icon: "🔍",
                  title: "Busca y filtra",
                  description:
                    "Ingresa la marca, modelo o simplemente describe lo que buscas. Filtra por región, año, precio y más.",
                },
                {
                  step: "02",
                  icon: "📊",
                  title: "Compara precios",
                  description:
                    "AutoMatch calcula el precio de mercado estimado basado en comparables reales. Sabrás si el auto está sobre o bajo mercado.",
                },
                {
                  step: "03",
                  icon: "✉️",
                  title: "Envía tu oferta",
                  description:
                    "¿Encontraste un buen negocio? Envía una oferta directamente desde la plataforma con o sin financiamiento.",
                },
              ].map((item) => (
                <div
                  key={item.step}
                  className="bg-white rounded-2xl p-7 shadow-sm border border-slate-200 space-y-3"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{item.icon}</span>
                    <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded-md">
                      Paso {item.step}
                    </span>
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900">{item.title}</h3>
                  <p className="text-slate-600 text-sm leading-relaxed">{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Score examples */}
        <section className="py-20 px-4 bg-white">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-slate-900">Score de oportunidad</h2>
              <p className="text-slate-600 mt-3">
                Cada auto tiene un score basado en comparables del mercado
              </p>
            </div>
            <div className="grid sm:grid-cols-4 gap-4">
              {[
                {
                  badge: "🔥 Muy buen precio",
                  color: "bg-emerald-50 border-emerald-200",
                  textColor: "text-emerald-800",
                  desc: "Precio ≥ 12% bajo el mercado. Oportunidad destacada.",
                  delta: "−15%",
                },
                {
                  badge: "✅ Buen precio",
                  color: "bg-green-50 border-green-200",
                  textColor: "text-green-800",
                  desc: "Precio entre 5% y 12% bajo el mercado.",
                  delta: "−8%",
                },
                {
                  badge: "➡️ Precio justo",
                  color: "bg-blue-50 border-blue-200",
                  textColor: "text-blue-800",
                  desc: "Precio dentro del rango de mercado esperado.",
                  delta: "−2%",
                },
                {
                  badge: "⚠️ Sobre precio",
                  color: "bg-red-50 border-red-200",
                  textColor: "text-red-800",
                  desc: "Precio superior al estimado del mercado.",
                  delta: "+9%",
                },
              ].map((item) => (
                <div
                  key={item.badge}
                  className={`rounded-xl border p-5 space-y-2 ${item.color}`}
                >
                  <p className={`text-sm font-semibold ${item.textColor}`}>{item.badge}</p>
                  <p className={`text-2xl font-bold ${item.textColor}`}>{item.delta}</p>
                  <p className="text-slate-600 text-xs leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Benefits */}
        <section id="beneficios" className="py-20 px-4 bg-slate-50">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-slate-900">¿Por qué AutoMatch?</h2>
            </div>
            <div className="grid sm:grid-cols-3 gap-8">
              {[
                {
                  icon: "⏱️",
                  title: "Ahorra tiempo",
                  description:
                    "No más buscar en Chileautos, Yapo y Auto.cl por separado. Todo en un lugar.",
                },
                {
                  icon: "🎯",
                  title: "Precio fundamentado",
                  description:
                    "El precio estimado se basa en autos comparables reales, no en promedios genéricos.",
                },
                {
                  icon: "🛡️",
                  title: "Decide con confianza",
                  description:
                    "Sabes exactamente cuánto pagas de más o de menos antes de negociar.",
                },
              ].map((b) => (
                <div key={b.title} className="bg-white rounded-2xl p-7 shadow-sm border border-slate-200">
                  <div className="text-3xl mb-4">{b.icon}</div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">{b.title}</h3>
                  <p className="text-slate-600 text-sm leading-relaxed">{b.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-20 px-4 bg-blue-600">
          <div className="max-w-2xl mx-auto text-center space-y-6 text-white">
            <h2 className="text-3xl font-bold">¿Listo para encontrar tu próximo auto?</h2>
            <p className="text-blue-100 text-lg">
              Empieza ahora y descubre cuáles autos están realmente bajo mercado.
            </p>
            <Link
              href="/buscar"
              className="inline-flex items-center bg-white text-blue-700 font-semibold px-8 py-4 rounded-xl hover:bg-blue-50 transition-colors text-lg"
            >
              Buscar autos →
            </Link>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
