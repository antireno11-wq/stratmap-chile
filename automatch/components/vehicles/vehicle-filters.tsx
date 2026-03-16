"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback, useTransition } from "react";
import { CHILE_REGIONS, BRANDS } from "@/lib/utils";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const CURRENT_YEAR = new Date().getFullYear();

const YEAR_OPTIONS = Array.from({ length: 15 }, (_, i) => {
  const y = CURRENT_YEAR - i;
  return { value: String(y), label: String(y) };
});

const TRANSMISSION_OPTIONS = [
  { value: "MANUAL", label: "Manual" },
  { value: "AUTOMATIC", label: "Automático" },
  { value: "CVT", label: "CVT" },
];

const FUEL_OPTIONS = [
  { value: "GASOLINE", label: "Bencina" },
  { value: "DIESEL", label: "Diésel" },
  { value: "HYBRID", label: "Híbrido" },
  { value: "ELECTRIC", label: "Eléctrico" },
  { value: "GAS", label: "Gas" },
];

const SORT_OPTIONS = [
  { value: "opportunity", label: "Mejor oportunidad" },
  { value: "price_asc", label: "Menor precio" },
  { value: "price_desc", label: "Mayor precio" },
  { value: "year_desc", label: "Más nuevos" },
  { value: "mileage_asc", label: "Menor kilometraje" },
];

const REGION_OPTIONS = CHILE_REGIONS.map((r) => ({ value: r, label: r }));
const BRAND_OPTIONS = BRANDS.map((b) => ({ value: b, label: b }));

export function VehicleFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const get = (key: string) => searchParams.get(key) ?? "";

  const update = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      params.delete("page"); // reset pagination on filter change
      startTransition(() => {
        router.push(`${pathname}?${params.toString()}`);
      });
    },
    [router, pathname, searchParams]
  );

  const clearAll = () => {
    startTransition(() => {
      router.push(pathname);
    });
  };

  const hasFilters =
    get("brand") || get("model") || get("yearMin") || get("yearMax") ||
    get("priceMin") || get("priceMax") || get("mileageMax") || get("region") ||
    get("transmission") || get("fuelType");

  return (
    <aside className="bg-white rounded-xl border border-slate-200 p-5 space-y-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-slate-900 text-sm">Filtros</h2>
        {hasFilters && (
          <button
            onClick={clearAll}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            disabled={isPending}
          >
            Limpiar todo
          </button>
        )}
      </div>

      {/* Sort */}
      <Select
        label="Ordenar por"
        options={SORT_OPTIONS}
        value={get("sort") || "opportunity"}
        onChange={(e) => update("sort", e.target.value)}
      />

      {/* Brand */}
      <Select
        label="Marca"
        placeholder="Todas las marcas"
        options={BRAND_OPTIONS}
        value={get("brand")}
        onChange={(e) => update("brand", e.target.value)}
      />

      {/* Model */}
      <Input
        label="Modelo"
        placeholder="Ej: Corolla"
        value={get("model")}
        onChange={(e) => update("model", e.target.value)}
      />

      {/* Year range */}
      <div>
        <span className="text-sm font-medium text-slate-700 block mb-1.5">Año</span>
        <div className="flex gap-2">
          <Select
            placeholder="Desde"
            options={YEAR_OPTIONS}
            value={get("yearMin")}
            onChange={(e) => update("yearMin", e.target.value)}
            className="flex-1"
          />
          <Select
            placeholder="Hasta"
            options={YEAR_OPTIONS}
            value={get("yearMax")}
            onChange={(e) => update("yearMax", e.target.value)}
            className="flex-1"
          />
        </div>
      </div>

      {/* Price range */}
      <div>
        <span className="text-sm font-medium text-slate-700 block mb-1.5">Precio (CLP)</span>
        <div className="flex gap-2">
          <Input
            type="number"
            placeholder="Mínimo"
            value={get("priceMin")}
            onChange={(e) => update("priceMin", e.target.value)}
            className="flex-1"
          />
          <Input
            type="number"
            placeholder="Máximo"
            value={get("priceMax")}
            onChange={(e) => update("priceMax", e.target.value)}
            className="flex-1"
          />
        </div>
      </div>

      {/* Mileage */}
      <Input
        label="Km máximo"
        type="number"
        placeholder="Ej: 80000"
        value={get("mileageMax")}
        onChange={(e) => update("mileageMax", e.target.value)}
      />

      {/* Region */}
      <Select
        label="Región"
        placeholder="Todas las regiones"
        options={REGION_OPTIONS}
        value={get("region")}
        onChange={(e) => update("region", e.target.value)}
      />

      {/* Transmission */}
      <Select
        label="Transmisión"
        placeholder="Cualquiera"
        options={TRANSMISSION_OPTIONS}
        value={get("transmission")}
        onChange={(e) => update("transmission", e.target.value)}
      />

      {/* Fuel */}
      <Select
        label="Combustible"
        placeholder="Cualquiera"
        options={FUEL_OPTIONS}
        value={get("fuelType")}
        onChange={(e) => update("fuelType", e.target.value)}
      />

      {isPending && (
        <p className="text-xs text-slate-500 text-center">Actualizando...</p>
      )}
    </aside>
  );
}
