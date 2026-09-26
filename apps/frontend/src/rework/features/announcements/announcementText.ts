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

import { resolveLocalizedText } from "@core/hooks/useLocalizedUploadWarning";

/**
 * Resolve one announcement text: viewer's locale, then `en`, then ANY locale
 * the admin actually filled in.
 *
 * The last step is what the deployer-configured banners do not need and an
 * announcement does. The backend requires only one non-empty locale and the
 * editor opens on the French tab, so a French-only announcement is entirely
 * ordinary — resolving it to nothing for an English viewer would render an
 * accented strip with an icon, a close button and no words in it. A message in
 * the wrong language is information; an empty banner is a bug on screen.
 */
export function resolveAnnouncementText(
  map: { [locale: string]: string } | undefined | null,
  language: string | undefined,
): string | null {
  const preferred = resolveLocalizedText(map, language);
  if (preferred) return preferred;
  const anyFilled = Object.values(map ?? {}).find((text) => text.trim());
  return anyFilled ?? null;
}
