import { useStore } from "zustand";
import { localizationStore } from "@/store";
import { DICTS, type Dict } from "./i18n";

/**
 * Resolve the string table for the Creator's UI language (Localization
 * domain), re-rendering the caller when it changes.
 *
 * Returns the dictionary object (e.g. `t.loading`) with English fallback for
 * keys missing from a translated locale.
 */
export function useTranslation(): Dict {
  const locale = useStore(localizationStore, (s) => s.uiLanguage);
  return DICTS[locale] ?? DICTS.en;
}

/** Replace `{{var}}` placeholders in a translated string. */
export function interpolate(
  template: string,
  vars: Record<string, string | number>,
): string {
  let value = template;
  for (const [key, replacement] of Object.entries(vars)) {
    value = value.replace(
      new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, "g"),
      String(replacement),
    );
  }
  return value;
}
