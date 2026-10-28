import { en, es, de, type Dict, type Locale } from "./i18n";

const dicts: Record<Locale, Dict> = { en, es, de };

/**
 * Resolve the string table for the active UI language.
 *
 * Returns the dictionary object (e.g. `t.loading`) with English fallback for
 * keys missing from a translated locale.
 */
export function useTranslation(locale: Locale = "en"): Dict {
  return dicts[locale] ?? dicts.en;
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
