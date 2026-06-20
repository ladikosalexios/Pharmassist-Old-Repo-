import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "../locales/en.json";
import el from "../locales/el.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      el: { translation: el },
    },
    // Default to Greek (HMVO req. 1): a fresh load with no ?lng and no stored
    // preference resolves to "el". "navigator" is intentionally omitted from the
    // detection order so a non-Greek browser doesn't render the app in English;
    // an explicit ?lng=en or a stored pharmassist_lang still switches to English.
    fallbackLng: "el",
    detection: {
      order: ["querystring", "localStorage"],
      lookupLocalStorage: "pharmassist_lang",
    },
    supportedLngs: ["el", "en"],
    interpolation: { escapeValue: false },
  });

// Keep <html lang> in sync with the active language so browser auto-translation
// (Chrome/Safari) detects the real content language — HMVO req. 3. Without this
// the page always declares lang="en" even when rendering Greek.
function applyDocumentLang(lng?: string) {
  if (typeof document !== "undefined") {
    document.documentElement.lang = (lng || i18n.resolvedLanguage || "el").split("-")[0];
  }
}
i18n.on("languageChanged", applyDocumentLang);
applyDocumentLang(i18n.resolvedLanguage);

export default i18n;
