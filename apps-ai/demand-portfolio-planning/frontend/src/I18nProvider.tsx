import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { dictionaries, format, type Key, type Lang } from "./i18n";

const STORAGE_KEY = "dpp.lang";

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key, vars?: Record<string, string | number>) => string;
}

const Ctx = createContext<I18nValue | null>(null);

function detectInitial(): Lang {
  if (typeof window === "undefined") return "de";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "de" || stored === "en") return stored;
  if (typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("en")) {
    return "en";
  }
  return "de";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectInitial);

  useEffect(() => {
    document.documentElement.lang = lang;
    window.localStorage.setItem(STORAGE_KEY, lang);
  }, [lang]);

  const setLang = useCallback((l: Lang) => setLangState(l), []);

  const t = useCallback(
    (key: Key, vars?: Record<string, string | number>) =>
      format(dictionaries[lang][key] ?? dictionaries.de[key], vars),
    [lang],
  );

  const value = useMemo<I18nValue>(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18nValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n must be used inside I18nProvider");
  return v;
}

export function useT() {
  return useI18n().t;
}
