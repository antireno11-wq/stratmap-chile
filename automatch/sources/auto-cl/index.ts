import { BaseProvider, RawListing } from "../base";

/**
 * Auto.cl provider (MOCK)
 * Real implementation: replace fetchListings() with HTTP requests to Auto.cl
 */
export class AutoClProvider extends BaseProvider {
  readonly slug = "auto-cl";
  readonly name = "Auto.cl";

  async fetchListings(): Promise<RawListing[]> {
    // TODO: implement real scraping/API integration
    return [];
  }
}
