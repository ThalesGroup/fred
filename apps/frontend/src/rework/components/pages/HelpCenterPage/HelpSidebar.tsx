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

import { Fragment } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import NavigationMenuItem from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import { helpPagePath, type HelpSectionTree } from "@rework/features/helpCenter/content";
import type { HelpLang } from "@rework/features/helpCenter/manifest";
import styles from "./HelpSidebar.module.scss";

interface HelpSidebarProps {
  tree: HelpSectionTree[];
  lang: HelpLang;
  activeSectionId: string;
  activePageId: string;
}

/**
 * Wiki navigation rail: one header per section (from the manifest), then the
 * section's pages as the same menu items as the team navigation rail.
 */
export default function HelpSidebar({ tree, lang, activeSectionId, activePageId }: HelpSidebarProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <aside className={styles.sidebar} aria-label={t("rework.helpCenter.sidebarAria")}>
      {tree.map((section) => (
        <Fragment key={section.id}>
          <div className={styles.sectionHeader}>{t(section.titleKey)}</div>
          {section.pages.map((page) => (
            <NavigationMenuItem
              key={page.id}
              type="button"
              label={page.title}
              icon={{ category: "outlined", type: page.icon }}
              selected={section.id === activeSectionId && page.id === activePageId}
              onClick={() => navigate(helpPagePath(lang, section.id, page.id))}
            />
          ))}
        </Fragment>
      ))}
    </aside>
  );
}
