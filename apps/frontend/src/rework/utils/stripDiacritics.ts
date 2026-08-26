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

/**
 * Strips combining diacritical marks after NFD decomposition
 * ("données" -> "donnees", Cyrillic "й" -> "и"). Characters with no
 * decomposition (CJK, ß, ø, ...) pass through unchanged. Shared by heading
 * slugs (slugifyHeading) and Mermaid node ID derivation so the two never
 * diverge on the same accented text.
 */
export function stripDiacritics(text: string): string {
  return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
