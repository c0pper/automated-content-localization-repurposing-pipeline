import { useCallback } from "react";
import { en, es, de } from "./i18n";

export type Locale = "en" | "es" | "de";

const dicts: Record<Locale, typeof en> = { en, es, de };

export function useTranslation(locale = "en") {
  const t = dicts[locale as Locale] ?? dicts.en;
  return useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      let value = (t as Record<string, string>)[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          value = value.replace(new RegExp(`\\{\\{\\s*${k}\\s*\\}\\}`, "g"), String(v));
        }
      }
      return value;
    },
    [locale],
  );
}
