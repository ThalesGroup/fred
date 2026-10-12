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

import { useTranslation } from "react-i18next";
import { useActivePatchNoteQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { resolveAnnouncementText } from "./announcementText";

/**
 * The active patch note, resolved to the viewer's locale, for the load-time gate
 * and the profile menu. Title and body share their locales (the backend enforces
 * it), so resolving each with the same fallbacks lands on the same language.
 */
export function useActivePatchNote() {
  const { i18n } = useTranslation();
  // Read once per load: a note activated mid-session waits for the next load.
  const { data } = useActivePatchNoteQuery();
  const note = data?.patch_note;
  const title = note && resolveAnnouncementText(note.title, i18n.language);
  const markdown = note && resolveAnnouncementText(note.description_long, i18n.language);
  if (!note || !title || !markdown) return null;
  return { note, title, markdown, dismissed: data.dismissed ?? false };
}
