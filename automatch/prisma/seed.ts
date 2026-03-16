import { PrismaClient, Transmission, FuelType, OpportunityScore } from "@prisma/client";
import { calculateScore, ComparableVehicle } from "../lib/scoring";

const prisma = new PrismaClient();

// ────────────────────────────────────────────────────────────────
// Raw vehicle definitions (no IDs yet, we'll create them in DB)
// ────────────────────────────────────────────────────────────────
interface RawVehicle {
  brand: string;
  model: string;
  version?: string;
  year: number;
  mileage: number;
  price: number;
  transmission: Transmission;
  fuelType: FuelType;
  region: string;
  color?: string;
  doors?: number;
  engineCC?: number;
}

const rawVehicles: RawVehicle[] = [
  // ── Toyota Corolla (8) ──────────────────────────────────────
  { brand: "Toyota", model: "Corolla", version: "1.8 XEI AT", year: 2022, mileage: 18000, price: 14500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1800 },
  { brand: "Toyota", model: "Corolla", version: "1.8 XLI AT", year: 2021, mileage: 32000, price: 12800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 1800 },
  { brand: "Toyota", model: "Corolla", version: "1.8 XEI AT", year: 2021, mileage: 28000, price: 13200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Negro", doors: 4, engineCC: 1800 },
  { brand: "Toyota", model: "Corolla", version: "1.8 XLI MT", year: 2020, mileage: 45000, price: 11500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 1800 },
  { brand: "Toyota", model: "Corolla", version: "1.8 XEI AT", year: 2020, mileage: 52000, price: 9200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 1800 }, // VERY_GOOD_DEAL
  { brand: "Toyota", model: "Corolla", version: "1.8 XLI MT", year: 2019, mileage: 68000, price: 10500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de La Araucanía", color: "Plata", doors: 4, engineCC: 1800 },
  { brand: "Toyota", model: "Corolla", version: "1.6 GLI MT", year: 2018, mileage: 82000, price: 8900000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Blanco", doors: 4, engineCC: 1600 },
  { brand: "Toyota", model: "Corolla", version: "1.8 XEI AT", year: 2018, mileage: 75000, price: 9800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Gris", doors: 4, engineCC: 1800 },

  // ── Toyota Hilux (6) ────────────────────────────────────────
  { brand: "Toyota", model: "Hilux", version: "2.8 SRV 4x4 AT", year: 2022, mileage: 22000, price: 31000000, transmission: "AUTOMATIC", fuelType: "DIESEL", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2800 },
  { brand: "Toyota", model: "Hilux", version: "2.4 SR 4x2 AT", year: 2021, mileage: 38000, price: 27500000, transmission: "AUTOMATIC", fuelType: "DIESEL", region: "Región de Antofagasta", color: "Plata", doors: 4, engineCC: 2400 },
  { brand: "Toyota", model: "Hilux", version: "2.4 SR 4x2 MT", year: 2020, mileage: 55000, price: 24000000, transmission: "MANUAL", fuelType: "DIESEL", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 2400 },
  { brand: "Toyota", model: "Hilux", version: "2.8 SRV 4x4 AT", year: 2020, mileage: 48000, price: 25500000, transmission: "AUTOMATIC", fuelType: "DIESEL", region: "Región Metropolitana de Santiago", color: "Negro", doors: 4, engineCC: 2800 },
  { brand: "Toyota", model: "Hilux", version: "2.4 DX 4x2 MT", year: 2019, mileage: 72000, price: 22000000, transmission: "MANUAL", fuelType: "DIESEL", region: "Región de La Araucanía", color: "Blanco", doors: 4, engineCC: 2400 },
  { brand: "Toyota", model: "Hilux", version: "2.4 SR 4x2 AT", year: 2018, mileage: 89000, price: 23500000, transmission: "AUTOMATIC", fuelType: "DIESEL", region: "Región de Los Lagos", color: "Plata", doors: 4, engineCC: 2400 }, // OVERPRICED

  // ── Toyota RAV4 (5) ─────────────────────────────────────────
  { brand: "Toyota", model: "RAV4", version: "2.5 XLE AWD CVT", year: 2022, mileage: 20000, price: 25000000, transmission: "CVT", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2500 },
  { brand: "Toyota", model: "RAV4", version: "2.0 VX FWD AT", year: 2021, mileage: 35000, price: 23000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Toyota", model: "RAV4", version: "2.0 VX FWD AT", year: 2020, mileage: 50000, price: 20500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Azul", doors: 4, engineCC: 2000 },
  { brand: "Toyota", model: "RAV4", version: "2.0 VX FWD AT", year: 2020, mileage: 55000, price: 16800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2000 }, // VERY_GOOD_DEAL
  { brand: "Toyota", model: "RAV4", version: "2.0 VX FWD AT", year: 2019, mileage: 68000, price: 19000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región de Coquimbo", color: "Plata", doors: 4, engineCC: 2000 },

  // ── Hyundai Accent (7) ──────────────────────────────────────
  { brand: "Hyundai", model: "Accent", version: "1.4 GL AT", year: 2021, mileage: 25000, price: 10500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1400 },
  { brand: "Hyundai", model: "Accent", version: "1.4 GL MT", year: 2021, mileage: 30000, price: 9800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 1400 },
  { brand: "Hyundai", model: "Accent", version: "1.4 GL AT", year: 2020, mileage: 42000, price: 9200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Azul", doors: 4, engineCC: 1400 },
  { brand: "Hyundai", model: "Accent", version: "1.4 GL MT", year: 2019, mileage: 58000, price: 8100000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 1400 },
  { brand: "Hyundai", model: "Accent", version: "1.4 GL MT", year: 2019, mileage: 61000, price: 7200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 1400 }, // GOOD_DEAL
  { brand: "Hyundai", model: "Accent", version: "1.4 GL MT", year: 2018, mileage: 74000, price: 7000000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Plata", doors: 4, engineCC: 1400 },
  { brand: "Hyundai", model: "Accent", version: "1.4 GL MT", year: 2017, mileage: 88000, price: 5800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de La Araucanía", color: "Blanco", doors: 4, engineCC: 1400 },

  // ── Hyundai Tucson (5) ──────────────────────────────────────
  { brand: "Hyundai", model: "Tucson", version: "2.0 GL FWD AT", year: 2022, mileage: 18000, price: 22500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2000 },
  { brand: "Hyundai", model: "Tucson", version: "2.0 GL FWD AT", year: 2021, mileage: 32000, price: 20000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Hyundai", model: "Tucson", version: "2.0 GLS FWD AT", year: 2020, mileage: 48000, price: 18000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Plata", doors: 4, engineCC: 2000 },
  { brand: "Hyundai", model: "Tucson", version: "2.0 GL FWD AT", year: 2020, mileage: 52000, price: 15200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Negro", doors: 4, engineCC: 2000 }, // VERY_GOOD_DEAL
  { brand: "Hyundai", model: "Tucson", version: "2.0 GL 4WD MT", year: 2019, mileage: 65000, price: 16500000, transmission: "MANUAL", fuelType: "DIESEL", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 2000 },

  // ── Kia Sportage (6) ────────────────────────────────────────
  { brand: "Kia", model: "Sportage", version: "2.0 LX FWD AT", year: 2022, mileage: 15000, price: 21000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2000 },
  { brand: "Kia", model: "Sportage", version: "2.0 LX FWD AT", year: 2021, mileage: 28000, price: 18500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Kia", model: "Sportage", version: "2.0 LX FWD AT", year: 2020, mileage: 44000, price: 16800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Rojo", doors: 4, engineCC: 2000 },
  { brand: "Kia", model: "Sportage", version: "2.0 LX FWD MT", year: 2019, mileage: 60000, price: 15200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 2000 },
  { brand: "Kia", model: "Sportage", version: "2.0 LX FWD MT", year: 2019, mileage: 55000, price: 13000000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Azul", doors: 4, engineCC: 2000 }, // GOOD_DEAL
  { brand: "Kia", model: "Sportage", version: "2.0 LX FWD MT", year: 2018, mileage: 78000, price: 13500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Plata", doors: 4, engineCC: 2000 },

  // ── Kia Rio (5) ─────────────────────────────────────────────
  { brand: "Kia", model: "Rio", version: "1.4 EX AT", year: 2021, mileage: 28000, price: 10200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1400 },
  { brand: "Kia", model: "Rio", version: "1.4 EX MT", year: 2020, mileage: 42000, price: 8900000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Gris", doors: 4, engineCC: 1400 },
  { brand: "Kia", model: "Rio", version: "1.4 LX MT", year: 2019, mileage: 58000, price: 7800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Rojo", doors: 4, engineCC: 1400 },
  { brand: "Kia", model: "Rio", version: "1.4 LX MT", year: 2018, mileage: 72000, price: 7200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 1400 },
  { brand: "Kia", model: "Rio", version: "1.4 LX MT", year: 2017, mileage: 85000, price: 6500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de La Araucanía", color: "Plata", doors: 4, engineCC: 1400 },

  // ── Mazda 3 (6) ─────────────────────────────────────────────
  { brand: "Mazda", model: "3", version: "2.0 Sport AT", year: 2021, mileage: 22000, price: 14800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 2000 },
  { brand: "Mazda", model: "3", version: "2.0 Sport AT", year: 2020, mileage: 38000, price: 13200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2000 },
  { brand: "Mazda", model: "3", version: "2.0 Grand Touring MT", year: 2019, mileage: 52000, price: 11800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Mazda", model: "3", version: "2.0 Sport AT", year: 2019, mileage: 48000, price: 12800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Azul", doors: 4, engineCC: 2000 }, // slightly overpriced
  { brand: "Mazda", model: "3", version: "2.0 Grand Touring MT", year: 2018, mileage: 68000, price: 10500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Negro", doors: 4, engineCC: 2000 },
  { brand: "Mazda", model: "3", version: "2.0 Sport MT", year: 2017, mileage: 82000, price: 9200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Blanco", doors: 4, engineCC: 2000 },

  // ── Mazda CX-5 (4) ──────────────────────────────────────────
  { brand: "Mazda", model: "CX-5", version: "2.5 Sport AWD AT", year: 2021, mileage: 28000, price: 22000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2500 },
  { brand: "Mazda", model: "CX-5", version: "2.0 Touring FWD AT", year: 2020, mileage: 42000, price: 19500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 2000 },
  { brand: "Mazda", model: "CX-5", version: "2.0 Touring FWD MT", year: 2019, mileage: 58000, price: 17800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Mazda", model: "CX-5", version: "2.5 Sport AWD AT", year: 2018, mileage: 72000, price: 16200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Plata", doors: 4, engineCC: 2500 },

  // ── Suzuki Swift (6) ────────────────────────────────────────
  { brand: "Suzuki", model: "Swift", version: "1.2 GL AT", year: 2022, mileage: 18000, price: 10200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Naranja", doors: 4, engineCC: 1200 },
  { brand: "Suzuki", model: "Swift", version: "1.2 GL MT", year: 2021, mileage: 28000, price: 9100000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1200 },
  { brand: "Suzuki", model: "Swift", version: "1.2 GL MT", year: 2020, mileage: 40000, price: 8300000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 1200 },
  { brand: "Suzuki", model: "Swift", version: "1.2 GL MT", year: 2019, mileage: 55000, price: 7400000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Azul", doors: 4, engineCC: 1200 },
  { brand: "Suzuki", model: "Swift", version: "1.2 GL MT", year: 2019, mileage: 52000, price: 6200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 1200 }, // VERY_GOOD_DEAL
  { brand: "Suzuki", model: "Swift", version: "1.2 GL MT", year: 2018, mileage: 68000, price: 7100000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Blanco", doors: 4, engineCC: 1200 },

  // ── Chevrolet Sail (5) ──────────────────────────────────────
  { brand: "Chevrolet", model: "Sail", version: "1.5 LT MT", year: 2020, mileage: 38000, price: 8500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1500 },
  { brand: "Chevrolet", model: "Sail", version: "1.5 LS MT", year: 2019, mileage: 52000, price: 7800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 1500 },
  { brand: "Chevrolet", model: "Sail", version: "1.5 LS MT", year: 2018, mileage: 68000, price: 7100000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Plata", doors: 4, engineCC: 1500 },
  { brand: "Chevrolet", model: "Sail", version: "1.5 LS MT", year: 2017, mileage: 82000, price: 6400000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Blanco", doors: 4, engineCC: 1500 },
  { brand: "Chevrolet", model: "Sail", version: "1.5 LT MT", year: 2017, mileage: 78000, price: 8200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 1500 }, // OVERPRICED

  // ── Nissan Kicks (5) ────────────────────────────────────────
  { brand: "Nissan", model: "Kicks", version: "1.6 Advance CVT", year: 2022, mileage: 18000, price: 14800000, transmission: "CVT", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1600 },
  { brand: "Nissan", model: "Kicks", version: "1.6 Sense CVT", year: 2021, mileage: 30000, price: 13200000, transmission: "CVT", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Naranja", doors: 4, engineCC: 1600 },
  { brand: "Nissan", model: "Kicks", version: "1.6 Sense CVT", year: 2020, mileage: 45000, price: 12000000, transmission: "CVT", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 1600 },
  { brand: "Nissan", model: "Kicks", version: "1.6 Sense CVT", year: 2020, mileage: 42000, price: 10200000, transmission: "CVT", fuelType: "GASOLINE", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 1600 }, // GOOD_DEAL
  { brand: "Nissan", model: "Kicks", version: "1.6 Sense CVT", year: 2019, mileage: 60000, price: 11200000, transmission: "CVT", fuelType: "GASOLINE", region: "Región de La Araucanía", color: "Azul", doors: 4, engineCC: 1600 },

  // ── Volkswagen Golf (5) ─────────────────────────────────────
  { brand: "Volkswagen", model: "Golf", version: "1.4 TSI Comfortline AT", year: 2020, mileage: 32000, price: 14200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Gris", doors: 4, engineCC: 1400 },
  { brand: "Volkswagen", model: "Golf", version: "1.4 TSI Comfortline MT", year: 2019, mileage: 48000, price: 12800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Negro", doors: 4, engineCC: 1400 },
  { brand: "Volkswagen", model: "Golf", version: "1.4 TSI Trendline MT", year: 2018, mileage: 62000, price: 11500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Blanco", doors: 4, engineCC: 1400 },
  { brand: "Volkswagen", model: "Golf", version: "1.4 TSI Trendline MT", year: 2018, mileage: 68000, price: 10200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Rojo", doors: 4, engineCC: 1400 },
  { brand: "Volkswagen", model: "Golf", version: "1.4 TSI Comfortline AT", year: 2017, mileage: 80000, price: 9800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Gris", doors: 4, engineCC: 1400 },

  // ── Ford Focus (5) ──────────────────────────────────────────
  { brand: "Ford", model: "Focus", version: "2.0 Titanium AT", year: 2019, mileage: 45000, price: 11200000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Azul", doors: 4, engineCC: 2000 },
  { brand: "Ford", model: "Focus", version: "2.0 SE AT", year: 2018, mileage: 58000, price: 10100000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2000 },
  { brand: "Ford", model: "Focus", version: "2.0 S MT", year: 2018, mileage: 62000, price: 8500000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Plata", doors: 4, engineCC: 2000 }, // GOOD_DEAL
  { brand: "Ford", model: "Focus", version: "2.0 SE AT", year: 2017, mileage: 75000, price: 8900000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región del Biobío", color: "Rojo", doors: 4, engineCC: 2000 },
  { brand: "Ford", model: "Focus", version: "2.0 S MT", year: 2017, mileage: 80000, price: 8200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Blanco", doors: 4, engineCC: 2000 },

  // ── Peugeot 208 (5) ─────────────────────────────────────────
  { brand: "Peugeot", model: "208", version: "1.6 Allure AT", year: 2021, mileage: 25000, price: 10800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 1600 },
  { brand: "Peugeot", model: "208", version: "1.6 Active AT", year: 2020, mileage: 38000, price: 9500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1600 },
  { brand: "Peugeot", model: "208", version: "1.2 Active MT", year: 2019, mileage: 52000, price: 8700000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 1200 },
  { brand: "Peugeot", model: "208", version: "1.2 Active MT", year: 2019, mileage: 48000, price: 7200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Azul", doors: 4, engineCC: 1200 }, // GOOD_DEAL
  { brand: "Peugeot", model: "208", version: "1.2 Access MT", year: 2018, mileage: 65000, price: 8100000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Maule", color: "Blanco", doors: 4, engineCC: 1200 },

  // ── Honda CR-V (4) ──────────────────────────────────────────
  { brand: "Honda", model: "CR-V", version: "1.5T EX AWD CVT", year: 2021, mileage: 28000, price: 23500000, transmission: "CVT", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 1500 },
  { brand: "Honda", model: "CR-V", version: "2.0 EX FWD AT", year: 2020, mileage: 42000, price: 21000000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Plata", doors: 4, engineCC: 2000 },
  { brand: "Honda", model: "CR-V", version: "2.0 LX FWD AT", year: 2019, mileage: 58000, price: 18800000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Honda", model: "CR-V", version: "2.0 LX FWD AT", year: 2018, mileage: 72000, price: 17500000, transmission: "AUTOMATIC", fuelType: "GASOLINE", region: "Región del Biobío", color: "Blanco", doors: 4, engineCC: 2000 },

  // ── Mitsubishi ASX (4) ──────────────────────────────────────
  { brand: "Mitsubishi", model: "ASX", version: "2.0 GLS FWD CVT", year: 2021, mileage: 30000, price: 17500000, transmission: "CVT", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Blanco", doors: 4, engineCC: 2000 },
  { brand: "Mitsubishi", model: "ASX", version: "2.0 GL FWD CVT", year: 2020, mileage: 44000, price: 15800000, transmission: "CVT", fuelType: "GASOLINE", region: "Región Metropolitana de Santiago", color: "Rojo", doors: 4, engineCC: 2000 },
  { brand: "Mitsubishi", model: "ASX", version: "2.0 GL FWD MT", year: 2019, mileage: 60000, price: 14200000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región de Valparaíso", color: "Gris", doors: 4, engineCC: 2000 },
  { brand: "Mitsubishi", model: "ASX", version: "2.0 GL FWD MT", year: 2018, mileage: 75000, price: 12800000, transmission: "MANUAL", fuelType: "GASOLINE", region: "Región del Biobío", color: "Plata", doors: 4, engineCC: 2000 },
];

const sources = [
  { name: "Chileautos", slug: "chileautos", baseUrl: "https://www.chileautos.cl" },
  { name: "Auto.cl", slug: "auto-cl", baseUrl: "https://www.auto.cl" },
  { name: "Yapo.cl", slug: "yapo", baseUrl: "https://www.yapo.cl/vehiculos" },
  { name: "Automotoras", slug: "automotoras", baseUrl: "https://www.automotoras.cl" },
];

async function main() {
  console.log("🌱 Starting seed...");

  // Cleanup
  await prisma.offer.deleteMany();
  await prisma.priceSnapshot.deleteMany();
  await prisma.listing.deleteMany();
  await prisma.vehicle.deleteMany();
  await prisma.source.deleteMany();

  // Create sources
  const createdSources = await Promise.all(
    sources.map((s) => prisma.source.create({ data: s }))
  );
  console.log(`✅ Created ${createdSources.length} sources`);

  // Build comparables map (brand+model → prices for scoring)
  const comparablesMap = new Map<string, ComparableVehicle[]>();
  rawVehicles.forEach((v) => {
    const key = `${v.brand}__${v.model}`.toLowerCase();
    if (!comparablesMap.has(key)) comparablesMap.set(key, []);
    comparablesMap.get(key)!.push({
      brand: v.brand,
      model: v.model,
      year: v.year,
      mileage: v.mileage,
      listedPrice: v.price,
    });
  });

  let createdCount = 0;

  for (let i = 0; i < rawVehicles.length; i++) {
    const v = rawVehicles[i];
    const sourceIndex = i % createdSources.length;
    const source = createdSources[sourceIndex];

    // Calculate score using all OTHER vehicles of same brand+model as comparables
    const key = `${v.brand}__${v.model}`.toLowerCase();
    const allComparables = comparablesMap.get(key) ?? [];
    const comparables = allComparables.filter((c) => c.listedPrice !== v.price);

    const score = calculateScore(
      {
        brand: v.brand,
        model: v.model,
        version: v.version,
        year: v.year,
        mileage: v.mileage,
        transmission: v.transmission,
        fuelType: v.fuelType,
        region: v.region,
        listedPrice: v.price,
      },
      comparables
    );

    // Create vehicle + listing
    const vehicle = await prisma.vehicle.create({
      data: {
        brand: v.brand,
        model: v.model,
        version: v.version,
        year: v.year,
        mileage: v.mileage,
        transmission: v.transmission,
        fuelType: v.fuelType,
        region: v.region,
        color: v.color,
        doors: v.doors,
        engineCC: v.engineCC,
        imageUrls: [],
        listings: {
          create: {
            sourceId: source.id,
            listedPrice: v.price,
            marketEstimate: score.marketEstimate,
            deltaAmount: score.deltaAmount,
            deltaPercentage: score.deltaPercentage,
            opportunityScore: score.opportunityScore,
            confidenceScore: score.confidenceScore,
            scoreExplanation: score.explanation,
            isActive: true,
            originalUrl: `${source.baseUrl}/autos/${v.brand.toLowerCase()}-${v.model.toLowerCase().replace(/\s/g, "-")}-${v.year}`,
            description: `${v.brand} ${v.model} ${v.version ?? ""} ${v.year} en ${v.region}. ${v.mileage.toLocaleString("es-CL")} km. ${v.transmission === "AUTOMATIC" ? "Automático" : v.transmission === "CVT" ? "CVT" : "Manual"}. ${v.fuelType === "GASOLINE" ? "Bencina" : v.fuelType === "DIESEL" ? "Diésel" : v.fuelType === "HYBRID" ? "Híbrido" : v.fuelType === "ELECTRIC" ? "Eléctrico" : "Gas"}.`,
          },
        },
      },
    });

    // Create price snapshot
    await prisma.priceSnapshot.create({
      data: {
        vehicleId: vehicle.id,
        price: v.price,
        source: source.slug,
      },
    });

    createdCount++;
    if (createdCount % 10 === 0) {
      console.log(`   ...${createdCount}/${rawVehicles.length} vehicles`);
    }
  }

  console.log(`✅ Created ${createdCount} vehicles with listings`);

  // Stats summary
  const listings = await prisma.listing.groupBy({
    by: ["opportunityScore"],
    _count: { opportunityScore: true },
  });
  console.log("\n📊 Score distribution:");
  listings.forEach((l) => {
    console.log(`   ${l.opportunityScore}: ${l._count.opportunityScore}`);
  });

  console.log("\n🎉 Seed complete!");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
