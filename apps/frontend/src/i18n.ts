// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import en from "./locales/en/translation.json";
import fr from "./locales/fr/translation.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      fr: { translation: fr },
    },
    fallbackLng: "en",
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      caches: [],
    },
  });

export default i18n;

/** Keep only string labels whose shipped key is a string: anything else cannot rename text. */
function shippedLabels(overrides: unknown, shipped: unknown): Record<string, unknown> {
  const labels: Record<string, unknown> = {};
  if (!overrides || typeof overrides !== "object" || !shipped || typeof shipped !== "object") return labels;
  for (const [key, value] of Object.entries(overrides)) {
    if (!Object.prototype.hasOwnProperty.call(shipped, key)) continue;
    const current = (shipped as Record<string, unknown>)[key];
    if (typeof current === "string" && typeof value === "string") labels[key] = value;
    else if (current && typeof current === "object") {
      const nested = shippedLabels(value, current);
      if (Object.keys(nested).length) labels[key] = nested;
    }
  }
  return labels;
}

/** Apply optional deployment labels before render; a broken file leaves the shipped text. */
export async function loadThemeTranslations(): Promise<void> {
  await Promise.all(
    ["en", "fr"].map(async (language) => {
      try {
        const response = await fetch(`/theme-translations/${language}.json`, { cache: "no-cache" });
        if (response.status === 404) return;
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const labels = shippedLabels(await response.json(), i18n.getResourceBundle(language, "translation"));
        i18n.addResourceBundle(language, "translation", labels, true, true);
      } catch (error) {
        console.warn(`Theme translations for ${language} ignored:`, error);
      }
    }),
  );
}
