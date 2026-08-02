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

import type { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export const HELP_LANGS = ["fr", "en"] as const;
export type HelpLang = (typeof HELP_LANGS)[number];

export function isHelpLang(value: string | undefined): value is HelpLang {
  return HELP_LANGS.includes(value as HelpLang);
}

export interface HelpSectionSpec {
  /** URL segment and content folder name (`content/<lang>/<id>/`). */
  id: string;
  /** i18n key for the section title shown in the sidebar and breadcrumb. */
  titleKey: string;
  /** Icon used for the section's landing-page item in the sidebar. */
  icon: IconProps;
}

/**
 * Ordered list of the Help Center's sections. Pages inside each section come
 * from the markdown files in `content/<lang>/<id>/` (see `content.ts`) — this
 * manifest only fixes the sections' identity, order, and chrome. Adding a
 * page never requires touching this file; adding a section does.
 */
export const HELP_SECTIONS: HelpSectionSpec[] = [
  {
    id: "getting-started",
    titleKey: "rework.helpCenter.sections.gettingStarted",
    icon: { category: "outlined", type: "rocket_launch" },
  },
  {
    id: "features",
    titleKey: "rework.helpCenter.sections.features",
    icon: { category: "outlined", type: "widgets" },
  },
  {
    id: "guides",
    titleKey: "rework.helpCenter.sections.guides",
    icon: { category: "outlined", type: "map" },
  },
  {
    id: "troubleshooting",
    titleKey: "rework.helpCenter.sections.troubleshooting",
    icon: { category: "outlined", type: "build" },
  },
  {
    id: "faq",
    titleKey: "rework.helpCenter.sections.faq",
    icon: { category: "outlined", type: "quiz" },
  },
  {
    id: "architecture",
    titleKey: "rework.helpCenter.sections.architecture",
    icon: { category: "outlined", type: "architecture" },
  },
  {
    id: "changelog",
    titleKey: "rework.helpCenter.sections.changelog",
    icon: { category: "outlined", type: "new_releases" },
  },
];

export const DEFAULT_SECTION_ID = HELP_SECTIONS[0].id;
