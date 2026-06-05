import i18n, { type InitOptions } from "i18next";
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
    fallbackLng: "el",
    detection: {
      order: ["querystring", "localStorage", "navigator"],
      lookupLocalStorage: "pharmassist_lang",
    },
    supportedLngs: ["el", "en"],
    interpolation: { escapeValue: false },
    // `initImmediate` is honoured at runtime but absent from i18next 26's
    // InitOptions typings — cast keeps the synchronous-init behaviour.
    initImmediate: false,
  } as InitOptions);

export default i18n;
