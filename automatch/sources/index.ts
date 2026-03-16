import { ChileautosProvider } from "./chileautos";
import { AutoClProvider } from "./auto-cl";
import { YapoProvider } from "./yapo";
import { AutomotorasProvider } from "./automotoras";
import type { BaseProvider } from "./base";

export const providers: BaseProvider[] = [
  new ChileautosProvider(),
  new AutoClProvider(),
  new YapoProvider(),
  new AutomotorasProvider(),
];

export { BaseProvider } from "./base";
export type { RawListing, NormalizedListing } from "./base";
