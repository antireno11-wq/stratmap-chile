import { BaseProvider, RawListing } from "../base";

/**
 * Automotoras independientes provider (MOCK)
 * Real implementation: aggregate from multiple independent dealers via their APIs
 */
export class AutomotorasProvider extends BaseProvider {
  readonly slug = "automotoras";
  readonly name = "Automotoras";

  async fetchListings(): Promise<RawListing[]> {
    // TODO: implement real scraping/API integration
    return [];
  }
}
