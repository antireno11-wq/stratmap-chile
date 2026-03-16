import { BaseProvider, RawListing } from "../base";

/**
 * ChileAutos provider (MOCK)
 * Real implementation: replace fetchListings() with HTTP requests to ChileAutos API/scraper
 */
export class ChileautosProvider extends BaseProvider {
  readonly slug = "chileautos";
  readonly name = "ChileAutos";

  async fetchListings(): Promise<RawListing[]> {
    // TODO: implement real scraping/API integration
    // Currently returns empty array — data is seeded directly
    return [];
  }
}
