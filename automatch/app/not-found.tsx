import Link from "next/link";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";

export default function NotFound() {
  return (
    <>
      <Navbar />
      <main className="flex-1 flex items-center justify-center px-4 py-24">
        <div className="text-center space-y-5">
          <p className="text-7xl font-bold text-slate-200">404</p>
          <h1 className="text-2xl font-bold text-slate-900">Página no encontrada</h1>
          <p className="text-slate-500">
            El auto o la página que buscas no existe o fue removida.
          </p>
          <Link
            href="/buscar"
            className="inline-flex bg-blue-600 text-white font-medium px-6 py-3 rounded-xl hover:bg-blue-700 transition-colors"
          >
            Volver a buscar
          </Link>
        </div>
      </main>
      <Footer />
    </>
  );
}
