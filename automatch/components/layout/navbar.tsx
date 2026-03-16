"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-slate-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9l2.45-4.9A2 2 0 017.24 3h9.52a2 2 0 011.8 1.1L21 9M3 9v9a2 2 0 002 2h14a2 2 0 002-2V9M3 9h18" />
              </svg>
            </div>
            <span className="font-bold text-xl text-slate-900 tracking-tight">AutoMatch</span>
          </Link>

          {/* Nav */}
          <nav className="hidden sm:flex items-center gap-6">
            <Link
              href="/buscar"
              className={cn(
                "text-sm font-medium transition-colors",
                pathname.startsWith("/buscar")
                  ? "text-blue-600"
                  : "text-slate-600 hover:text-slate-900"
              )}
            >
              Buscar autos
            </Link>
            <Link
              href="/#como-funciona"
              className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
            >
              Cómo funciona
            </Link>
          </nav>

          {/* CTA */}
          <div className="flex items-center gap-3">
            <Link
              href="/buscar"
              className="hidden sm:inline-flex items-center text-sm font-medium bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Buscar autos
            </Link>
            {/* Mobile menu button */}
            <Link href="/buscar" className="sm:hidden text-slate-600 hover:text-slate-900">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
