import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { OpportunityScore } from "@prisma/client";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCLP(amount: number): string {
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatKm(km: number): string {
  return new Intl.NumberFormat("es-CL").format(km) + " km";
}

export function formatPercentage(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export const OPPORTUNITY_LABELS: Record<OpportunityScore, string> = {
  VERY_GOOD_DEAL: "Muy buen precio",
  GOOD_DEAL: "Buen precio",
  FAIR_PRICE: "Precio justo",
  OVERPRICED: "Sobre precio",
};

export const OPPORTUNITY_COLORS: Record<OpportunityScore, string> = {
  VERY_GOOD_DEAL: "bg-emerald-100 text-emerald-800 border-emerald-200",
  GOOD_DEAL: "bg-green-100 text-green-800 border-green-200",
  FAIR_PRICE: "bg-blue-100 text-blue-800 border-blue-200",
  OVERPRICED: "bg-red-100 text-red-800 border-red-200",
};

export const CHILE_REGIONS = [
  "Región de Arica y Parinacota",
  "Región de Tarapacá",
  "Región de Antofagasta",
  "Región de Atacama",
  "Región de Coquimbo",
  "Región de Valparaíso",
  "Región Metropolitana de Santiago",
  "Región del Libertador General Bernardo O'Higgins",
  "Región del Maule",
  "Región de Ñuble",
  "Región del Biobío",
  "Región de La Araucanía",
  "Región de Los Ríos",
  "Región de Los Lagos",
  "Región de Aysén del General Carlos Ibáñez del Campo",
  "Región de Magallanes y de la Antártica Chilena",
];

export const BRANDS = [
  "Suzuki", "Toyota", "Hyundai", "Kia", "Mazda",
  "Chevrolet", "Nissan", "Peugeot", "Volkswagen", "Ford",
  "Honda", "Mitsubishi", "Subaru", "Renault", "Jeep",
];
