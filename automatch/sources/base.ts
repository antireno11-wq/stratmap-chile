import type { Transmission, FuelType } from "@prisma/client";

export interface RawListing {
  externalId: string;
  title: string;
  brand: string;
  model: string;
  version?: string;
  year: number;
  mileage: number;
  price: number;
  region: string;
  comuna?: string;
  transmission: Transmission;
  fuelType: FuelType;
  color?: string;
  doors?: number;
  engineCC?: number;
  imageUrls?: string[];
  description?: string;
  originalUrl?: string;
}

export interface NormalizedListing {
  externalId: string;
  brand: string;
  model: string;
  version?: string;
  year: number;
  mileage: number;
  listedPrice: number;
  region: string;
  comuna?: string;
  transmission: Transmission;
  fuelType: FuelType;
  color?: string;
  doors?: number;
  engineCC?: number;
  imageUrls: string[];
  description?: string;
  originalUrl?: string;
}

export abstract class BaseProvider {
  abstract readonly slug: string;
  abstract readonly name: string;

  abstract fetchListings(): Promise<RawListing[]>;

  normalizeListing(raw: RawListing): NormalizedListing {
    return {
      externalId: raw.externalId,
      brand: this.normalizeBrand(raw.brand),
      model: this.normalizeModel(raw.model),
      version: raw.version,
      year: raw.year,
      mileage: raw.mileage,
      listedPrice: raw.price,
      region: raw.region,
      comuna: raw.comuna,
      transmission: raw.transmission,
      fuelType: raw.fuelType,
      color: raw.color,
      doors: raw.doors,
      engineCC: raw.engineCC,
      imageUrls: raw.imageUrls ?? [],
      description: raw.description,
      originalUrl: raw.originalUrl,
    };
  }

  private normalizeBrand(brand: string): string {
    const map: Record<string, string> = {
      toyota: "Toyota", suzuki: "Suzuki", hyundai: "Hyundai",
      kia: "Kia", mazda: "Mazda", chevrolet: "Chevrolet",
      nissan: "Nissan", peugeot: "Peugeot", volkswagen: "Volkswagen",
      ford: "Ford", honda: "Honda", mitsubishi: "Mitsubishi",
    };
    return map[brand.toLowerCase()] ?? brand;
  }

  private normalizeModel(model: string): string {
    return model.trim();
  }

  async fetchAndNormalize(): Promise<NormalizedListing[]> {
    const raw = await this.fetchListings();
    return raw.map((r) => this.normalizeListing(r));
  }
}
