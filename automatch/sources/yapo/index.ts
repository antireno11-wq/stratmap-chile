import { BaseProvider, RawListing } from "../base";

/**
 * Yapo provider (MOCK)
 * Real implementation: replace fetchListings() with HTTP requests to Yapo.cl
 */
export class YapoProvider extends BaseProvider {
  readonly slug = "yapo";
  readonly name = "Yapo.cl";

  async fetchListings(): Promise<RawListing[]> {
    // TODO: implement real scraping/API integration
    return [];
  }
}
