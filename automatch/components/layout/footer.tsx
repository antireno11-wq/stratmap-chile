import Link from "next/link";

export function Footer() {
  return (
    <footer className="bg-slate-900 text-slate-400 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
          {/* Brand */}
          <div className="col-span-1">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-7 h-7 bg-blue-500 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9l2.45-4.9A2 2 0 017.24 3h9.52a2 2 0 011.8 1.1L21 9M3 9v9a2 2 0 002 2h14a2 2 0 002-2V9M3 9h18" />
                </svg>
              </div>
              <span className="font-bold text-white">AutoMatch</span>
            </div>
            <p className="text-sm leading-relaxed">
              Encuentra el mejor match entre auto, precio y oportunidad.
            </p>
          </div>

          {/* Links */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3">Plataforma</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/buscar" className="hover:text-white transition-colors">Buscar autos</Link></li>
              <li><Link href="/#como-funciona" className="hover:text-white transition-colors">Cómo funciona</Link></li>
              <li><Link href="/#beneficios" className="hover:text-white transition-colors">Beneficios</Link></li>
            </ul>
          </div>

          {/* Note */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3">Sobre AutoMatch</h4>
            <p className="text-sm leading-relaxed">
              MVP v0.1 · Datos de ejemplo para Chile. Las estimaciones de precio son
              indicativas y basadas en comparables del mercado local.
            </p>
          </div>
        </div>

        <div className="border-t border-slate-800 mt-8 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
          <p>© 2024 AutoMatch · MVP · Solo datos de demostración</p>
          <Link href="/admin" className="text-slate-600 hover:text-slate-500 transition-colors">
            Admin
          </Link>
        </div>
      </div>
    </footer>
  );
}
