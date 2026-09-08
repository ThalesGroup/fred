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

const FALLBACK_LOCALE = "en";

/**
 * Pick an application's display string for the active locale. Applications are
 * deployed independently of Fred, so their labels arrive as locale maps in the
 * catalog rather than as keys into Fred's own translation bundle.
 */
export function applicationLocaleText(text: Readonly<Record<string, string>>, locale: string): string {
  const candidates = [locale, locale.split("-")[0], FALLBACK_LOCALE];
  for (const candidate of candidates) {
    // Own-property only: the catalog is deployment configuration, and an
    // inherited "constructor" or "toString" must never become a label.
    if (Object.prototype.hasOwnProperty.call(text, candidate)) {
      const value = text[candidate];
      if (value) return value;
    }
  }
  return Object.values(text).find((value) => Boolean(value)) ?? "";
}
