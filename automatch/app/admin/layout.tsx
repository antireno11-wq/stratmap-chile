import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: {
    default: "Admin",
    template: "%s | Admin — AutoMatch",
  },
};

const NAV_ITEMS = [
  { href: "/admin", label: "Dashboard", icon: "📊" },
  { href: "/admin/autos", label: "Autos", icon: "🚗" },
  { href: "/admin/ofertas", label: "Ofertas", icon: "✉️" },
  { href: "/admin/fuentes", label: "Fuentes", icon: "🔌" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex bg-slate-50">
      {/* Sidebar */}
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-5 border-b border-slate-200">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9l2.45-4.9A2 2 0 017.24 3h9.52a2 2 0 011.8 1.1L21 9M3 9v9a2 2 0 002 2h14a2 2 0 002-2V9M3 9h18" />
              </svg>
            </div>
            <span className="font-bold text-slate-900">AutoMatch</span>
          </Link>
          <p className="text-xs text-slate-500 mt-1 ml-9">Panel Admin</p>
        </div>

        <nav className="p-3 flex-1">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-2.5 px-3 py-2.5 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-lg transition-colors"
            >
              <span>{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-200 space-y-2">
          <Link
            href="/"
            className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors"
          >
            ← Volver al sitio
          </Link>
          <form action="/api/admin/login" method="DELETE">
            <a
              href="/api/admin/login"
              onClick={async (e) => {
                e.preventDefault();
                await fetch("/api/admin/login", { method: "DELETE" });
                window.location.href = "/admin/login";
              }}
              className="text-xs text-slate-400 hover:text-red-500 cursor-pointer transition-colors"
            >
              Cerrar sesión
            </a>
          </form>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}
