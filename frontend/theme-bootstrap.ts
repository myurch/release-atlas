import { applyTheme, currentPreference } from "./theme";
// Apply before styles paint to avoid a light flash when opening a dark review.
applyTheme(currentPreference());
