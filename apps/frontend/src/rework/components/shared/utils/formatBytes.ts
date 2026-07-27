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

// One shared, locale-aware byte formatter (replaces the duplicate copies that
// used to live in DocumentUploadDrawer and SessionAttachmentsDrawer). Unit
// labels are localized by `Intl.NumberFormat` — English renders "1.5 MB",
// French "1,5 Mo" — so callers never hard-code "Ko/Mo/Go" vs "KB/MB/GB".
//
// Callers with a translation context should pass `i18n.language`; the default
// (the browser locale) keeps the util dependency-free — importing the app i18n
// singleton here would pull it into every unit test that renders a caller.
const UNITS = ["byte", "kilobyte", "megabyte", "gigabyte", "terabyte"] as const;

const defaultLocale = (): string | undefined => (typeof navigator !== "undefined" ? navigator.language : undefined);

function formatUnit(value: number, unit: (typeof UNITS)[number], locale: string | undefined): string {
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * Human-readable, locale-aware file size. Picks the largest unit (up to TB) for
 * which the value is ≥ 1, rounds bytes to a whole number and larger units to one
 * decimal. `locale` defaults to the active i18n language.
 */
export function formatBytes(bytes: number, locale: string | undefined = defaultLocale()): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return formatUnit(0, "byte", locale);
  const k = 1024;
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), UNITS.length - 1);
  const value = bytes / Math.pow(k, exponent);
  const rounded = exponent === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return formatUnit(rounded, UNITS[exponent], locale);
}
