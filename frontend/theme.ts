export type ThemePreference = "system" | "dark" | "light";
export type Theme = "dark" | "light";
export const THEME_KEY = "release-atlas-appearance";

export function readPreference(
  storage?: Pick<Storage, "getItem">,
): ThemePreference {
  try {
    const value = storage?.getItem(THEME_KEY);
    return value === "dark" || value === "light" ? value : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(
  preference: ThemePreference,
  hostLight: boolean,
  hostDark: boolean,
): Theme {
  if (preference !== "system") return preference;
  return hostLight && !hostDark ? "light" : "dark";
}

export function currentPreference(): ThemePreference {
  try {
    return readPreference(window.localStorage);
  } catch {
    return "system";
  }
}

export function applyTheme(preference: ThemePreference): void {
  let light = false,
    dark = false;
  try {
    light = window.matchMedia("(prefers-color-scheme: light)").matches;
    dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    /* No host preference available: resolveTheme defaults to dark. */
  }
  document.documentElement.dataset.theme = resolveTheme(
    preference,
    light,
    dark,
  );
}
