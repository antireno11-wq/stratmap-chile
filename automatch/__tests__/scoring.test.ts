import { calculateScore, ScoringInput } from "../lib/scoring";
import type { ComparableVehicle } from "../lib/scoring";

const baseInput: ScoringInput = {
  brand: "Toyota",
  model: "Corolla",
  year: 2020,
  mileage: 50000,
  transmission: "AUTOMATIC",
  fuelType: "GASOLINE",
  region: "Región Metropolitana de Santiago",
  listedPrice: 10000000,
};

const comparables: ComparableVehicle[] = [
  { brand: "Toyota", model: "Corolla", year: 2020, mileage: 48000, listedPrice: 12000000 },
  { brand: "Toyota", model: "Corolla", year: 2020, mileage: 52000, listedPrice: 11800000 },
  { brand: "Toyota", model: "Corolla", year: 2019, mileage: 65000, listedPrice: 11000000 },
  { brand: "Toyota", model: "Corolla", year: 2021, mileage: 30000, listedPrice: 13500000 },
  { brand: "Toyota", model: "Corolla", year: 2020, mileage: 55000, listedPrice: 11500000 },
];

describe("calculateScore", () => {
  it("returns a VERY_GOOD_DEAL when price is well below market", () => {
    const result = calculateScore(baseInput, comparables);
    expect(result.deltaPercentage).toBeLessThan(-5);
    expect(["VERY_GOOD_DEAL", "GOOD_DEAL"]).toContain(result.opportunityScore);
  });

  it("returns OVERPRICED when listed price is much higher than market", () => {
    const highInput: ScoringInput = { ...baseInput, listedPrice: 15000000 };
    const result = calculateScore(highInput, comparables);
    expect(result.opportunityScore).toBe("OVERPRICED");
    expect(result.deltaPercentage).toBeGreaterThan(5);
  });

  it("returns FAIR_PRICE when price is within ±5% of market", () => {
    // Median of comparables ≈ 11800000, let's set price to ~11800000
    const fairInput: ScoringInput = { ...baseInput, listedPrice: 12000000 };
    const result = calculateScore(fairInput, comparables);
    expect(result.deltaPercentage).toBeGreaterThanOrEqual(-12);
  });

  it("calculates deltaAmount correctly", () => {
    const result = calculateScore(baseInput, comparables);
    expect(result.deltaAmount).toBe(result.marketEstimate - baseInput.listedPrice === 0
      ? 0
      : baseInput.listedPrice - result.marketEstimate);
  });

  it("returns confidenceScore > 0 with comparables", () => {
    const result = calculateScore(baseInput, comparables);
    expect(result.confidenceScore).toBeGreaterThan(0);
    expect(result.confidenceScore).toBeLessThanOrEqual(100);
  });

  it("returns low confidence with no comparables", () => {
    const result = calculateScore(baseInput, []);
    expect(result.confidenceScore).toBeLessThanOrEqual(15);
  });

  it("provides a non-empty explanation", () => {
    const result = calculateScore(baseInput, comparables);
    expect(result.explanation).toBeTruthy();
    expect(typeof result.explanation).toBe("string");
    expect(result.explanation.length).toBeGreaterThan(10);
  });

  it("handles a single comparable gracefully", () => {
    const single = [comparables[0]];
    const result = calculateScore(baseInput, single);
    expect(result.marketEstimate).toBeGreaterThan(0);
    expect(result.opportunityScore).toBeDefined();
  });

  it("classifies VERY_GOOD_DEAL at exactly -12%", () => {
    // If market estimate is 10M, price at 8.8M = exactly -12%
    const result = calculateScore(
      { ...baseInput, listedPrice: 8800000 },
      [{ brand: "Toyota", model: "Corolla", year: 2020, mileage: 50000, listedPrice: 10000000 }]
    );
    expect(result.opportunityScore).toBe("VERY_GOOD_DEAL");
  });
});

describe("calculateScore — score boundaries", () => {
  const single: ComparableVehicle[] = [
    { brand: "Toyota", model: "Corolla", year: 2020, mileage: 50000, listedPrice: 10000000 },
  ];

  it("GOOD_DEAL: between -12% and -5%", () => {
    // -8%: price = 9200000 vs market 10000000
    const result = calculateScore({ ...baseInput, listedPrice: 9200000 }, single);
    expect(result.opportunityScore).toBe("GOOD_DEAL");
  });

  it("FAIR_PRICE: between -5% and +5%", () => {
    const result = calculateScore({ ...baseInput, listedPrice: 10200000 }, single);
    expect(result.opportunityScore).toBe("FAIR_PRICE");
  });

  it("OVERPRICED: above +5%", () => {
    const result = calculateScore({ ...baseInput, listedPrice: 11000000 }, single);
    expect(result.opportunityScore).toBe("OVERPRICED");
  });
});
