import { Transmission, FuelType, OpportunityScore } from "@prisma/client";

export interface ScoringInput {
  brand: string;
  model: string;
  version?: string | null;
  year: number;
  mileage: number;
  transmission: Transmission;
  fuelType: FuelType;
  region: string;
  listedPrice: number;
}

export interface ComparableVehicle {
  brand: string;
  model: string;
  year: number;
  mileage: number;
  listedPrice: number;
}

export interface ScoringResult {
  marketEstimate: number;
  deltaAmount: number;
  deltaPercentage: number;
  opportunityScore: OpportunityScore;
  confidenceScore: number;
  explanation: string;
}

function getMileageMultiplier(mileage: number, baseMileage: number): number {
  const diff = mileage - baseMileage;
  // ~CLP 300 per km difference, normalized
  if (Math.abs(diff) < 10000) return 1.0;
  if (diff < 0) return 1 + Math.abs(diff) / 200000 * 0.15; // fewer km = higher value
  return 1 - diff / 200000 * 0.15; // more km = lower value
}

function getOpportunityScore(deltaPercentage: number): OpportunityScore {
  if (deltaPercentage <= -12) return "VERY_GOOD_DEAL";
  if (deltaPercentage <= -5) return "GOOD_DEAL";
  if (deltaPercentage < 5) return "FAIR_PRICE";
  return "OVERPRICED";
}

function getConfidenceScore(comparableCount: number, yearTolerance: number): number {
  if (comparableCount === 0) return 10;
  let base = Math.min(comparableCount * 10, 70);
  if (yearTolerance === 1) base += 20;
  else if (yearTolerance === 2) base += 10;
  else base += 5;
  return Math.min(base, 95);
}

function buildExplanation(
  comparableCount: number,
  deltaPercentage: number,
  opportunityScore: OpportunityScore,
  marketEstimate: number
): string {
  const fmtEstimate = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(marketEstimate);
  const absDelta = Math.abs(deltaPercentage).toFixed(1);

  if (comparableCount === 0) {
    return `Estimación basada en valores de referencia del mercado. No se encontraron comparables exactos.`;
  }

  switch (opportunityScore) {
    case "VERY_GOOD_DEAL":
      return `Precio ${absDelta}% bajo el mercado. Estimamos el valor justo en ${fmtEstimate} basado en ${comparableCount} autos similares. Oportunidad destacada.`;
    case "GOOD_DEAL":
      return `Precio ${absDelta}% bajo el mercado. Estimamos el valor justo en ${fmtEstimate} considerando ${comparableCount} comparables. Buen deal.`;
    case "FAIR_PRICE":
      return `Precio dentro del rango de mercado. Estimamos el valor justo en ${fmtEstimate} según ${comparableCount} autos similares.`;
    case "OVERPRICED":
      return `Precio ${absDelta}% sobre el mercado estimado de ${fmtEstimate}. Comparado con ${comparableCount} autos similares.`;
  }
}

export function calculateScore(
  input: ScoringInput,
  allListings: ComparableVehicle[]
): ScoringResult {
  const sameModel = allListings.filter(
    (v) =>
      v.brand.toLowerCase() === input.brand.toLowerCase() &&
      v.model.toLowerCase() === input.model.toLowerCase() &&
      v.listedPrice !== input.listedPrice
  );

  // Try progressively wider year tolerance
  let comparables: ComparableVehicle[] = [];
  let yearTolerance = 1;

  for (const tolerance of [1, 2, 3]) {
    comparables = sameModel.filter(
      (v) => Math.abs(v.year - input.year) <= tolerance
    );
    yearTolerance = tolerance;
    if (comparables.length >= 3) break;
  }

  if (comparables.length === 0) comparables = sameModel;

  // Apply mileage adjustment
  const avgMileage = comparables.length > 0
    ? comparables.reduce((s, v) => s + v.mileage, 0) / comparables.length
    : input.mileage;

  const adjustedPrices = comparables.map((v) => {
    const mult = getMileageMultiplier(input.mileage, v.mileage);
    return v.listedPrice * mult;
  });

  let marketEstimate: number;
  if (adjustedPrices.length === 0) {
    // Fallback: use brand-based estimate
    marketEstimate = input.listedPrice * 1.05;
  } else {
    const sorted = [...adjustedPrices].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    marketEstimate = sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
  }

  marketEstimate = Math.round(marketEstimate);
  const deltaAmount = input.listedPrice - marketEstimate;
  const deltaPercentage = (deltaAmount / marketEstimate) * 100;
  const opportunityScore = getOpportunityScore(deltaPercentage);
  const confidenceScore = getConfidenceScore(comparables.length, yearTolerance);
  const explanation = buildExplanation(comparables.length, deltaPercentage, opportunityScore, marketEstimate);

  return {
    marketEstimate,
    deltaAmount,
    deltaPercentage,
    opportunityScore,
    confidenceScore,
    explanation,
  };
}
